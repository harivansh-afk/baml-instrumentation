# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.10.6"]
# ///
"""Render static SVG bar charts from separately identified immutable collections."""

import argparse
import base64
import csv
import hashlib
import html
import json
import math
import re
from collections import defaultdict
from pathlib import Path
import statistics
import tomllib

from report import versions_for_cases

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
    "08_stateful_workflow": "Stateful workflow",
    "09_json_hello": "JSON hello world",
    "10_quick_sort": "Three-way quicksort",
    "11_generate_sort": "Generate and sort",
}
# Key, label, unit, divisor, normalize by jobs, scope note.
METRICS = [
    (
        "execution_wall_ns",
        "Execution wall / job",
        "µs / job",
        1000,
        True,
        "Timed batch ÷ jobs. Includes adapter entry, allocation/reclamation and result serialization. Each observation is a process batch average, not a per-call latency sample.",
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
    cases = list(dict.fromkeys(s["case"] for s in protocol["scenarios"]))
    versions = versions_for_cases(manifest, cases)
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
        doc = root / "report-docs" / (case + ".txt")
        if not doc.exists():
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
            "doc_sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
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


ESC = html.escape
LEVEL_COLORS = dict(off="#254e70", low="#365c7b", medium="#587c99", high="#7897b0")


def number(value, digits=3):
    if value is None:
        return "Unavailable"
    if value == 0:
        return "0"
    return format(value, f",.{digits}g")


def table(headers, rows, caption=""):
    content = '<div class="table-scroll" tabindex="0"><table>'
    if caption:
        content += f"<caption>{ESC(caption)}</caption>"
    content += (
        "<thead><tr>"
        + "".join(f'<th scope="col">{ESC(str(x))}</th>' for x in headers)
        + "</tr></thead><tbody>"
    )
    for row in rows:
        content += (
            "<tr>"
            + "".join(
                f"<{'th scope="row"' if i == 0 else 'td'}>{ESC(str(x))}</{'th' if i == 0 else 'td'}>"
                for i, x in enumerate(row)
            )
            + "</tr>"
        )
    return content + "</tbody></table></div>"


def bar(entries, title, unit, chart_id, directory, note=""):
    """All bars start at zero; whiskers are observed ranges, never confidence bounds."""
    from io import StringIO
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 12,
            "svg.fonttype": "none",
            "svg.hashsalt": "instrumentation-static-v1",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
        }
    )
    entries = [e for e in entries if e[1] is not None]
    if not entries:
        return ""
    labels = [e[0] for e in entries]
    values = [e[1]["median"] for e in entries]
    maxvalue = max(e[1]["max"] for e in entries) or 1
    fig, ax = plt.subplots(
        figsize=(7.5, max(2.1, 0.40 * len(entries) + 0.7)), layout="constrained"
    )
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    pos = list(range(len(entries)))
    ax.barh(pos, values, color=[e[2] for e in entries], height=0.56, zorder=2)
    ax.errorbar(
        values,
        pos,
        xerr=[
            [e[1]["median"] - e[1]["min"] for e in entries],
            [e[1]["max"] - e[1]["median"] for e in entries],
        ],
        fmt="none",
        ecolor="#192d3d",
        capsize=2,
        elinewidth=0.8,
        zorder=3,
    )
    ax.set_yticks(pos, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, maxvalue * 1.34)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.tick_params(axis="x", labelsize=11)
    # A separate scientific-offset label collides with the right-aligned unit.
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel(unit, loc="right")
    ax.grid(axis="x", color="#e6e9ed", linewidth=0.6, zorder=0)
    for i, e in enumerate(entries):
        ax.text(
            e[1]["max"] + maxvalue * 0.025,
            i,
            number(e[1]["median"]),
            va="center",
            fontsize=11,
            color="#172b3c",
        )
    raw = StringIO()
    fig.savefig(
        raw,
        format="svg",
        metadata={"Date": None, "Creator": "instrumentation / matplotlib 3.10.6"},
    )
    plt.close(fig)
    svg = raw.getvalue()
    svg = svg[svg.index("<svg") :]
    svg = svg.replace(
        "font-family: 'DejaVu Sans'", "font-family: 'DejaVu Sans', Arial, sans-serif"
    )
    # Every inline SVG needs a separate ID namespace, including clip paths.
    ids = re.findall(r'id="([^"]+)"', svg)
    for identity in ids:
        unique = chart_id + "-" + identity
        svg = svg.replace('id="' + identity + '"', 'id="' + unique + '"')
        svg = svg.replace("url(#" + identity + ")", "url(#" + unique + ")")
        svg = svg.replace('href="#' + identity + '"', 'href="#' + unique + '"')
    svg = svg.replace(
        "<svg ", f'<svg role="img" aria-labelledby="{chart_id}-title" ', 1
    )
    start = svg.index(">") + 1
    svg = (
        svg[:start]
        + f'<title id="{chart_id}-title">{ESC(title)}. Bars show medians; whiskers show observed minimum and maximum. Unit: {ESC(unit)}.</title>'
        + svg[start:]
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (chart_id + ".svg")).write_text(svg)
    rows = [
        (
            e[0],
            number(e[1]["median"], 9),
            number(e[1]["min"], 9),
            number(e[1]["max"], 9),
            e[1]["n"],
        )
        for e in entries
    ]
    return (
        f'<figure id="{chart_id}"><figcaption>{ESC(title)}</figcaption><div class="plot-scroll" tabindex="0">{svg}</div><p class="chart-note">{ESC(note)}</p><details><summary>Values · {ESC(unit)}</summary>'
        + table(["Runtime", "Median", "Minimum", "Maximum", "n"], rows)
        + "</details></figure>"
    )


