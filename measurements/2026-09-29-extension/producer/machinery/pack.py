"""Measure published BAML packaging and a complete off-mode invocation."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

from fixtures import fixture, oracle, matches
from run import ROOT, CASES, tools, pins, env, digest, write, csv_write, version
import measure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=CASES,
        default=["00_startup", "01_array_traversal", "04_allocation_retention"],
    )
    parser.add_argument("--cpus", default=str(min(os.sched_getaffinity(0))))
    args = parser.parse_args()
    output = args.output.resolve()
    cpus = [int(x) for x in args.cpus.split(",")]
    if not cpus or not set(cpus) <= os.sched_getaffinity(0):
        parser.error("CPUs must belong to the allowed affinity")
    output.mkdir(parents=True, exist_ok=False)
    t = tools()
    rows = []
    metadata = dict(
        schema=1,
        kind="published-pack-validation",
        status="running",
        time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        platform=platform.platform(),
        machine_cpuinfo=Path("/proc/cpuinfo").read_text(),
        pins=pins(),
        cli_version=version([t["baml"], "--version"]),
        cpu_affinity=cpus,
        argv=sys.argv,
        observer_sha256=digest(measure.observer()),
        observer_compiler=version(["cc", "--version"]),
        controller_sha256=digest(__file__),
        baseline_accepted=False,
        cache_policy="bytecode and diagnostics caches disabled; filesystem caches uncontrolled",
    )
    write(output / "environment.json", metadata)
    try:
        collect(args, output, cpus, t, rows)
    except Exception as error:
        metadata.update(status="failed", error=str(error), completed_cases=len(rows))
        write(output / "environment.json", metadata)
        raise
    metadata.update(
        status="failed" if any(r["status"] != "ok" for r in rows) else "passed",
        completed_cases=len(rows),
    )
    write(output / "environment.json", metadata)
    if metadata["status"] != "passed":
        raise SystemExit(1)


def collect(args, output, cpus, t, rows):
    for case in args.cases:
        artifact = ROOT / ".cache/packed" / case
        artifact.mkdir(parents=True, exist_ok=True)
        source = artifact / "main.baml"
        source.write_text(
            (ROOT / "cases" / case / "workload.baml").read_text()
            + "\nfunction main(raw: string) -> string { run(prepare(raw)) }\n"
        )
        snapshot = output / case / "main.baml"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, snapshot)
        binary = artifact / "program"
        e = env(len(cpus))
        e["BAML_TELEMETRY"] = "off"
        command = [t["baml"], "pack", "main", "--file", str(source), "-o", str(binary)]
        build = measure.run(command, output / case / "build", e, cpus)
        if build["status"] != "ok":
            raise RuntimeError(f"pack failed: {output / case}")
        raw = fixture(
            case,
            size=64,
            batches=8,
            retain=2,
            fanout=1 if case == "08_stateful_workflow" else 8,
        )
        arguments = artifact / "arguments.json"
        write(arguments, dict(raw=raw))
        write(output / case / "arguments.json", dict(raw=raw))
        observation = measure.run(
            [str(binary), "--json-args", "@" + str(arguments)],
            output / case / "invocation",
            e,
            cpus,
        )
        try:
            correct = matches(
                json.loads(
                    json.loads((output / case / "invocation/stdout.txt").read_text())
                ),
                oracle(case, raw),
            )
        except (ValueError, TypeError):
            correct = False
        row = dict(
            case=case,
            language="baml",
            backend="published-pack",
            level="off",
            status="ok" if observation["status"] == "ok" and correct else "failed",
            compile_wall_ns=build["process_wall_ns"],
            compile_cpu_ns=build["process_cpu_ns"],
            compile_peak_rss_bytes=build["peak_rss_bytes"],
            process_wall_ns=observation["process_wall_ns"],
            process_cpu_ns=observation["process_cpu_ns"],
            peak_rss_bytes=observation["peak_rss_bytes"],
            packed_bytes=binary.stat().st_size,
            artifact_sha256=digest(binary),
            source_sha256=digest(source),
            cli_sha256=digest(t["baml"]),
            pack_host_sha256=digest(Path(t["baml"]).with_name("baml-pack-host")),
            source_revision=pins()["baml_revision"],
            gc_coverage="unknown",
            artifact_scope="published musl host plus Program; single executable; no external runtime",
        )
        write(
            output / case / "artifact.json",
            row
            | dict(
                compile_command=command,
                invocation_command=[str(binary), "--json-args", "@" + str(arguments)],
                environment=e,
                input=raw,
                compile_observation=build,
                invocation_observation=observation,
            ),
        )
        rows.append(row)
        csv_write(output / "pack.csv", rows, list(rows[0]))
        print(case, row["status"], flush=True)


if __name__ == "__main__":
    main()
