"""Derive comparison-ready CSV; never change raw observations or accept a baseline."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import statistics

KEYS = [
    "case",
    "scenario",
    "language",
    "backend",
    "level",
    "sink",
    "jobs",
    "warmup",
    "input_sha256",
    "artifact_sha256",
]
METRICS = [
    "execution_wall_ns",
    "execution_cpu_ns",
    "process_wall_ns",
    "process_cpu_ns",
    "launch_to_ready_ns",
    "peak_rss_bytes",
    "drain_ns",
    "gc_execution",
    "recording_bytes",
]


def versions_for_cases(manifest, cases):
    """Unselected cached artifacts cannot decide a collection's version labels."""
    selected = set(cases)
    versions = defaultdict(set)
    for key, record in manifest.items():
        if key.split("/", 1)[0] in selected:
            versions[record["language"]].add(record["version"].splitlines()[0])
    for language, values in versions.items():
        if len(values) != 1:
            raise ValueError(f"Mixed {language} versions within one collection")
    return {language: next(iter(values)) for language, values in versions.items()}


def summarize(path):
    groups = defaultdict(list)
    with path.open() as f:
        for row in csv.DictReader(f):
            groups[tuple(row[k] for k in KEYS)].append(row)
    out = []
    for key, rows in groups.items():
        for metric in METRICS:
            values = [
                float(r[metric])
                for r in rows
                if r["status"] == "ok" and r.get(metric) not in ("", None)
            ]
            out.append(
                dict(zip(KEYS, key))
                | dict(
                    metric=metric,
                    n=len(values),
                    failed=sum(r["status"] != "ok" for r in rows),
                    minimum=min(values) if values else "",
                    median=statistics.median(values) if values else "",
                    maximum=max(values) if values else "",
                    coverage=";".join(sorted(set(r.get("coverage", "") for r in rows))),
                )
            )
    with path.with_name("summary.csv").open("w") as f:
        w = csv.DictWriter(
            f,
            fieldnames=KEYS
            + ["metric", "n", "failed", "minimum", "median", "maximum", "coverage"],
        )
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    a = p.parse_args()
    for path in sorted(a.run.glob("*/samples.csv")):
        summarize(path)