def runtime_charts(data, scenario, directory):
    groups = scenario["groups"]
    prefix = data["run"] + "-" + scenario["name"]
    out = []

    def entries(metric, scope):
        result = []
        for key in data["order"]:
            if key not in groups:
                continue
            config = data["configs"][key]
            language = config["language"]
            if (
                scope == "references"
                and language == "baml"
                and config["level"] != "off"
            ):
                continue
            if scope == "btel" and language != "baml":
                continue
            label = config["label"]
            if config["sink"] == "none":
                label += " · no sink"
            color = (
                LEVEL_COLORS.get(config["level"], config["color"])
                if scope == "btel"
                else config["color"]
            )
            result.append((label, groups[key]["metrics"][metric], color))
        return result

    charts = [
        ("execution_wall_ns", "references"),
        ("execution_wall_ns", "btel"),
        ("execution_cpu_ns", "references"),
        ("peak_rss_bytes", "references"),
        ("peak_rss_bytes", "btel"),
        ("process_wall_ns", "references"),
        ("drain_ns", "btel"),
        ("recording_bytes", "btel"),
    ]
    for metric, scope in charts:
        info = data["metrics"][metric]
        label = (
            ("BTEL modes" if scope == "btel" else "Language comparison")
            + " · "
            + info["label"]
        )
        out.append(
            bar(
                entries(metric, scope),
                label,
                info["unit"],
                prefix + "-" + metric + "-" + scope,
                directory,
                info["note"],
            )
        )
    for metric in ("execution_wall_ns", "execution_cpu_ns"):
        values = entries(metric, "references")
        references = [e for e in values if not e[0].startswith("BAML") and e[1]]
        baml = next((e[1] for e in values if e[0].startswith("BAML")), None)
        if (
            references
            and baml
            and baml["median"] > 4 * max(e[1]["median"] for e in references)
        ):
            info = data["metrics"][metric]
            out.append(
                bar(
                    references,
                    "Reference runtimes · " + info["label"],
                    info["unit"],
                    prefix + "-" + metric + "-reference-zoom",
                    directory,
                    "Additional linear scale for the reference runtimes. The full comparison including BAML appears above.",
                )
            )
    # Counters with different meanings are a table, not a shared GC ranking.
    counters = []
    for key in data["order"]:
        if key not in groups:
            continue
        group = groups[key]
        cells = [
            data["configs"][key]["label"],
            str(group["observations"]),
            str(group["failed"]),
        ]
        for metric in (
            "gc_execution",
            "allocated_bytes",
            "heap_alloc_bytes",
            "gc_pause_ns",
        ):
            value = group["metrics"][metric]
            cells.append(
                f"{number(value['median'])} [{number(value['min'])}, {number(value['max'])}]"
                if value
                else "Unavailable"
                if data["configs"][key]["language"] != "rust"
                or metric != "gc_execution"
                else "Not applicable"
            )
        counters.append(cells)
    detail = table(
        [
            "Runtime",
            "Trials",
            "Failed",
            "GC count",
            "Go allocated MiB",
            "Go final heap MiB",
            "Go pause ms",
        ],
        counters,
        "Median [minimum, maximum]. BAML full collections, Go cycles and Python cyclic collections differ. Node/Bun GC counters unavailable.",
    )
    required = scenario.get("requires_gc", {})
    if required:
        detail += (
            "<p>Required execution collections per trial: "
            + ESC(", ".join(f"{NAMES[k]} ≥ {v}" for k, v in required.items()))
            + ". See the downloadable coverage evidence.</p>"
        )
    phases = []
    for key in data["order"]:
        if key not in groups:
            continue
        row = [data["configs"][key]["label"]]
        for metric in ("process_cpu_ns", "launch_to_ready_ns"):
            value = groups[key]["metrics"][metric]
            row.append(
                f"{number(value['median'])} [{number(value['min'])}, {number(value['max'])}]"
                if value
                else "Unavailable"
            )
        phases.append(row)
    detail += table(
        ["Runtime", "Whole-process CPU ms", "Launch-to-ready ms"],
        phases,
        "Median [minimum, maximum]. Whole-process phases are not subtracted from execution.",
    )
    if scenario["case"] == "08_stateful_workflow":
        amortized = []
        for label, value, color in entries("execution_wall_ns", "references"):
            if value:
                divisor = scenario["batches"] * 1000
                converted = {
                    k: v / divisor
                    if k in ("min", "median", "max")
                    else [x / divisor for x in v]
                    if k == "values"
                    else v
                    for k, v in value.items()
                }
                amortized.append((label, converted, color))
        out.insert(
            0,
            bar(
                amortized,
                "Amortized workflow wall per request",
                "ms / request",
                prefix + "-per-request",
                directory,
                "Whole timed batch divided by requests, including invalid inputs. This is an average cost, not an individually timed latency or percentile.",
            ),
        )
    parameters = " · ".join(
        f"{key.replace('_', ' ')}: {scenario[key]}"
        for key in (
            "size",
            "variant",
            "batches",
            "retain",
            "fanout",
            "delay_ms",
            "jobs",
            "warmup",
        )
        if key in scenario
    )
    return (
        f'<article id="{prefix}"><h4>{ESC(scenario["name"])}</h4><p>{ESC(scenario["claim"])}</p><p class="parameters">{ESC(parameters)}</p><div class="chart-grid">'
        + "".join(out)
        + "</div>"
        + detail
        + "</article>"
    )


