# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.10.6"]
# ///
"""Render the frozen backend reference as static charts and an Excalidraw section."""

import base64
import csv
import hashlib
import html
import json
import math
import statistics as stats
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "measurements/backend-baseline-v1/board"
BASE = json.loads((OUT.parent / "baseline.json").read_text())
METRICS = {m["id"]: m for m in BASE["metrics"]}
COLLECTIONS = {
    "original": "2026-09-29-shared-host",
    "extension": "2026-09-29-extension",
}
LANGUAGES = ["baml", "node", "rust", "go", "python", "bun"]
NAMES = dict(zip(LANGUAGES, ["BAML", "Node / V8", "Rust", "Go", "Python", "Bun"]))
COLORS = dict(
    zip(LANGUAGES, ["#244bb0", "#427434", "#99502d", "#087a79", "#7955a2", "#596371"])
)
LEVELS = ["off", "low", "medium", "high"]
LEVEL_COLORS = ["#244bb0", "#567bcb", "#7d59a8", "#c46d21"]
SUITE = [
    (
        "original",
        "array-indexed",
        "Indexed array traversal",
        "8,192 integers; 128 jobs; 4 warmups",
        "Indexing, arithmetic and loop dispatch. No BAML GC observed.",
        1,
    ),
    (
        "extension",
        "merge-random",
        "Merge sort",
        "1,024 random integers; 32 jobs; 4 warmups",
        "Handwritten recursion, calls and array copies. No BAML GC observed.",
        1,
    ),
    (
        "original",
        "json-aggregate",
        "JSON aggregation",
        "1,024 records; 32 jobs; 4 warmups",
        "Parsing, strings and aggregate construction. No BAML GC observed.",
        1,
    ),
    (
        "extension",
        "workflow-retain-4",
        "Stateful workflow",
        "768 requests × 128 items; retain 4 keys; no warmup or timers",
        "Persistent state, mutation and eviction. Five BAML collections per batch.",
        768,
    ),
    (
        "extension",
        "generate-sort",
        "Generate and sort",
        "8,192 integers; 32 jobs; 4 warmups",
        "Deterministic generation and native numeric sort. No BAML GC observed.",
        1,
    ),
]
PANELS = []
OBSERVATIONS = []
FOOTER = "29 Sep 2026 • shared Linux aarch64 host • historical reference; host isolation unverified"
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 13,
        "svg.fonttype": "none",
        "svg.hashsalt": "baml-baseline-v1",
    }
)


def csv_rows(relative):
    path = ROOT / "measurements" / relative
    key = str(path.relative_to(ROOT))
    assert key in BASE["source_sha256"], f"Unfrozen input: {key}"
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest() == BASE["source_sha256"][key]
    ), f"Changed input: {key}"
    return list(csv.DictReader(path.open()))


RUNTIME = {
    name: csv_rows(f"{directory}/runtime.csv")
    for name, directory in COLLECTIONS.items()
}
HTTP = csv_rows("2026-09-29-http/http.csv")


def select(collection, scenario, language, level="off"):
    level = level if language == "baml" else "not_applicable"
    rows = [
        r
        for r in RUNTIME[collection]
        if r["scenario"] == scenario
        and r["language"] == language
        and r["level"] == level
        and r["sink"] == ("local" if language == "baml" else "not_applicable")
    ]
    assert len(rows) == 20 and len({r["trial"] for r in rows}) == 20, (
        scenario,
        language,
        level,
        len(rows),
    )
    assert all(r["status"] == "ok" for r in rows), (
        scenario,
        language,
        level,
        "failed trial",
    )
    assert len({r["input_sha256"] for r in rows}) == 1
    if language == "baml":
        assert all(r["telemetry_valid"] == "True" for r in rows)
    return rows


