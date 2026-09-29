# /// script
# requires-python = ">=3.12"
# dependencies = ["plotly==6.3.0"]
# ///
"""Render a portable comparison document from one immutable collection."""

import argparse
import base64
import csv
import hashlib
import html
import json
import math
from collections import defaultdict
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ["baml", "rust", "go", "python", "node", "bun"]
NAMES = dict(zip(LANGUAGES, ["BAML", "Rust", "Go", "Python", "Node", "Bun"]))
COLORS = {
    "baml": "#244bb0",
    "rust": "#99502d",
    "go": "#087a79",
    "python": "#7955a2",
    "node": "#427434",
    "bun": "#596371",
}
TITLES = {
    "00_startup": "Startup",
    "01_array_traversal": "Array traversal",
    "02_merge_sort": "Merge sort",
    "03_json_aggregate": "JSON aggregation",
    "04_allocation_retention": "Allocation & retention",
    "05_async_fanout": "Async fanout",
    "07_function_calls": "Function calls",
}
# Key, label, unit, divisor, normalize by jobs, scope note.
METRICS = [
    (
        "execution_wall_ns",
        "Execution wall / job",
        "µs / job",
        1000,
        True,
        "Timed batch ÷ jobs. Includes adapter entry, allocation/reclamation and result serialization. Each point is a process batch average, not a per-call latency sample.",
    ),
    (
        "execution_cpu_ns",
        "Execution CPU / job",
        "µs / job",
        1000,
        True,
        "Process CPU consumed during the execution batch ÷ jobs. CPU can exceed wall time when threads run concurrently.",
    ),
    (
        "process_wall_ns",
        "Whole-process wall",
        "ms",
        1e6,
        False,
        "Observer fork to child reaped, including preparation, warmup, all jobs and shutdown. BAML includes post-execution metadata diagnostics.",
    ),
    (
        "process_cpu_ns",
        "Whole-process CPU",
        "ms",
        1e6,
        False,
        "wait4 user + system CPU, including threads and waited descendants. This is the entire process lifecycle.",
    ),
    (
        "peak_rss_bytes",
        "Peak process RSS",
        "MiB",
        1048576,
        False,
        "wait4 resident-memory high-water mark. Includes the runtime, adapter and diagnostic machinery. RSS is not live heap.",
    ),
    (
        "launch_to_ready_ns",
        "Launch to ready",
        "ms",
        1e6,
        False,
        "Controller launch to received ready marker; includes observer and pipe overhead. This is not exact runtime initialization time.",
    ),
    (
        "drain_ns",
        "BAML drain",
        "ms",
        1e6,
        False,
        "BAML shutdown/drain phase after measured execution. Reference runtimes do not expose an equivalent phase.",
    ),
    (
        "recording_bytes",
        "BTEL recording size",
        "MiB",
        1048576,
        False,
        "Local recording bytes across the whole process, including prepare, warmup and execution. No destination produces zero bytes even when BTEL processing is enabled.",
    ),
    (
        "gc_execution",
        "Observed execution GC",
        "collections",
        1,
        False,
        "Collections observed during the entire execution batch: BAML full collections, Go GC cycles, Python cyclic collections. These counters have different meanings. Rust: not applicable; Node/Bun: unavailable.",
    ),
    (
        "allocated_bytes",
        "Go allocated bytes",
        "MiB",
        1048576,
        False,
        "Go TotalAlloc delta over execution. Comparable allocation counters are unavailable for the other runtimes.",
    ),
    (
        "heap_alloc_bytes",
        "Go heap allocation",
        "MiB",
        1048576,
        False,
        "Go HeapAlloc at the end of execution. Includes unreclaimed garbage; not a live-object size. The export corrects the original raw label heap_live_bytes.",
    ),
    (
        "gc_pause_ns",
        "Go GC pause total",
        "ms",
        1e6,
        False,
        "Go PauseTotalNs delta over execution; concurrent cycles can cross the batch boundary. BAML pause attribution requires a separate profiling build and is unavailable here.",
    ),
]


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def stats(values):
    if not values:
        return None
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Measurements must be finite and nonnegative")
    return {
        "n": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
        "values": values,
    }