def build_charts(data, case, info, directory):
    prefix = data["run"] + "-" + case + "-build"
    groups = info["build"]
    out = []

    def values(field, languages, divisor=1):
        result = []
        for g in groups:
            if g["language"] not in languages or not g[field]:
                continue
            value = {
                k: (
                    v / divisor
                    if k in ("min", "median", "max")
                    else [x / divisor for x in v]
                    if k == "values"
                    else v
                )
                for k, v in g[field].items()
            }
            result.append((g["label"], value, g["color"]))
        return result

    for key, title, unit, langs, divisor, note in [
        (
            "wall",
            "Native compile wall",
            "s",
            ("rust", "go"),
            1,
            "Empty application and dependency compilation caches; fetching excluded. Filesystem caches uncontrolled.",
        ),
        (
            "wall",
            "BAML source → bytecode wall",
            "ms",
            ("baml",),
            0.001,
            "Different output target from native compilation; shared compiler host is already built.",
        ),
        (
            "cpu",
            "Native compile CPU",
            "s",
            ("rust", "go"),
            1,
            "Whole compiler process tree CPU, including dependency compilation.",
        ),
        (
            "rss",
            "Compiler peak RSS",
            "MiB",
            ("baml", "rust", "go"),
            1,
            "High-water mark reported by wait4; not the simultaneous sum of compiler descendants.",
        ),
        (
            "bytes",
            "Native executable size",
            "MiB",
            ("rust", "go"),
            1048576,
            "Includes workload and measurement adapter; excludes dynamic system libraries.",
        ),
        (
            "bytes",
            "BAML bytecode size",
            "KiB",
            ("baml",),
            1024,
            "Shared BAML measurement host excluded; full packed size listed separately.",
        ),
        (
            "bytes",
            "Script + adapter source size",
            "KiB",
            ("python", "node", "bun"),
            1024,
            "Shared interpreters and dependencies excluded; not equivalent to a native executable.",
        ),
    ]:
        out.append(
            bar(
                values(key, langs, divisor),
                title,
                unit,
                prefix + "-" + key + "-" + langs[0],
                directory,
                note,
            )
        )
    pack = info["pack"]
    rows = []
    for label, key, divisor, unit in [
        ("Published BAML pack wall", "wall", 1, "s"),
        ("Published BAML packed executable", "bytes", 1048576, "MiB"),
        ("Packed invocation, small validation fixture", "process", 1, "ms"),
    ]:
        if pack[key]:
            rows.append(
                (label, number(pack[key]["median"] / divisor), unit, pack[key]["n"])
            )
    for group in groups:
        for field, label in [
            ("shared", "shared measurement host"),
            ("runtime", "interpreter executable"),
        ]:
            if group[field]:
                rows.append(
                    (
                        group["label"] + " " + label,
                        number(group[field]["median"] / 1048576),
                        "MiB",
                        group[field]["n"],
                    )
                )
    return (
        '<h4>Compilation and artifact sizes</h4><p>These outputs have different deployment scopes. Missing compilation for Python, Node and Bun means no separate build step was measured.</p><div class="chart-grid">'
        + "".join(out)
        + "</div>"
        + table(["Artifact or phase", "Median", "Unit", "n"], rows)
    )