def observation(
    collection,
    scenario,
    language,
    level="off",
    column="execution_wall_ns",
    requests=1,
    divisor=1e6,
    per_job=True,
):
    rows = select(collection, scenario, language, level)
    values = [
        float(r[column]) / divisor / (int(r["jobs"]) * requests if per_job else 1)
        for r in rows
    ]
    record = {
        "collection": COLLECTIONS[collection],
        "scenario": scenario,
        "language": language,
        "level": rows[0]["level"],
        "column": column,
        "divisor": divisor,
        "requests_per_job": requests,
        "per_job": per_job,
        "n": len(values),
        "median": stats.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "values": values,
        "input_sha256": rows[0]["input_sha256"],
    }
    OBSERVATIONS.append(record)
    return record


def header(title, subtitle):
    fig = plt.figure(figsize=(14, 8.5), facecolor="white")
    fig.text(0.045, 0.94, title, fontsize=25, weight="bold", color="#172033")
    fig.text(0.045, 0.89, subtitle, fontsize=13, color="#4d5665")
    return fig


def save(fig, slug, title, note):
    fig.text(
        0.045, 0.092, note, fontsize=11, color="#4d5665", va="top", linespacing=1.6
    )
    fig.text(0.045, 0.025, FOOTER, fontsize=10, color="#6b7280")
    for extension in ("png", "svg"):
        fig.savefig(
            OUT / f"{slug}.{extension}",
            dpi=160,
            metadata={"Date": None} if extension == "svg" else None,
        )
    plt.close(fig)
    PANELS.append({"id": slug, "title": title, "note": note})


def bar(
    slug, title, subtitle, labels, values, colors, unit, note, ranges=None, parity=False
):
    fig = header(title, subtitle)
    ax = fig.add_axes([0.19, 0.22, 0.73, 0.60])
    bars = ax.barh(labels, values, color=colors, height=0.62)
    if ranges:
        ax.errorbar(
            values,
            range(len(values)),
            xerr=[
                [v - lo for v, (lo, hi) in zip(values, ranges)],
                [hi - v for v, (lo, hi) in zip(values, ranges)],
            ],
            fmt="none",
            color="#26313f",
            capsize=3,
            linewidth=1,
        )
    maximum = max([hi for _, hi in ranges] if ranges else values)
    ax.set_xlim(0, maximum * 1.23)
    ax.invert_yaxis()
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=12)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e6e9ed")
    ax.set_xlabel(unit + " • lower is better", labelpad=12)
    if parity:
        ax.axvline(1, color="#222", ls="--", lw=1.4)
    for i, (b, value) in enumerate(zip(bars, values)):
        end = ranges[i][1] if ranges else value
        ax.text(
            end + maximum * 0.02,
            b.get_y() + b.get_height() / 2,
            f"{value:.4g}"
            if value < 0.1
            else f"{value:,.3f}"
            if value < 10
            else f"{value:,.2f}",
            va="center",
            fontsize=13,
            weight="bold",
        )
    save(fig, slug, title, note)