def metric_stats(rows, metric):
    key, _, _, divisor, per_job, _ = metric
    values = []
    for row in rows:
        if row["status"] != "ok" or row.get(key) in (None, ""):
            continue
        if key in ("recording_bytes", "drain_ns") and row["language"] != "baml":
            continue
        jobs = int(row["jobs"]) if per_job else 1
        if jobs <= 0:
            raise ValueError("Measured batches must contain at least one job")
        values.append(float(row[key]) / divisor / jobs)
    return stats(values)


def sections(text):
    result = defaultdict(list)
    title = ""
    for line in text.splitlines():
        if line and not line.startswith(" "):
            title = line
        elif line.strip():
            result[title].append(line.strip())
    return {key: " ".join(value) for key, value in result.items()}


def config(row):
    return "/".join(row[k] for k in ("language", "backend", "level", "sink"))


def collect(root):
    protocol = json.loads((root / "protocol.json").read_text())
    rows = read_csv(root / "runtime.csv")
    builds = read_csv(root / "compilation.csv")
    packed = [
        r for path in sorted(root.glob("packed/*/pack.csv")) for r in read_csv(path)
    ]
    manifest = json.loads((root / "compilation/0/manifest.json").read_text())
    versions = {r["language"]: r["version"].splitlines()[0] for r in manifest.values()}
    cases = list(dict.fromkeys(s["case"] for s in protocol["scenarios"]))
    configs = {}
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        identity = (row["run_directory"], row["trial_path"])
        if identity in seen:
            raise ValueError(f"Duplicate trial: {identity}")
        seen.add(identity)
        key = config(row)
        label = NAMES.get(row["language"], row["language"])
        if row["language"] == "baml":
            label += " / " + row["level"]
        label += (
            " · " + row["backend"]
            if row["backend"] not in (*LANGUAGES, protocol["backend"])
            else ""
        )
        configs[key] = {
            "label": label,
            "language": row["language"],
            "level": row["level"],
            "sink": row["sink"],
            "backend": row["backend"],
            "color": COLORS[row["language"]],
        }
        groups[(row["scenario"], key)].append(row)
    levels = ["off", "low", "medium", "high"]
    order = sorted(
        configs,
        key=lambda k: (
            LANGUAGES.index(configs[k]["language"]),
            levels.index(configs[k]["level"]) if configs[k]["level"] in levels else 0,
            k,
        ),
    )
    scenarios = []
    for scenario in protocol["scenarios"]:
        entries = {}
        for key in order:
            group = groups.get((scenario["name"], key), [])
            if not group:
                continue
            # Never merge unlike workloads/artifacts into one distribution.
            for field in ("case", "jobs", "warmup", "input_sha256", "artifact_sha256"):
                if len({r[field] for r in group}) != 1:
                    raise ValueError(f"Mixed {field} in {scenario['name']}/{key}")
            if group[0]["case"] != scenario["case"]:
                raise ValueError("Case identity does not match frozen protocol")
            entries[key] = {
                "failed": sum(r["status"] != "ok" for r in group),
                "observations": len(group),
                "coverage": sorted({r["coverage"] for r in group}),
                "metrics": {m[0]: metric_stats(group, m) for m in METRICS},
            }
        scenarios.append(scenario | {"groups": entries})
    by_case = {}
    for case in cases:
        doc = ROOT / "cases" / case / "README.txt"
        detail = sections(doc.read_text())
        compile_groups = []
        for lang in LANGUAGES:
            group = [r for r in builds if r["case"] == case and r["language"] == lang]
            good = [r for r in group if r["status"] == "ok"]
            if not group:
                continue
            compile_groups.append(
                {
                    "language": lang,
                    "label": NAMES[lang],
                    "color": COLORS[lang],
                    "kind": group[0]["artifact_kind"],
                    "wall": stats([float(r["process_wall_ns"]) / 1e9 for r in good]),
                    "cpu": stats([float(r["process_cpu_ns"]) / 1e9 for r in good]),
                    "rss": stats([float(r["peak_rss_bytes"]) / 1048576 for r in good]),
                    "bytes": stats(
                        [
                            float(r["artifact_bytes"])
                            for r in group
                            if r["artifact_bytes"]
                        ]
                    ),
                    "shared": stats(
                        [
                            float(r["shared_host_bytes"])
                            for r in group
                            if r["shared_host_bytes"]
                        ]
                    ),
                    "runtime": stats(
                        [
                            float(r["runtime_executable_bytes"])
                            for r in group
                            if r["runtime_executable_bytes"]
                        ]
                    ),
                    "failed": sum(
                        bool(r["status"]) and r["status"] != "ok" for r in group
                    ),
                }
            )
        pack = [r for r in packed if r["case"] == case and r["status"] == "ok"]
        by_case[case] = {
            "title": TITLES.get(case, case),
            "doc": detail,
            "build": compile_groups,
            "pack": {
                "failed": sum(r["status"] != "ok" for r in packed if r["case"] == case),
                "wall": stats([float(r["compile_wall_ns"]) / 1e9 for r in pack]),
                "cpu": stats([float(r["compile_cpu_ns"]) / 1e9 for r in pack]),
                "rss": stats(
                    [float(r["compile_peak_rss_bytes"]) / 1048576 for r in pack]
                ),
                "bytes": stats([float(r["packed_bytes"]) for r in pack]),
                "process": stats([float(r["process_wall_ns"]) / 1e6 for r in pack]),
            },
        }
    return {
        "run": root.name,
        "protocol": protocol,
        "versions": versions,
        "configs": configs,
        "order": order,
        "scenarios": scenarios,
        "cases": by_case,
        "collection": json.loads((root / "collection.json").read_text()),
        "coverage": json.loads((root / "coverage.json").read_text()),
        "metrics": {m[0]: {"label": m[1], "unit": m[2], "note": m[5]} for m in METRICS},
        "counts": {
            "trials": len(rows),
            "failed": sum(r["status"] != "ok" for r in rows),
            "builds": sum(r["status"] == "ok" for r in builds),
            "packs": sum(r["status"] == "ok" for r in packed),
        },
        "hashes": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "runtime.csv",
                "compilation.csv",
                "protocol.json",
                "producer.json",
            )
        },
    }