def overview(data):
    keys = [
        k
        for k in data["order"]
        if data["configs"][k]["sink"] != "none"
        and (
            data["configs"][k]["language"] != "baml"
            or data["configs"][k]["level"] == "off"
        )
    ]
    rows = []
    for scenario in data["scenarios"]:
        if scenario.get("sink") == "none":
            continue
        row = [scenario["name"]]
        for key in keys:
            metric = (
                scenario["groups"]
                .get(key, {})
                .get("metrics", {})
                .get("execution_wall_ns")
            )
            row.append(number(metric["median"]) if metric else "Unavailable")
        rows.append(row)
    return table(
        ["Workload"] + [data["configs"][k]["label"] for k in keys],
        rows,
        "Median execution µs/job. Each row is a different workload; there is no combined language score.",
    )


def sorting_comparison(data, directory):
    pairs = []
    for language in LANGUAGES:
        entries = []
        for variant in ("random", "sorted", "reverse", "duplicates"):
            for algorithm, color in [("merge", "#254e70"), ("quick", "#c27738")]:
                scenario = next(
                    (
                        s
                        for s in data["scenarios"]
                        if s["name"] == algorithm + "-" + variant
                    ),
                    None,
                )
                if scenario is None:
                    continue
                key = next(
                    (
                        k
                        for k in scenario["groups"]
                        if data["configs"][k]["language"] == language
                        and (language != "baml" or data["configs"][k]["level"] == "off")
                    ),
                    None,
                )
                if key:
                    entries.append(
                        (
                            variant + " · " + algorithm,
                            scenario["groups"][key]["metrics"]["execution_wall_ns"],
                            color,
                        )
                    )
        if entries:
            pairs.append(
                bar(
                    entries,
                    NAMES[language] + " · merge vs quicksort",
                    "µs / job",
                    data["run"] + "-sort-pair-" + language,
                    directory,
                    "1,024 identical prepared integers; copy, sort and serialize. Separate scenario blocks, not paired trials. BAML uses telemetry off; each runtime has its own linear axis.",
                )
            )
    return (
        '<section><h3>Two handwritten sorting algorithms</h3><div class="chart-grid">'
        + "".join(pairs)
        + "</div></section>"
        if pairs
        else ""
    )