def table(slug, title, subtitle, headers, rows, widths, note, fontsize=12):
    fig = header(title, subtitle)
    ax = fig.add_axes([0.045, 0.19, 0.91, 0.63])
    ax.axis("off")
    tab = ax.table(
        cellText=rows,
        colLabels=headers,
        colWidths=widths,
        cellLoc="left",
        colLoc="left",
        bbox=[0, 0, 1, 1],
    )
    tab.auto_set_font_size(False)
    tab.set_fontsize(fontsize)
    for (row, col), cell in tab.get_celld().items():
        cell.set_edgecolor("white")
        cell.PAD = 0.055
        if row == 0:
            cell.set_facecolor("#172033")
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("#eef2f8" if row % 2 else "#f8f9fb")
    save(fig, slug, title, note)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for relative, expected in BASE["source_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, (
            relative
        )
    suite_ratios = {level: [] for level in LEVELS}
    for collection, scenario, title, size, behavior, requests in SUITE:
        node = observation(collection, scenario, "node", requests=requests)["median"]
        for level in LEVELS:
            suite_ratios[level].append(
                observation(collection, scenario, "baml", level, requests=requests)[
                    "median"
                ]
                / node
            )
    geomeans = {
        level: math.exp(stats.mean(map(math.log, ratios)))
        for level, ratios in suite_ratios.items()
    }
    m = lambda key: METRICS[key]["median"]
    table(
        "01-scorecard",
        "BAML: the starting reference",
        "Keep each cost separate. Record candidate absolute values and change versus this reference.",
        ["KPI", "Measured reference", "What it includes"],
        [
            [
                "Execution vs Node / V8",
                f"{geomeans['off']:.2f}× off / {geomeans['high']:.2f}× high",
                "Five-workload geometric mean; ratio > 1 is slower",
            ],
            [
                "Workflow wall / CPU",
                f"{m('workflow_wall_ms'):.3f} / {m('workflow_cpu_ms'):.3f} ms",
                "Per request; BTEL off; collection included",
            ],
            [
                "Build workflow",
                f"{m('build_runnable_ms'):.3f} ms",
                "Source → packed executable; runtime prebuilt",
            ],
            [
                "Packed hello invocation",
                f"{m('packed_startup_ms'):.3f} ms",
                "Fresh process through exit; includes shutdown",
            ],
            [
                "Native executable",
                f"{m('packed_workflow_mib'):.3f} MiB",
                "Workflow + published musl runtime host",
            ],
            [
                "Allocation peak RSS",
                f"{m('allocation_rss_retain_4_mib'):.2f} / {m('allocation_rss_retain_64_mib'):.2f} MiB",
                "Retain 4 / 64; entire measurement process",
            ],
            [
                "HTTP aggregate p99",
                f"{m('http_aggregate_p99_ms'):.3f} ms",
                "BTEL off; 200 offered req/s; 3-second windows",
            ],
            [
                "BTEL high recording",
                f"{m('btel_high_kib_per_request'):.2f} KiB/request",
                "Whole recording / 768 requests; local sink",
            ],
        ],
        [0.25, 0.25, 0.50],
        "Observed medians. Existing batch checks pass; full conformance is unproven.\nOne HTTP telemetry recording failed validation elsewhere in this collection.",
    )
    bar(
        "02-v8-target",
        "The target: beat V8 with telemetry on",
        "Same five workloads at each level; equal weight per workload; Node / V8 = 1.00×",
        [f"BTEL {l}" for l in LEVELS],
        list(geomeans.values()),
        LEVEL_COLORS,
        "BAML / Node execution wall ratio",
        "Geometric mean = exp(mean(log(BAML median / Node median))). Dashed line is parity.\nAdapter + workload + serialization are timed; these are not isolated VM dispatch costs.",
        parity=True,
    )
    table(
        "03-workload-ratios",
        "Where the V8 gap comes from",
        "Each cell is BAML execution wall / Node execution wall. Below 1.00× beats Node.",
        ["Workload", "BTEL off", "Low", "Medium", "High"],
        [
            [case[2]] + [f"{suite_ratios[level][i]:.2f}×" for level in LEVELS]
            for i, case in enumerate(SUITE)
        ]
        + [
            ["Equal-weight geometric mean"]
            + [f"{geomeans[level]:.2f}×" for level in LEVELS]
        ],
        [0.40, 0.15, 0.15, 0.15, 0.15],
        "Ratio of separate medians, 20 processes per configuration. Fixed finite warmup, not proven V8 steady state.\nThe suite is a chosen reference set, not a claim about every BAML program.",
    )
    for i, (collection, scenario, title, size, behavior, requests) in enumerate(
        SUITE, 4
    ):
        configurations = [("baml", "off"), ("baml", "high")] + [
            (l, "off") for l in LANGUAGES[1:]
        ]
        observations = [
            observation(collection, scenario, lang, level, requests=requests)
            for lang, level in configurations
        ]
        assert len({o["input_sha256"] for o in observations}) == 1, scenario
        labels = [
            f"BAML · {lev}" if lang == "baml" else NAMES[lang]
            for lang, lev in configurations
        ]
        colors = [
            LEVEL_COLORS[3] if lang == "baml" and lev == "high" else COLORS[lang]
            for lang, lev in configurations
        ]
        unit = "ms / request" if requests > 1 else "ms / job"
        bar(
            f"{i:02d}-{scenario}",
            title,
            size,
            labels,
            [o["median"] for o in observations],
            colors,
            unit,
            behavior
            + "\nMedian of 20 process batch averages; whiskers show observed min–max, not confidence intervals.",
            [(o["minimum"], o["maximum"]) for o in observations],
        )
    cpu = [
        observation(
            "extension",
            "workflow-retain-4",
            lang,
            requests=768,
            column="execution_cpu_ns",
        )
        for lang in LANGUAGES
    ]
    bar(
        "09-workflow-cpu",
        "Workflow CPU cost",
        "768 requests × 128 items; retain 4; no timers; BAML BTEL off",
        [NAMES[l] for l in LANGUAGES],
        [o["median"] for o in cpu],
        [COLORS[l] for l in LANGUAGES],
        "CPU ms / request",
        "Process CPU during the execution batch, including runtime threads. Wall and CPU answer different questions.\nRust is handwritten reference code. All languages include their adapter and output serialization.",
    )
    rss = [
        [
            observation(
                "original",
                scenario,
                lang,
                column="peak_rss_bytes",
                divisor=2**20,
                per_job=False,
            )["median"]
            for lang in LANGUAGES
        ]
        for scenario in ["allocation-low-retention", "allocation-high-retention"]
    ]
    fig = header(
        "Memory under allocation pressure",
        "2,048 items × 128 batches/job; 8 jobs; 1 warmup; BAML BTEL off",
    )
    ax = fig.add_axes([0.16, 0.22, 0.76, 0.59])
    for j, (name, values, color) in enumerate(
        zip(["Retain 4", "Retain 64"], rss, ["#244bb0", "#c46d21"])
    ):
        ys = [i + (j - 0.5) * 0.35 for i in range(len(LANGUAGES))]
        ax.barh(ys, values, height=0.30, label=name, color=color)
        for y, value in zip(ys, values):
            ax.text(value + 2, y, f"{value:.2f}", va="center", fontsize=11)
    ax.set_yticks(range(len(LANGUAGES)), [NAMES[l] for l in LANGUAGES])
    ax.invert_yaxis()
    ax.set_xlim(0, max(max(v) for v in rss) * 1.2)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e6e9ed")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlabel("Peak process RSS, MiB • lower is better")
    save(
        fig,
        "10-memory",
        "Memory under allocation pressure",
        "Median of 20 processes; includes adapter, runtime and diagnostics, not just live heap.\nBAML collected 8 / 6 times per batch; Node GC coverage is unknown. Collection counts are not a speed score.",
    )
    btel = []
    for level in LEVELS:
        wall = observation(
            "extension", "workflow-retain-4", "baml", level, requests=768
        )["median"]
        cpu = observation(
            "extension",
            "workflow-retain-4",
            "baml",
            level,
            requests=768,
            column="execution_cpu_ns",
        )["median"]
        recording = observation(
            "extension",
            "workflow-retain-4",
            "baml",
            level,
            column="recording_bytes",
            requests=768,
            divisor=1024,
        )["median"]
        drain = observation(
            "extension",
            "workflow-retain-4",
            "baml",
            level,
            column="drain_ns",
            per_job=False,
        )["median"]
        btel.append(
            [
                level,
                f"{wall:.3f}",
                f"{cpu:.3f}",
                f"{100 * (wall / m('workflow_wall_ms') - 1):+.2f}%",
                f"{recording:.4f}" if recording < 1 else f"{recording:.2f}",
                f"{drain:.3f}",
            ]
        )
    table(
        "11-telemetry",
        "Telemetry cost stays visible",
        "Stateful workflow; same work at every level; local file sink; median of 20 processes",
        [
            "BTEL",
            "Wall ms/req",
            "CPU ms/req",
            "Wall change",
            "KiB/req",
            "Drain ms/batch",
        ],
        btel,
        [0.11, 0.18, 0.18, 0.17, 0.16, 0.20],
        "Drain is a separate post-batch boundary. Recording bytes include preparation and warmup where present.\nSmall negative low-level overhead is noise, not evidence that enabling telemetry makes BAML faster.",
    )
    packed = {}
    for collection, case, name in [
        ("original", "00_startup", "Hello"),
        ("extension", "08_stateful_workflow", "Workflow"),
    ]:
        rows = [
            r
            for n in range(5)
            for r in csv_rows(f"{COLLECTIONS[collection]}/packed/{n}/pack.csv")
            if r["case"] == case and r["backend"] == "published-pack"
        ]
        assert len(rows) == 5 and all(
            r["status"] == "ok" and r["level"] == "off" for r in rows
        )
        assert len({r["artifact_sha256"] for r in rows}) == 1
        packed[name] = rows
    sizes = [
        stats.median(float(r["packed_bytes"]) / 2**20 for r in rows)
        for rows in packed.values()
    ]
    bar(
        "12-native-size",
        "Native executable size",
        "BAML BTEL off; one complete executable; five identical artifact observations per case",
        list(packed),
        sizes,
        ["#244bb0", "#567bcb"],
        "MiB on disk",
        "Published musl runtime host + bytecode. This measures the LTO / runtime-pruning opportunity, not an AOT result.\nWASM size and size without dynamic compilation are unmeasured. Source-file size is not deployment size.",
    )
    table(
        "13-build-startup",
        "Build and startup are separate costs",
        "BAML packed executables; 5 builds and 5 fresh invocations per case",
        ["Boundary", "Hello median", "Workflow median", "Scope"],
        [
            [label]
            + [
                f"{stats.median(float(r[col]) / div for r in rows):.3f} {unit}"
                for rows in packed.values()
            ]
            + [scope]
            for col, div, unit, label, scope in [
                (
                    "compile_wall_ns",
                    1e6,
                    "ms",
                    "Build wall",
                    "Source → runnable; host already built",
                ),
                (
                    "compile_cpu_ns",
                    1e6,
                    "ms",
                    "Build CPU",
                    "CPU used by that pack command",
                ),
                (
                    "compile_peak_rss_bytes",
                    2**20,
                    "MiB",
                    "Build peak RSS",
                    "Pack command high-water mark",
                ),
                (
                    "process_wall_ns",
                    1e6,
                    "ms",
                    "Invocation wall",
                    "Case-specific input → exit; includes shutdown",
                ),
            ]
        ],
        [0.20, 0.18, 0.20, 0.42],
        "Workflow build range: 559.702–1,578.407 ms. Bytecode cache off; filesystem caches uncontrolled.\nPacked workflow invocation: 8 requests × 64 items, retain 2, sequential 10 ms tools; differs from runtime suite.",
    )
    http_table = []
    for lang, level in [("baml", l) for l in LEVELS] + [
        (l, "not_applicable") for l in LANGUAGES[1:]
    ]:
        rows = [
            r
            for r in HTTP
            if r["scenario"] == "http-aggregate-200"
            and r["language"] == lang
            and r["level"] == level
        ]
        assert len(rows) == 5 and len({r["trial"] for r in rows}) == 5
        assert all(
            r["status"] == "ok"
            and r["client_schedule_valid"] == "True"
            and r["failed"] == "0"
            for r in rows
        )
        assert lang != "baml" or all(r["telemetry_valid"] == "True" for r in rows)
        p99 = stats.median(float(r["latency_p99_ns"]) / 1e6 for r in rows)
        rate = stats.median(float(r["throughput"]) for r in rows)
        http_table.append(
            [
                NAMES[lang] + (" · " + level if lang == "baml" else ""),
                f"{p99:.3f}",
                f"{rate:.1f}",
                "0 / 3,000",
            ]
        )
    table(
        "14-http",
        "HTTP at a fixed offered load",
        "Aggregate 64 items; 200 req/s offered; 3-second window × 5 trials; 10 warmup requests",
        ["Runtime", "p99 latency, ms", "Completed req/s", "Failed / attempted"],
        http_table,
        [0.31, 0.23, 0.23, 0.23],
        "Median of trial p99s and throughputs; failures total all five trials. Loopback HTTP/1.1, connection close.\nThis measures the server + runtime + handler stack. 200 req/s is the test rate, not maximum capacity.",
    )
    concurrent = []
    for scenario in ["workflow-tools-1", "workflow-tools-4"]:
        concurrent.append(
            [
                observation("extension", scenario, "baml", requests=192, column=col)[
                    "median"
                ]
                for col in ["execution_wall_ns", "execution_cpu_ns"]
            ]
        )
    table(
        "15-concurrency",
        "Concurrency with waiting",
        "BAML BTEL off; 192 requests × 512 items; four tools; each timer 1 ms; retain 4",
        ["Scheduling", "Wall ms/request", "CPU ms/request"],
        [
            [name] + [f"{v:.3f}" for v in values]
            for name, values in zip(
                ["Sequential tools", "Four concurrent tools"], concurrent
            )
        ],
        [0.46, 0.27, 0.27],
        "Same tool work in both conditions. Wall includes waiting; CPU does not charge idle wait time.\nThis does not establish CPU-parallel speedup. True multicore scaling remains unmeasured.",
        fontsize=15,
    )
    table(
        "16-next-backend",
        "MIR → Rust: what to record next",
        "Record supported semantics first; then report absolute costs and change against the same-checkout VM.",
        ["Check", "Rule for every implementation"],
        [
            [
                "Correctness",
                "Same inputs, outputs, state transitions, errors and cleanup.\nUnsupported behavior stays UNSUPPORTED; no partial-suite full score.",
            ],
            [
                "Execution",
                "Run all five fixed workloads; show each result and their geometric mean.\nCompare off + each supported telemetry level; target ratio < 1 vs V8.",
            ],
            [
                "Build + native size",
                "Include Rust compilation + linking; declare runtime build/cache scope.\nMeasure executable plus required runtime dependencies; identify strip/LTO flags.",
            ],
            [
                "Memory + GC",
                "Keep retention and work fixed; demonstrate collection on GC cases.\nPreserve reclamation semantics; report peak RSS and collection coverage.",
            ],
            [
                "Telemetry + HTTP",
                "Require complete telemetry and zero delivery loss at supported levels.\nCompare latency at the same offered load, with errors and client lag visible.",
            ],
            [
                "Host drift",
                "Rerun the frozen VM beside the candidate on the same host.\nCost index = 100 × candidate median / control median; lower is better.",
            ],
        ],
        [0.24, 0.76],
        "Unmeasured: WASM footprint, dynamic-compiler removal, sustained capacity, GC pause tails and CPU scaling.\nScalar-only MIR → Rust tests cannot yet claim a workflow, GC, JSON or whole-suite win.",
        fontsize=12,
    )
    result = {
        "schema": 1,
        "baseline_id": BASE["id"],
        "source_sha256": BASE["source_sha256"],
        "runtime_suite": [s[1] for s in SUITE],
        "node_ratios": suite_ratios,
        "geometric_mean_ratios": geomeans,
        "observations": OBSERVATIONS,
        "packed": packed,
        "http_table": http_table,
        "panels": PANELS,
    }
    (OUT / "chart-data.json").write_text(json.dumps(result, indent=2) + "\n")
    build_excalidraw()
    cards = "\n".join(
        f'<figure><a href="{p["id"]}.svg"><img src="{p["id"]}.png" alt="{html.escape(p["title"])}"></a></figure>'
        for p in PANELS
    )
    (OUT / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BAML baseline board</title><style>body{margin:24px;background:#e8ecf2;color:#172033;font:16px system-ui}main{max-width:1400px;margin:auto}figure{margin:24px 0}img{width:100%;display:block}a{color:#244bb0}</style><main><h1>BAML baseline board</h1><p>Frozen 29 Sep 2026 observations. <a href="README.txt">Scope and reproduction</a> · <a href="chart-data.json">Exact values</a> · <a href="baseline-section.excalidraw">Excalidraw section</a></p>'
        + cards
        + "</main></html>"
    )
    print(
        json.dumps(
            {"panels": len(PANELS), "geomeans": geomeans, "output": str(OUT)}, indent=2
        )
    )


def build_excalidraw():
    elements = []
    files = {}
    timestamp = 1790726400000

    def common(identity, kind, x, y, width, height):
        return {
            "id": identity,
            "type": kind,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "angle": 0,
            "strokeColor": "#172033",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": 1729 + len(elements),
            "version": 1,
            "versionNonce": 1739 + len(elements),
            "isDeleted": False,
            "boundElements": None,
            "updated": timestamp,
            "link": None,
            "locked": False,
        }

    title = "CURRENT BASELINE  ·  29 SEPTEMBER 2026"
    heading = common("baml-baseline-v1-title", "text", -350, 4300, 4000, 75)
    heading.update(
        text=title,
        originalText=title,
        fontSize=60,
        fontFamily=2,
        textAlign="left",
        verticalAlign="top",
        containerId=None,
        autoResize=True,
        lineHeight=1.25,
    )
    elements.append(heading)
    subtitle = "BAML 0.20.2-nightly.20260927.a  |  340b9085d942  |  shared Linux aarch64\nRust 1.98.1  ·  Go 1.27.1  ·  Python 3.14.7  ·  Node 26.10.0  ·  Bun 1.4.2\nGoal: beat V8 with telemetry ON. Lower cost is better; correctness and complete telemetry are gates.\nSource: instrumentation/measurements/backend-baseline-v1/board/chart-data.json"
    sub = common("baml-baseline-v1-subtitle", "text", -350, 4410, 4000, 160)
    sub.update(
        text=subtitle,
        originalText=subtitle,
        fontSize=32,
        fontFamily=2,
        textAlign="left",
        verticalAlign="top",
        containerId=None,
        autoResize=True,
        lineHeight=1.25,
    )
    elements.append(sub)
    # Three columns align this section to the width of the existing technical map.
    for i, panel in enumerate(PANELS):
        data = (OUT / (panel["id"] + ".png")).read_bytes()
        file_id = hashlib.sha1(data).hexdigest()
        files[file_id] = {
            "id": file_id,
            "mimeType": "image/png",
            "dataURL": "data:image/png;base64," + base64.b64encode(data).decode(),
            "created": timestamp,
            "lastRetrieved": timestamp,
        }
        el = common(
            "baml-baseline-v1-" + panel["id"],
            "image",
            -350 + (i % 3) * 1360,
            4600 + (i // 3) * 885,
            1280,
            1280 * 8.5 / 14,
        )
        el.update(
            fileId=file_id,
            status="saved",
            scale=[1, 1],
            crop=None,
            strokeColor="transparent",
        )
        elements.append(el)
    (OUT / "baseline-section.excalidraw").write_text(
        json.dumps(
            {
                "type": "excalidraw",
                "version": 2,
                "source": "https://draw.harivan.sh",
                "elements": elements,
                "files": files,
                "appState": {"viewBackgroundColor": "#ffffff"},
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
