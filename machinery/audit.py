"""Check saved exports against raw records without executing a benchmark."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def producer(root):
    hashes = read(root / "producer.json")
    for name, expected in hashes.items():
        require(
            sha(root / "producer" / name) == expected,
            f"{root}: producer mismatch: {name}",
        )
    return len(hashes)


def exported(export, raw, exclude=()):
    for key, value in export.items():
        if key in exclude:
            continue
        original = raw.get(key)
        if key == "heap_alloc_bytes" and original is None:
            original = raw.get("heap_live_bytes")
        expected = "" if original is None else str(original)
        require(value == expected, f"Export differs: {key}: {value!r} != {expected!r}")


def accounting(export, path):
    usage = read(path)
    expected = dict(
        process_wall_ns=usage["wall_ns"],
        process_cpu_ns=round((usage["user_cpu_s"] + usage["system_cpu_s"]) * 1e9),
        peak_rss_bytes=usage["peak_rss_bytes"],
    )
    for key, value in expected.items():
        require(int(export[key]) == value, f"{path}: {key} accounting mismatch")


def batch(root):
    count = producer(root)
    protocol = read(root / "protocol.json")
    observations = rows(root / "runtime.csv")
    seen = set()
    groups = defaultdict(list)
    inputs = defaultdict(set)
    missing_recordings = 0
    for row in observations:
        identity = (row["run_directory"], row["trial_path"])
        require(identity not in seen, f"{root}: duplicate trial")
        seen.add(identity)
        directory = root / row["run_directory"] / row["trial_path"]
        sample = read(directory / "sample.json")
        exported(row, sample, exclude=("run_directory",))
        require(row["status"] == "ok", f"{directory}: unsuccessful trial")
        accounting(row, directory / "usage.json")
        require(
            sha(directory.parent / (directory.name + ".input.json"))
            == row["input_sha256"],
            f"{directory}: input hash mismatch",
        )
        inputs[row["scenario"]].add(row["input_sha256"])
        groups[(row["scenario"], row["language"], row["level"], row["sink"])].append(
            row
        )
        if (
            row["language"] == "baml"
            and row["level"] != "off"
            and row["sink"] == "local"
        ):
            evidence = read(directory / "telemetry.json")
            calls = int(row["jobs"]) + int(row["warmup"])
            require(
                evidence["valid"] and evidence["root_completions"] == calls + 1,
                f"{directory}: recording roots",
            )
            require(
                evidence["run_count"] == (0 if row["level"] == "low" else calls),
                f"{directory}: recording calls",
            )
            if (directory / "recordings").exists():
                size = sum(
                    p.stat().st_size
                    for p in (directory / "recordings").rglob("*")
                    if p.is_file()
                )
                require(
                    size == int(row["recording_bytes"]),
                    f"{directory}: recording size mismatch",
                )
            else:
                missing_recordings += 1
    for name, hashes in inputs.items():
        require(len(hashes) == 1, f"{name}: languages received different inputs")
    for scenario in protocol["scenarios"]:
        languages = scenario.get(
            "languages", ["baml", "rust", "go", "python", "node", "bun"]
        )
        for lang in languages:
            for level in (
                scenario.get("levels", ["off", "low", "medium", "high"])
                if lang == "baml"
                else ["not_applicable"]
            ):
                sink = (
                    scenario.get("sink", "local")
                    if lang == "baml"
                    else "not_applicable"
                )
                group = groups[(scenario["name"], lang, level, sink)]
                require(
                    len(group) == protocol["runtime_trials"],
                    f"{scenario['name']}/{lang}/{level}: missing trials",
                )
                require(
                    len({r["artifact_sha256"] for r in group}) == 1,
                    "mixed artifact hashes",
                )
                minimum = scenario.get("requires_gc", {}).get(lang)
                if minimum:
                    require(
                        all(int(r["gc_execution"]) >= minimum for r in group),
                        f"{scenario['name']}/{lang}: insufficient GC",
                    )
    for row in rows(root / "compilation.csv"):
        if row["status"] == "ok":
            accounting(
                row,
                root
                / "compilation"
                / row["repeat"]
                / row["case"]
                / row["language"]
                / "usage.json",
            )
    for variant in ("random", "sorted", "reverse", "duplicates"):
        if "quick-" + variant in inputs:
            require(
                inputs["quick-" + variant] == inputs["merge-" + variant],
                f"{variant}: sort inputs differ",
            )
    return dict(
        kind="batch",
        root=str(root),
        trials=len(observations),
        producer_files=count,
        local_recordings_unavailable=missing_recordings,
    )


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1] if values else None


def http(root, build_root):
    count = producer(root)
    producer(build_root)
    protocol = read(root / "protocol.json")
    observations = rows(root / "http.csv")
    seen = set()
    groups = defaultdict(list)
    schedule_failures = 0
    for row in observations:
        require(row["trial_path"] not in seen, "Duplicate HTTP trial")
        seen.add(row["trial_path"])
        directory = root / row["trial_path"]
        sample = read(directory / "sample.json")
        exported(row, sample)
        require(
            row["status"] in ("ok", "request_failure", "telemetry_coverage_failure"),
            f"{directory}: incomplete or invalid trial",
        )
        accounting(row, directory / "usage.json")
        result = read(directory / "requests.json")
        config = read(directory / "requests.input.json")
        requests = result["requests"]
        require(
            [r["index"] for r in requests] == list(range(config["requests"])),
            f"{directory}: missing/duplicate requests",
        )
        good = [r for r in requests if r["status"] == "ok"]
        require(
            len(good) == int(row["completed"])
            and len(requests) - len(good) == int(row["failed"]),
            f"{directory}: response totals",
        )
        lags = []
        for request in requests:
            require(
                request["scheduled_ns"]
                == result["started_ns"]
                + round(request["index"] * 1e9 / config["rate"]),
                f"{directory}: arrival schedule",
            )
            if "dispatch_ns" not in request:
                continue
            lag = max(0, request["dispatch_ns"] - request["scheduled_ns"])
            lags.append(lag)
            require(
                request["lag_ns"] == lag
                and request["latency_ns"]
                == max(0, request["completed_ns"] - request["scheduled_ns"])
                and request["service_ns"]
                == request["completed_ns"] - request["dispatch_ns"],
                f"{directory}: request durations",
            )
        values = dict(
            client_lag_p99_ns=percentile(lags, 0.99),
            service_p95_ns=percentile([r["service_ns"] for r in good], 0.95),
        )
        for key, q in [
            ("latency_p50_ns", 0.5),
            ("latency_p95_ns", 0.95),
            ("latency_p99_ns", 0.99),
        ]:
            values[key] = percentile([r["latency_ns"] for r in good], q)
        for key, value in values.items():
            require(sample[key] == value, f"{directory}: {key} percentile mismatch")
        end = max(
            result["started_ns"] + round(config["requests"] * 1e9 / config["rate"]),
            max(r.get("completed_ns", result["started_ns"]) for r in requests),
        )
        duration = end - result["started_ns"]
        require(
            sample["duration_ns"] == duration
            and math.isclose(
                sample["throughput"], len(good) * 1e9 / duration, rel_tol=1e-12
            ),
            f"{directory}: throughput window mismatch",
        )
        valid = (
            values["client_lag_p99_ns"] is not None
            and values["client_lag_p99_ns"] <= protocol["max_client_lag_ms"] * 1e6
        )
        require(
            sample["client_schedule_valid"] == valid,
            f"{directory}: schedule validity mismatch",
        )
        schedule_failures += not valid
        input_hash = hashlib.sha256(
            json.dumps(
                {k: v for k, v in config.items() if k != "port"}, sort_keys=True
            ).encode()
        ).hexdigest()
        require(
            sample["input_sha256"] == input_hash,
            f"{directory}: HTTP input hash mismatch",
        )
        groups[(row["scenario"], row["language"], row["level"])].append(row)
        if row["language"] == "baml" and row["level"] != "off":
            evidence = read(directory / "telemetry.json")
            calls = protocol["warmup_requests"] + len(
                [r for r in requests if "dispatch_ns" in r]
            )
            if row["status"] == "telemetry_coverage_failure":
                require(
                    not evidence["valid"],
                    f"{directory}: failed telemetry unexpectedly marked valid",
                )
                continue
            require(
                evidence["valid"]
                and evidence["root_completions"] == calls + 1
                and evidence["handler_count"]
                == (0 if row["level"] == "low" else calls),
                f"{directory}: HTTP telemetry coverage",
            )
    for scenario in protocol["scenarios"]:
        for lang in ("baml", "rust", "go", "python", "node", "bun"):
            for level in (
                ("off", "low", "medium", "high")
                if lang == "baml"
                else ("not_applicable",)
            ):
                group = groups[(scenario["name"], lang, level)]
                require(
                    len(group) == protocol["trials"],
                    f"{scenario['name']}/{lang}/{level}: missing HTTP trials",
                )
                require(
                    len({r["input_sha256"] for r in group}) == 1
                    and len({r["artifact_sha256"] for r in group}) == 1,
                    "Mixed HTTP input/artifact",
                )
    for row in rows(build_root / "compilation.csv"):
        if row["status"] == "ok":
            accounting(
                row,
                build_root
                / "compilation"
                / row["repeat"]
                / row["language"]
                / "usage.json",
            )
    return dict(
        kind="http",
        root=str(root),
        trials=len(observations),
        requests=sum(int(r["requests"]) for r in observations),
        producer_files=count,
        schedule_violations=schedule_failures,
        invalid_measurement_trials=sum(
            r["status"] not in ("ok", "request_failure") for r in observations
        ),
        failed_requests=sum(int(r["failed"]) for r in observations),
        request_failure_trials=sum(
            r["status"] == "request_failure" for r in observations
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, nargs="*", default=[])
    parser.add_argument("--http", type=Path)
    parser.add_argument("--http-build", type=Path)
    a = parser.parse_args()
    if bool(a.http) != bool(a.http_build):
        parser.error("--http and --http-build must be paired")
    if not a.batch and not a.http:
        parser.error("provide --batch or --http")
    result = [batch(root) for root in a.batch]
    if a.http:
        result.append(http(a.http, a.http_build))
    print(json.dumps(result, indent=2))
    if any(
        r.get("schedule_violations", 0) or r.get("invalid_measurement_trials", 0)
        for r in result
    ):
        raise SystemExit("HTTP contains excluded measurements; see counts above")


if __name__ == "__main__":
    main()