def collection_document(data, root, directory):
    parts = []
    for case, info in data["cases"].items():
        doc = info["doc"]
        prefix = data["run"] + "-" + case
        details = "".join(
            f"<dt>{ESC(k)}</dt><dd>{ESC(doc.get(k, ''))}</dd>"
            for k in ("Work", "Boundary", "BAML path", "Evidence", "Claim")
        )
        refs = "".join(
            f'<li><a href="{ESC(url)}">{ESC(url.split("/baml_language/")[-1])}</a></li>'
            for url in doc.get("References", "").split()
        )
        scenarios = "".join(
            runtime_charts(data, s, directory)
            for s in data["scenarios"]
            if s["case"] == case
        )
        parts.append(
            f'<section id="{prefix}" class="case"><h3>{ESC(info["title"])}</h3><p>{ESC(doc.get("Question", ""))}</p><details><summary>Work, measurement boundary and compiler path</summary><dl>{details}</dl><ul class="references">{refs}</ul></details>'
            + scenarios
            + build_charts(data, case, info, directory)
            + "</section>"
        )
    downloads = "".join(
        download(root / name, label, data["run"] + "-" + name)
        for name, label in [
            ("runtime.csv", "Runtime CSV"),
            ("compilation.csv", "Compilation CSV"),
            ("summary.csv", "Summary CSV"),
            ("protocol.json", "Frozen protocol"),
            ("coverage.json", "GC coverage"),
            ("producer.json", "Producer hashes"),
            ("BASELINE.txt", "Text report"),
        ]
    )
    downloads += "".join(
        download(
            p,
            "BAML pack " + p.parent.name,
            data["run"] + "-pack-" + p.parent.name + ".csv",
        )
        for p in sorted(root.glob("packed/*/pack.csv"))
    )
    versions = " · ".join(NAMES[k] + " " + v for k, v in data["versions"].items())
    count = data["counts"]
    coverage = data["coverage"]
    bad = [r for r in coverage if r.get("gc_requirement_passed") is False]
    return (
        f'<section id="{ESC(data["run"])}"><h2>{ESC(data["run"])}</h2><p>{count["trials"]:,} runtime trials · {count["failed"]} failed · {count["builds"]} compiler observations · {count["packs"]} pack/invocation pairs · {len(bad)} GC coverage failures.</p><p>CPUs {ESC(data["protocol"]["cpus"])}; {data["protocol"]["workers"]} workers where supported. Rust uses Tokio current_thread; Python, Node and Bun use one event loop.</p><p class="versions">{ESC(versions)}</p><div class="downloads">{downloads}</div>'
        + overview(data)
        + sorting_comparison(data, directory)
        + "".join(parts)
        + "</section>"
    )


def http_rows(root):
    rows = read_csv(root / "http.csv")
    seen = set()
    groups = defaultdict(list)
    for row in rows:
        if row["trial_path"] in seen:
            raise ValueError("Duplicate HTTP trial: " + row["trial_path"])
        seen.add(row["trial_path"])
        groups[(row["scenario"], row["language"], row["level"])].append(row)
    for key, group in groups.items():
        for field in ("artifact_sha256", "input_sha256", "requests", "offered_rate"):
            values = {
                row.get(field)
                for row in group
                if row["status"] in ("ok", "request_failure")
            }
            if len(values) > 1:
                raise ValueError(f"Mixed HTTP {field}: {key}")
    return rows


def http_metric_eligible(row, metric):
    if metric in ("client_lag_p99_ns", "failed"):
        # Diagnostics must show the observations that caused an exclusion.
        return row.get(metric) not in (None, "")
    return (
        row["status"] in ("ok", "request_failure")
        and row.get("client_schedule_valid") == "True"
    )