def download(path, label, filename=None):
    mime = "text/csv" if path.suffix == ".csv" else "text/plain"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<a download="{html.escape(filename or path.name)}" href="data:{mime};base64,{data}">{html.escape(label)}</a>'


def document(data, root):
    from plotly.offline import get_plotlyjs

    esc = html.escape
    parts = []
    for case, info in data["cases"].items():
        doc = info["doc"]
        scenarios = [s for s in data["scenarios"] if s["case"] == case]
        primary = {
            "01_array_traversal": "array-iterator",
            "07_function_calls": "calls",
        }.get(case, scenarios[0]["name"])
        options = "".join(
            f'<option value="{esc(s["name"])}" {"selected" if s["name"] == primary else ""}>{esc(s["name"])}</option>'
            for s in scenarios
        )
        default = "process_wall_ns" if case == "00_startup" else "execution_wall_ns"
        metrics = "".join(
            f'<option value="{key}" {"selected" if key == default else ""}>{esc(m["label"])}</option>'
            for key, m in data["metrics"].items()
        )
        refs = "".join(
            f'<li><a href="{esc(url)}">{esc(url.split("/baml_language/")[-1])}</a></li>'
            for url in doc.get("References", "").split()
        )
        boundaries = "".join(
            f"<dt>{esc(key)}</dt><dd>{esc(doc.get(key, ''))}</dd>"
            for key in ("Work", "Boundary", "Evidence", "Claim")
        )
        parts.append(f'''<section class="case-section" id="{case}" data-case="{case}">
          <div class="section-heading"><span class="case-id">{case.split("_")[0]}</span><h2>{esc(info["title"])}</h2></div>
          <p class="question">{esc(doc.get("Question", ""))}</p>
          <p class="compiler-path"><strong>BAML path</strong> {esc(doc.get("BAML path", ""))}</p>
          <div class="controls">
            <label>Workload<select class="scenario">{options}</select></label>
            <label>Metric<select class="metric">{metrics}</select></label>
            <label>Axis<select class="scale"><option value="log">Logarithmic</option><option value="linear">Linear</option></select></label>
          </div>
          <p class="workload-note"></p><p class="metric-note"></p>
          <div class="case-chart" role="img" aria-label="{esc(info["title"])} measurements; exact values in the table below"></div>
          <p class="chart-key">Small points: individual trials. Large diamond: median. Line: observed minimum–maximum; not a confidence interval.</p>
          <details class="values"><summary>Exact values and coverage</summary><div class="table-scroll"><table class="value-table"></table></div></details>
          <details><summary>What this case establishes · source references</summary><dl>{boundaries}</dl><ul class="references">{refs}</ul></details>
          <details><summary>Compile time and artifact size for this case</summary><div class="case-build"></div></details>
        </section>''')
    versions = "".join(
        f"<div><dt>{NAMES[lang]}</dt><dd>{esc(version)}</dd></div>"
        for lang, version in data["versions"].items()
    )
    downloads = "".join(
        download(root / name, label)
        for name, label in (
            ("runtime.csv", "Runtime CSV"),
            ("compilation.csv", "Compilation CSV"),
            ("summary.csv", "Summary CSV"),
            ("protocol.json", "Frozen protocol"),
            ("coverage.json", "GC coverage"),
            ("producer.json", "Producer hashes"),
            ("BASELINE.txt", "Text report"),
        )
    )
    downloads += "".join(
        download(
            path,
            f"BAML pack repeat {int(path.parent.name) + 1}",
            f"pack-repeat-{int(path.parent.name) + 1}.csv",
        )
        for path in sorted(root.glob("packed/*/pack.csv"))
    )
    hashes = "".join(
        f"<dt>{esc(name)}</dt><dd><code>{value}</code></dd>"
        for name, value in data["hashes"].items()
    )
    # Always-readable fallback: all runtime medians, even with JavaScript disabled.
    table = "<table><caption>Execution wall time, median µs/job</caption><thead><tr><th>Scenario</th>"
    local_order = [
        k
        for k in data["order"]
        if data["configs"][k]["sink"] != "none"
        or data["configs"][k]["language"] != "baml"
    ]
    table += (
        "".join(f"<th>{esc(data['configs'][k]['label'])}</th>" for k in local_order)
        + "</tr></thead><tbody>"
    )
    for scenario in data["scenarios"]:
        table += f"<tr><th>{esc(scenario['name'])}</th>"
        for key in local_order:
            matching = next(
                (
                    k
                    for k in scenario["groups"]
                    if data["configs"][k]["label"] == data["configs"][key]["label"]
                ),
                key,
            )
            value = (
                scenario["groups"]
                .get(matching, {})
                .get("metrics", {})
                .get("execution_wall_ns")
            )
            table += (
                f"<td>{value['median']:,.3f}</td>" if value else "<td>Not measured</td>"
            )
        table += "</tr>"
    table += "</tbody></table>"
    replacements = {
        "@@CASES@@": "\n".join(parts),
        "@@VERSIONS@@": versions,
        "@@DOWNLOADS@@": downloads,
        "@@HASHES@@": hashes,
        "@@FALLBACK@@": table,
        "@@COUNTS@@": f"{data['counts']['trials']:,} runtime trials · {data['counts']['failed']} failed · {data['counts']['builds']} compiler observations · {data['counts']['packs']} pack/invocation pairs",
        "@@RUN@@": esc(data["run"]),
        "@@CASELINKS@@": "".join(
            f'<a href="#{case}">{esc(info["title"])}</a>'
            for case, info in data["cases"].items()
        ),
        "@@DATA@@": json.dumps(data, separators=(",", ":"), allow_nan=False).replace(
            "<", "\\u003c"
        ),
        "@@PLOTLY@@": get_plotlyjs(),
    }
    template = (ROOT / "machinery/report.html").read_text()
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.collection.resolve()
    output = args.output or root / "index.html"
    data = collect(root)
    output.write_text(document(data, root))
    print(
        f"{output}: {output.stat().st_size:,} bytes; {data['counts']['trials']:,} trials"
    )


if __name__ == "__main__":
    main()
