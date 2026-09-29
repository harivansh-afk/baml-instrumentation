"""Derive a plain-text overview and combined CSVs after measurement completes."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics

from report import summarize, versions_for_cases
from run import FIELDS, csv_write, write


ORDER = [
    "baml/off",
    "baml/low",
    "baml/medium",
    "baml/high",
    "rust",
    "go",
    "python",
    "node",
    "bun",
]


def variant(row):
    return "baml/" + row["level"] if row["language"] == "baml" else row["language"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("collection", type=Path)
    a = p.parse_args()
    root = a.collection.resolve()
    protocol = json.loads((root / "protocol.json").read_text())
    manifest = json.loads((root / "compilation/0/manifest.json").read_text())
    versions = versions_for_cases(manifest, [s["case"] for s in protocol["scenarios"]])
    rows = []
    groups = defaultdict(list)
    for path in sorted(root.glob("runtime/*/*/samples.csv")):
        summarize(path)
        for row in csv.DictReader(path.open()):
            row["run_directory"] = str(path.parents[1].relative_to(root))
            if row["language"] == "go":
                observed = json.loads(
                    (path.parents[1] / row["trial_path"] / "sample.json").read_text()
                )
                row["allocated_bytes"] = observed.get("allocated_bytes")
                row["heap_alloc_bytes"] = observed.get(
                    "heap_alloc_bytes", observed.get("heap_live_bytes")
                )
                row["gc_pause_ns"] = observed.get("gc_pause_ns")
            rows.append(row)
            groups[(row["scenario"], variant(row))].append(row)
    csv_write(root / "runtime.csv", rows, FIELDS + ["run_directory"])
    summarize(root / "runtime.csv")
    coverage = []
    for scenario in protocol["scenarios"]:
        for name in ORDER:
            language = name.split("/")[0]
            if language not in scenario.get(
                "languages", ["baml", "rust", "go", "python", "node", "bun"]
            ):
                continue
            group = groups[(scenario["name"], name)]
            minimum = scenario.get("requires_gc", {}).get(language)
            counts = [int(r["gc_execution"]) for r in group if r.get("gc_execution")]
            coverage.append(
                dict(
                    scenario=scenario["name"],
                    configuration=name,
                    observations=len(group),
                    failed=sum(r["status"] != "ok" for r in group),
                    gc_minimum=min(counts) if counts else None,
                    gc_maximum=max(counts) if counts else None,
                    required_gc_minimum=minimum,
                    gc_requirement_passed=bool(group)
                    and all(
                        r["status"] == "ok"
                        and r.get("gc_execution")
                        and int(r["gc_execution"]) >= minimum
                        for r in group
                    )
                    if minimum
                    else None,
                )
            )
    write(root / "coverage.json", coverage)
    lines = [
        "Shared-host measurements, not an idle-machine baseline.",
        "",
        f"{len(rows)} runtime process trials; {sum(r['status'] != 'ok' for r in rows)} failed.",
        "Linux aarch64; CPUs "
        + protocol["cpus"]
        + "; "
        + str(protocol["workers"])
        + " runtime workers where supported.",
        "; ".join(
            language + ": " + versions[language]
            for language in ("baml", "rust", "go", "python", "node", "bun")
        ),
        "BAML uses the source-built release probe; published packed-executable results are separate.",
        f"{protocol['runtime_trials']} randomized process trials per configuration. Warmup/work counts are fixed in protocol.json.",
        "These finite batches do not establish JIT convergence or persistent-service behavior.",
        "",
        "Execution wall time: median microseconds per serialized job. No startup/drain time is subtracted.",
        "Each sample divides a timed batch by its job count; these are batch-average costs, not per-call latency percentiles.",
        "Startup uses one job; use the separate process-time table to assess its lifecycle cost.",
        f"{'scenario':30}" + "".join(f"{name:>13}" for name in ORDER),
    ]
    for scenario in protocol["scenarios"]:
        values = []
        for name in ORDER:
            values.append(
                [
                    int(r["execution_wall_ns"]) / int(r["jobs"]) / 1000
                    for r in groups[(scenario["name"], name)]
                    if r["status"] == "ok"
                ]
            )
        lines.append(
            f"{scenario['name']:30}"
            + "".join(
                f"{statistics.median(v):13.3f}" if v else f"{'N/A':>13}" for v in values
            )
        )
    lines += [
        "",
        "Fresh startup: median whole-process wall milliseconds and peak RSS MiB.",
        f"{'configuration':18}{'wall_ms':>14}{'RSS_MiB':>14}",
    ]
    for name in ORDER:
        group = [r for r in groups[("startup", name)] if r["status"] == "ok"]
        if group:
            lines.append(
                f"{name:18}{statistics.median(int(r['process_wall_ns']) for r in group) / 1e6:14.3f}{statistics.median(int(r['peak_rss_bytes']) for r in group) / 1048576:14.3f}"
            )
    compile_groups = defaultdict(list)
    for row in csv.DictReader((root / "compilation.csv").open()):
        compile_groups[(row["case"], row["language"])].append(row)
    lines += [
        "",
        f"Clean compiler-process wall seconds: median of {protocol['compile_trials']} builds; filesystem caches uncontrolled.",
        "BAML: source -> Program bytecode. Rust: native executable + dependencies. Go: native executable + stdlib.",
        "Python/Node/Bun: separate compilation unavailable; parsing/JIT stays in runtime observations.",
        f"{'case':30}{'BAML':>14}{'Rust':>14}{'Go':>14}",
    ]
    cases = list(dict.fromkeys(s["case"] for s in protocol["scenarios"]))
    for case in cases:
        values = [
            statistics.median(
                int(r["process_wall_ns"]) for r in compile_groups[(case, lang)]
            )
            / 1e9
            for lang in ("baml", "rust", "go")
        ]
        lines.append(f"{case:30}" + "".join(f"{v:14.6f}" for v in values))
    lines += [
        "",
        "Artifact sizes in bytes; different payloads, not interchangeable deployment totals.",
        f"{'case':30}{'BAML bytecode':>16}{'Rust+adapter':>16}{'Go+adapter':>16}{'BAML packed':>16}",
    ]
    packed = defaultdict(list)
    for path in root.glob("packed/*/pack.csv"):
        for row in csv.DictReader(path.open()):
            packed[row["case"]].append(int(row["packed_bytes"]))
    for case in cases:
        values = [
            int(
                statistics.median(
                    int(r["artifact_bytes"]) for r in compile_groups[(case, lang)]
                )
            )
            for lang in ("baml", "rust", "go")
        ]
        values.append(int(statistics.median(packed[case])))
        lines.append(f"{case:30}" + "".join(f"{v:16d}" for v in values))
    lines += [
        "",
        "Limits",
        "  Background services remained active. Affinity is not CPU isolation; host.json records each trial's conditions.",
        "  Execution includes adapter entry, allocation/reclamation and result serialization. Empty cases expose a floor; never subtract it.",
        "  BAML whole-process figures include post-execution metadata diagnostics; the packed path does not.",
        "  BAML/Go sustained-allocation claims require at least three execution-phase collections in every trial.",
        "  Python counts cyclic GC only; Rust uses ownership/reference counting; Node/Bun GC coverage is unknown.",
        "  BAML shared host, scripts and interpreter sizes are in artifacts.json/compilation.csv. Non-BAML full deployment inventories are unavailable.",
        "  HTTP, cloud telemetry and LLM capture are not covered. The optimizer may remove source-level calls.",
        "",
        "Data",
        "  runtime.csv and summary.csv retain per-scenario identities, successful sample counts, failures, ranges and coverage.",
        "  compilation.csv retains every build observation. packed/ retains published CLI packaging and invocation observations.",
        "  coverage.json checks the collection requirement; sources, exact inputs and logs remain in each runtime directory.",
    ]
    (root / "BASELINE.txt").write_text("\n".join(lines) + "\n")
    if any(
        c["failed"]
        or c["observations"] != protocol["runtime_trials"]
        or c["gc_requirement_passed"] is False
        for c in coverage
    ):
        raise SystemExit(
            "Collection contains failures, missing trials or insufficient GC coverage; inspect coverage.json"
        )


if __name__ == "__main__":
    main()