def http_document(root, build_root, directory):
    rows = http_rows(root)
    protocol = json.loads((root / "protocol.json").read_text())
    artifacts = json.loads((build_root / "artifacts.json").read_text())
    cargo = tomllib.loads(
        (build_root / "producer/machinery/http/Cargo.toml").read_text()
    )
    axum = str(cargo["dependencies"]["axum"]).lstrip("=")
    aiohttp = next(
        line.split("==", 1)[1]
        for line in (build_root / "producer/machinery/http/requirements.in")
        .read_text()
        .splitlines()
        if line.startswith("aiohttp==")
    )
    servers = ", ".join(map(str, protocol["server_cpus"]))
    clients = protocol["client_cpus"]
    versions = " · ".join(
        NAMES[k] + " " + str(v["version"]) for k, v in artifacts.items()
    )
    parts = []
    configs = [("baml", x) for x in ("off", "low", "medium", "high")] + [
        (x, "not_applicable") for x in LANGUAGES if x != "baml"
    ]
    metrics = [
        (
            "throughput",
            "Completed throughput",
            "requests / s",
            1,
            "Correct successful responses divided by max(planned load duration, time to last response or request deadline). This is achieved load, not maximum capacity.",
        ),
        (
            "failed",
            "Failed requests per process trial",
            "requests",
            1,
            "Diagnostic includes excluded trials. Median and observed range per trial; the table gives totals. A zero median does not mean every request succeeded.",
        ),
        (
            "latency_p50_ns",
            "Successful-response latency p50",
            "ms",
            1e6,
            "Scheduled arrival to received body; includes driver delay and queueing. Each bar summarizes one percentile per process trial.",
        ),
        (
            "latency_p95_ns",
            "Successful-response latency p95",
            "ms",
            1e6,
            "Nearest-rank percentile within each trial; bars show median of those trial percentiles, not a pooled percentile.",
        ),
        (
            "latency_p99_ns",
            "Successful-response latency p99",
            "ms",
            1e6,
            "Scheduled arrival to response body; includes client scheduling delay. Failures are shown separately and have no successful-response percentile.",
        ),
        (
            "service_p95_ns",
            "Dispatch-to-body p95",
            "ms",
            1e6,
            "Includes connection setup, transfer and server time; excludes delay between scheduled arrival and dispatch.",
        ),
        (
            "client_lag_p99_ns",
            "Client dispatch delay p99",
            "ms",
            1e6,
            f"Diagnostic includes excluded trials. Actual dispatch minus scheduled arrival; the frozen validity limit is {protocol['max_client_lag_ms']} ms.",
        ),
        (
            "process_cpu_ns",
            "Whole server process CPU",
            "ms",
            1e6,
            "wait4 CPU includes startup, correctness warmup, offered load, metadata and shutdown. Load client CPU is excluded.",
        ),
        (
            "peak_rss_bytes",
            "Peak server RSS",
            "MiB",
            1048576,
            "wait4 peak of the server process; load client memory excluded.",
        ),
        (
            "launch_to_ready_ns",
            "Launch to server ready",
            "ms",
            1e6,
            "Parent-observed launch to the server's bound-listener marker; includes observer and pipe overhead.",
        ),
        (
            "gc_service_lifetime",
            "BAML service-lifetime GC",
            "full collections",
            1,
            "Includes binding, warmup, load and service shutdown before telemetry drain. Other HTTP runtimes expose no matched counter here; collection count is not pause duration.",
        ),
        (
            "recording_bytes",
            "BTEL recording size",
            "MiB",
            1048576,
            "Includes the service lifetime and warmup requests.",
        ),
        (
            "drain_ns",
            "BAML telemetry drain",
            "ms",
            1e6,
            "Measured after the BAML service exits; server shutdown precedes this phase.",
        ),
    ]
    for scenario in protocol["scenarios"]:
        selected = [r for r in rows if r["scenario"] == scenario["name"]]
        charts = []
        for key, title, unit, divisor, note in metrics:
            entries = []
            for lang, level in configs:
                group = [
                    r
                    for r in selected
                    if r["language"] == lang
                    and r["level"] == level
                    and http_metric_eligible(r, key)
                    and r.get(key) not in ("", None)
                ]
                if not group:
                    continue
                entries.append(
                    (
                        NAMES[lang] + (" / " + level if lang == "baml" else ""),
                        stats([float(r[key]) / divisor for r in group]),
                        LEVEL_COLORS[level] if lang == "baml" else COLORS[lang],
                    )
                )
            charts.append(
                bar(
                    entries,
                    title,
                    unit,
                    root.name + "-" + scenario["name"] + "-" + key,
                    directory,
                    note,
                )
            )
        failures = []
        issues = []
        for lang, level in configs:
            group = [
                r for r in selected if r["language"] == lang and r["level"] == level
            ]
            label = NAMES[lang] + (" / " + level if lang == "baml" else "")
            invalid = sum(r["status"] not in ("ok", "request_failure") for r in group)
            failed = sum(int(r.get("failed") or 0) for r in group)
            schedules = sum(r.get("client_schedule_valid") == "False" for r in group)
            eligible = sum(http_metric_eligible(r, "throughput") for r in group)
            failures.append((label, len(group), eligible, invalid, failed, schedules))
            if invalid or failed or schedules:
                details = []
                if invalid:
                    details.append(f"{invalid} invalid measurement trial(s)")
                if failed:
                    details.append(f"{failed} failed request(s)")
                if schedules:
                    details.append(f"{schedules} invalid driver schedule(s)")
                issues.append(label + ": " + ", ".join(details))
        notice = (
            '<p class="scope">' + ESC("; ".join(issues)) + ".</p>" if issues else ""
        )
        payload = (
            str(scenario.get("size", 64)) + " input records per POST."
            if scenario["path"] == "/aggregate"
            else "Fixed JSON hello-world body."
        )
        parts.append(
            f'<article id="{root.name}-{scenario["name"]}"><h3>{ESC(scenario["name"])}</h3><p>{scenario["rate"]} scheduled requests/s for {protocol["duration_s"]} s per fresh server. {protocol["warmup_requests"]} sequential warmup requests precede load. {ESC(payload)}</p>'
            + notice
            + '<div class="chart-grid">'
            + "".join(charts)
            + "</div>"
            + table(
                [
                    "Runtime",
                    "Process trials",
                    "Eligible for performance",
                    "Invalid measurements",
                    "Failed requests",
                    "Schedule violations",
                ],
                failures,
            )
            + "</article>"
        )
    buildrows = read_csv(build_root / "compilation.csv")
    buildparts = []
    for key, title, unit, divisor in [
        ("process_wall_ns", "HTTP compiler wall", "s", 1e9),
        ("process_cpu_ns", "HTTP compiler CPU", "s", 1e9),
        ("peak_rss_bytes", "HTTP compiler peak RSS", "MiB", 1048576),
    ]:
        entries = []
        for lang in ("baml", "rust", "go"):
            values = [
                float(r[key]) / divisor
                for r in buildrows
                if r["language"] == lang and r["status"] == "ok"
            ]
            entries.append((NAMES[lang], stats(values), COLORS[lang]))
        buildparts.append(
            bar(
                entries,
                title,
                unit,
                root.name + "-build-" + key,
                directory,
                "BAML compiles source to bytecode; Rust/Go compile complete native services with empty dependency compilation caches. Targets differ.",
            )
        )
    for label, languages, divisor, unit in [
        ("HTTP native executable size", ("rust", "go"), 1048576, "MiB"),
        ("HTTP BAML bytecode size", ("baml",), 1024, "KiB"),
        ("HTTP script source size", ("python", "node", "bun"), 1024, "KiB"),
    ]:
        entries = []
        for lang in languages:
            values = [
                float(r["artifact_bytes"]) / divisor
                for r in buildrows
                if r["language"] == lang
            ]
            entries.append((NAMES[lang], stats(values), COLORS[lang]))
        buildparts.append(
            bar(
                entries,
                label,
                unit,
                root.name + "-artifact-" + languages[0],
                directory,
                "Artifact scopes differ; shared hosts, interpreters, dynamic libraries and script dependencies are not included in these bars.",
            )
        )
    artifacts = json.loads((build_root / "artifacts.json").read_text())
    sizes = [
        (
            NAMES[k],
            v["artifact_kind"],
            f"{v['artifact_bytes']:,}",
            f"{v.get('shared_host_bytes', v.get('runtime_executable_bytes', 0)):,}"
            if k not in ("go", "rust")
            else "Not inventoried",
        )
        for k, v in artifacts.items()
    ]
    downloads = "".join(
        download(root / name, label, root.name + "-" + name)
        for name, label in [
            ("http.csv", "HTTP process CSV"),
            ("protocol.json", "HTTP protocol"),
            ("producer.json", "HTTP producer hashes"),
        ]
    ) + download(
        build_root / "compilation.csv",
        "HTTP compilation CSV",
        root.name + "-compilation.csv",
    )
    if (root / "FINDINGS.txt").exists():
        downloads += download(
            root / "FINDINGS.txt",
            "Failures and exclusions",
            root.name + "-FINDINGS.txt",
        )
    doc_path = root / "report-docs/06_http_service.txt"
    if not doc_path.exists():
        doc_path = ROOT / "cases/06_http_service/README.txt"
    doc = sections(doc_path.read_text())
    boundaries = "".join(
        f"<dt>{ESC(k)}</dt><dd>{ESC(doc.get(k, ''))}</dd>"
        for k in ("Work", "Boundary", "BAML path", "Evidence", "Claim")
    )
    refs = "".join(
        f'<li><a href="{ESC(url)}">{ESC(url)}</a></li>'
        for url in doc.get("References", "").split()
    )
    explanation = f'<details><summary>Service boundary, compiler path and references</summary><dl>{boundaries}</dl><ul class="references">{refs}</ul></details>'
    request_failures = sum(int(row.get("failed") or 0) for row in rows)
    failure_trials = sum(row["status"] == "request_failure" for row in rows)
    invalid_trials = sum(row["status"] not in ("ok", "request_failure") for row in rows)
    schedule_failures = sum(row.get("client_schedule_valid") == "False" for row in rows)
    return (
        f'<section id="http"><h2>HTTP services</h2><p class="scope"><strong>{request_failures} failed requests across {failure_trials} process trials.</strong> {invalid_trials} invalid measurement trials and {schedule_failures} driver-schedule violations are excluded from performance bars. All raw observations are retained. A request timeout does not by itself identify a server, client, or kernel cause.</p><p>Loopback HTTP/1.1, one connection per request, no TLS or compression. Server CPUs {ESC(servers)}; client CPUs {ESC(clients)}. BAML native HTTP, Rust axum {ESC(axum)}, Go net/http, Python aiohttp {ESC(aiohttp)}, and Node/Bun node:http. BAML and Go use two configured workers. Rust, Python, Node and Bun use one event loop. These are complete stack comparisons; they do not isolate language execution.</p><p>{protocol["trials"]} independent processes per configuration and load. Bars retain completed, schedule-valid trials even when requests fail. Throughput counts only correct responses, and its duration includes request deadlines. Response percentiles use successful responses only; read them together with failure counts. Invalid driver schedules and harness failures remain in the tables. Request deadlines are {protocol["request_deadline_s"]} s; errors remain in the data. No maximum-capacity or production-network claim. Shared-host scheduling remains a confounder.</p><p class="versions">{ESC(versions)}</p><div class="downloads">{downloads}</div>'
        + explanation
        + "".join(parts)
        + '<h3>HTTP compilation and artifact scopes</h3><div class="chart-grid">'
        + "".join(buildparts)
        + "</div>"
        + table(
            [
                "Runtime",
                "Artifact scope",
                "Artifact bytes",
                "Shared host/interpreter bytes",
            ],
            sizes,
        )
        + "</section>"
    )


def document(collections, roots, directory, http_root=None, http_build=None):
    if isinstance(collections, dict):
        collections = [collections]
        roots = [roots]
    total = sum(d["counts"]["trials"] for d in collections)
    nav = "".join(
        f'<a href="#{d["run"]}-{case}">{ESC(info["title"])} <small>{ESC(d["run"])}</small></a>'
        for d in collections
        for case, info in d["cases"].items()
    )
    if http_root:
        nav += '<a href="#http">HTTP services</a>'
    body = "".join(
        collection_document(data, root, directory)
        for data, root in zip(collections, roots)
    )
    if http_root:
        body += http_document(http_root, http_build, directory)
    export = base64.b64encode(
        json.dumps(
            {
                "schema": 1,
                "batch_collections": collections,
                "http": {
                    "protocol": json.loads((http_root / "protocol.json").read_text()),
                    "process_rows": read_csv(http_root / "http.csv"),
                    "build_rows": read_csv(http_build / "compilation.csv"),
                }
                if http_root
                else None,
            },
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).decode()
    return (
        (ROOT / "machinery/report.html")
        .read_text()
        .replace("@@NAV@@", nav)
        .replace("@@COUNT@@", f"{total:,}")
        .replace("@@BODY@@", body)
        .replace("@@DATA@@", export)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collections", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--http", type=Path)
    parser.add_argument("--http-build", type=Path)
    args = parser.parse_args()
    roots = [p.resolve() for p in args.collections]
    output = args.output or roots[0] / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    if bool(args.http) != bool(args.http_build):
        parser.error("--http and --http-build must be provided together")
    # Freeze reporting prose separately from immutable measurement producers.
    for root in roots + ([args.http] if args.http else []):
        cases = (
            ["06_http_service"]
            if root == args.http
            else list(
                dict.fromkeys(
                    s["case"]
                    for s in json.loads((root / "protocol.json").read_text())[
                        "scenarios"
                    ]
                )
            )
        )
        snapshot = root / "report-docs"
        snapshot.mkdir(exist_ok=True)
        for case in cases:
            destination = snapshot / (case + ".txt")
            if not destination.exists():
                destination.write_bytes(
                    (ROOT / "cases" / case / "README.txt").read_bytes()
                )
        hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in snapshot.glob("*.txt")
        }
        (snapshot / "hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    data = [collect(p) for p in roots]
    directory = output.parent / "charts"
    output.write_text(document(data, roots, directory, args.http, args.http_build))
    print(
        f"{output}: {output.stat().st_size:,} bytes; {len(list(directory.glob('*.svg')))} static SVG charts"
    )


if __name__ == "__main__":
    main()
