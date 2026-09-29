"""Build and measure explicit artifacts. Every observation retains its scope."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time

from fixtures import checks, fixture, matches, oracle
import measure

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
CASES = tuple(
    p.name
    for p in sorted((ROOT / "cases").iterdir())
    if p.is_dir() and p.name != "06_http_service"
)
EXT = {
    "baml": "baml",
    "rust": "rs",
    "go": "go",
    "python": "py",
    "node": "ts",
    "bun": "ts",
}
FIELDS = [
    "schema",
    "case",
    "scenario",
    "language",
    "backend",
    "level",
    "sink",
    "trial",
    "status",
    "coverage",
    "jobs",
    "warmup",
    "execution_wall_ns",
    "execution_cpu_ns",
    "process_wall_ns",
    "process_cpu_ns",
    "launch_to_ready_ns",
    "peak_rss_bytes",
    "drain_ns",
    "gc_execution",
    "gc_warmup",
    "gc_drain",
    "gc_counter",
    "telemetry_valid",
    "telemetry_run_count",
    "recording_bytes",
    "artifact_sha256",
    "input_sha256",
    "trial_path",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def tools():
    return json.loads((CACHE / "tools.local.json").read_text())


def pins():
    return json.loads((ROOT / "machinery/tools.json").read_text())


def version(command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def env(workers=1):
    # No inherited tuning, external credentials, compiler cache, or telemetry policy.
    value = {
        k: os.environ[k]
        for k in (
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "SSL_CERT_FILE",
            "NIX_SSL_CERT_FILE",
            "NIX_LD",
            "NIX_LD_LIBRARY_PATH",
            "LIBRARY_PATH",
            "LD_LIBRARY_PATH",
        )
        if k in os.environ
    }
    value.update(
        {
            "LC_ALL": "C",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GOMAXPROCS": str(workers),
            "BENCH_WORKERS": str(workers),
            "TOKIO_WORKER_THREADS": str(workers),
            "BAML_TELEMETRY": "off",
            "BAML_NO_BYTECODE_CACHE": "1",
            "BAML_NO_DIAGNOSTICS_CACHE": "1",
            "BAML_AGENT_SKILL_CHECK": "off",
            "GOTOOLCHAIN": "local",
            "CARGO_NET_OFFLINE": "true",
        }
    )
    value["RUSTC"] = tools()["rustc"]
    return value


def sources(case, lang):
    paths = [
        ROOT / "cases" / case / f"workload.{EXT[lang]}",
        ROOT
        / "machinery/adapters"
        / ("baml.rs" if lang == "baml" else f"main.{EXT[lang]}"),
    ]
    if lang == "rust":
        paths += [ROOT / "machinery/Cargo.toml", ROOT / "machinery/Cargo.lock"]
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def csv_write(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(args):
    t = tools()
    p = pins()
    root = CACHE / "build" / args.backend
    root.mkdir(parents=True, exist_ok=True)
    manifest = (
        json.loads((root / "manifest.json").read_text())
        if (root / "manifest.json").exists()
        else {}
    )
    rows = []
    for case in args.cases:
        for lang in args.languages:
            dest = root / case / lang
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            source = ROOT / "cases" / case / f"workload.{EXT[lang]}"
            e = env(args.workers)
            binary = dest / "program"
            command = None
            record = {
                "language": lang,
                "backend": args.backend if lang == "baml" else lang,
                "sources": sources(case, lang),
                "cache_policy": "empty application and dependency compilation caches; dependencies fetched before timer",
            }
            if lang == "baml":
                if not args.baml_host:
                    raise ValueError(
                        "--baml-host is required; setup the selected source adapter first"
                    )
                host = Path(args.baml_host).resolve()
                provenance = json.loads(host.with_suffix(".json").read_text())
                if provenance["binary_sha256"] != digest(host) or provenance[
                    "probe_sha256"
                ] != digest(ROOT / "machinery/adapters/baml.rs"):
                    raise ValueError("BAML host provenance mismatch")
                if (
                    provenance["revision"] != args.baml_revision
                    or provenance["profile"] != args.baml_profile
                ):
                    raise ValueError("BAML source/profile differs from requested build")
                record["host_provenance"] = provenance
                record["shared_host_bytes"] = host.stat().st_size
                record.update(
                    host=str(host),
                    host_sha256=digest(host),
                    source_revision=args.baml_revision,
                    profile=args.baml_profile,
                    artifact_kind="BAML Program bytecode; shared measurement host excluded",
                )
                command = [str(host), "compile", str(source), str(binary)]
                invocation = [str(host), "run", str(binary)]
                record["version"] = (
                    p["tools"]["baml"]["version"]
                    if args.baml_revision == p["baml_revision"]
                    else args.baml_revision
                )
            elif lang == "rust":
                shutil.copy(source, dest / "workload.rs")
                shutil.copy(ROOT / "machinery/adapters/main.rs", dest / "main.rs")
                shutil.copy(ROOT / "machinery/Cargo.toml", dest / "Cargo.toml")
                shutil.copy(ROOT / "machinery/Cargo.lock", dest / "Cargo.lock")
                # Downloading dependencies is setup, compilation is measured.
                fetch_env = dict(e)
                fetch_env.pop("CARGO_NET_OFFLINE", None)
                subprocess.run(
                    [
                        t["cargo"],
                        "fetch",
                        "--locked",
                        "--manifest-path",
                        str(dest / "Cargo.toml"),
                    ],
                    env=fetch_env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                command = [
                    t["cargo"],
                    "build",
                    "--release",
                    "--locked",
                    "--offline",
                    "--jobs",
                    str(args.workers),
                    "--manifest-path",
                    str(dest / "Cargo.toml"),
                ]
                binary = dest / "target/release/workload"
                invocation = [str(binary)]
                record.update(
                    version=version([t["rustc"], "-Vv"]),
                    artifact_kind="native executable plus measurement adapter",
                )
            elif lang == "go":
                shutil.copy(source, dest / "workload.go")
                shutil.copy(ROOT / "machinery/adapters/main.go", dest / "main.go")
                e.update(
                    GOCACHE=str(dest / "go-cache"), GO111MODULE="off", CGO_ENABLED="0"
                )
                command = [
                    t["go"],
                    "build",
                    "-trimpath",
                    "-ldflags=-s -w",
                    "-o",
                    str(binary),
                    str(dest / "main.go"),
                    str(dest / "workload.go"),
                ]
                invocation = [str(binary)]
                record.update(
                    version=version([t["go"], "version"]),
                    artifact_kind="native executable plus measurement adapter",
                )
            else:
                binary = Path(t[lang])
                invocation = [
                    str(binary),
                    str(ROOT / f"machinery/adapters/main.{EXT[lang]}"),
                    str(source),
                ]
                record.update(
                    version=version([str(binary), "--version"]),
                    artifact_kind="source and measurement adapter; interpreter is shared",
                    compile_status="not_applicable",
                )
            if command:
                observed = measure.run(
                    command, dest / "compile", e, args.cpus, args.timeout
                )
                rows.append(
                    dict(
                        case=case, language=lang, backend=record["backend"], **observed
                    )
                )
                if observed["status"] != "ok":
                    raise RuntimeError(f"build failed: {dest}/compile/stderr.txt")
                record["compile"] = observed
                record["compile_command"] = command
            record.update(
                command=invocation,
                build_environment=e,
                artifact=str(binary),
                artifact_sha256=digest(binary),
                artifact_bytes=binary.stat().st_size,
                source_bytes=source.stat().st_size,
                tools=p["tools"],
                cpu_affinity=args.cpus,
                workers=args.workers,
            )
            if lang in ("node", "bun", "python"):
                record["artifact_bytes"] = sum(
                    (ROOT / path).stat().st_size for path in record["sources"]
                )
                record["runtime_executable_bytes"] = binary.stat().st_size
            manifest[f"{case}/{lang}"] = record
            write(root / "manifest.json", manifest)
            print(f"built {case}/{lang}", flush=True)
    csv_write(
        root / "compile.csv",
        rows,
        [
            "case",
            "language",
            "backend",
            "status",
            "process_wall_ns",
            "process_cpu_ns",
            "peak_rss_bytes",
        ],
    )


def load(case, lang, backend):
    record = json.loads((CACHE / "build" / backend / "manifest.json").read_text())[
        f"{case}/{lang}"
    ]
    if record["sources"] != sources(case, lang) or record["artifact_sha256"] != digest(
        record["artifact"]
    ):
        raise ValueError(f"stale artifact: {case}/{lang}")
    if lang == "baml" and record["host_sha256"] != digest(record["host"]):
        raise ValueError("stale BAML host")
    return record


def valid_protocol(observed, value, language, jobs):
    expected = (
        ["ready", "result", "drained"] if language == "baml" else ["ready", "result"]
    )
    if observed["event_order"] != expected or observed["malformed_lines"]:
        return False
    if type(value.get("jobs")) is not int or value["jobs"] != jobs:
        return False
    for counter in ("gc_execution", "gc_warmup"):
        count = value.get(counter)
        if count is not None and (type(count) is not int or count < 0):
            return False
        if (
            language == "baml"
            and count is None
            and value.get("gc_counter") != "unavailable"
        ):
            return False
    for phase in ("wall", "cpu"):
        duration = value.get(f"execution_{phase}_ns")
        total = observed.get(f"process_{phase}_ns")
        if type(duration) is not int or duration < 0 or total is None:
            return False
        if duration > total + 1_000_000:
            return False
    return isinstance(value.get("result"), str)


def trial(record, raw, case, lang, level, sink, jobs, warmup, directory, args):
    fixture_path = directory.parent / (directory.name + ".input.json")
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(raw)
    command = record["command"] + [str(fixture_path), str(jobs), str(warmup)]
    recordings = directory / "recordings"
    if lang == "baml":
        command += [sink, str(recordings)]
    e = env(args.workers)
    e["BAML_TELEMETRY"] = level if lang == "baml" else "off"
    observed = measure.run(command, directory, e, args.cpus, args.timeout)
    value = observed.pop("result") or {}
    drain = observed.pop("drain") or {}
    if observed["status"] == "ok" and not valid_protocol(observed, value, lang, jobs):
        observed["status"] = "invalid_protocol"
    row = dict(
        schema=1,
        case=case,
        language=lang,
        backend=record["backend"],
        level=level,
        sink=sink,
        jobs=jobs,
        warmup=warmup,
        artifact_sha256=record["artifact_sha256"],
        input_sha256=digest(fixture_path),
        trial_path=str(directory.relative_to(args.output)),
        **observed,
        **{
            k: v
            for k, v in value.items()
            if k not in ("event", "result", "received_ns", "jobs")
        },
        **{k: v for k, v in drain.items() if k not in ("event", "received_ns")},
    )
    if row["status"] == "ok":
        try:
            correct = (
                matches(json.loads(value["result"]), oracle(case, raw))
                and value["jobs"] == jobs
            )
        except (ValueError, KeyError, TypeError):
            correct = False
        if not correct:
            row["status"] = "wrong_result"
    gc = row.get("gc_execution")
    row["coverage"] = (
        "gc_observed"
        if gc is not None and gc > 0
        else (
            "gc_not_observed"
            if gc == 0
            else "gc_unknown"
            if lang != "rust"
            else "gc_not_applicable"
        )
    )
    if lang == "baml":
        if not drain.get("telemetry_ok", False) or drain.get("delivery_loss", 0):
            row["status"] = "telemetry_failure"
        if sink == "local" and level != "off" and row["status"] == "ok":
            check = subprocess.run(
                [record["host"], "inspect", str(recordings), str(jobs + warmup), level],
                capture_output=True,
                text=True,
                env=e,
                timeout=args.timeout,
            )
            (directory / "telemetry.json").write_text(check.stdout)
            (directory / "telemetry.stderr.txt").write_text(check.stderr)
            try:
                evidence = json.loads(check.stdout)
            except ValueError:
                evidence = {}
            row["telemetry_valid"] = check.returncode == 0 and evidence.get(
                "valid", False
            )
            row["telemetry_run_count"] = evidence.get("run_count")
            if not row["telemetry_valid"]:
                row["status"] = "telemetry_coverage_failure"
        elif level == "off":
            row["telemetry_valid"] = not recordings.exists() or not any(
                p.is_file() for p in recordings.rglob("*")
            )
            if not row["telemetry_valid"]:
                row["status"] = "telemetry_failure"
        row["recording_bytes"] = (
            sum(p.stat().st_size for p in recordings.rglob("*") if p.is_file())
            if recordings.exists()
            else 0
        )
    write(directory / "sample.json", row)
    return row


def execute(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    args.created_output = True
    metadata = {
        "schema": 1,
        "kind": args.action,
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_affinity": args.cpus,
        "workers": args.workers,
        "runtime_environment": env(args.workers),
        "observer_sha256": digest(measure.observer()),
        "observer_compiler": version(["cc", "--version"]),
        "pins": pins(),
        "argv": sys.argv,
        "protocol": "serialized job inside child; stdout and controller checks outside execution; ready time is parent-observed",
        "controller_hash": digest(__file__),
        "machinery_hashes": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (ROOT / "machinery").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        },
        "machine_cpuinfo": Path("/proc/cpuinfo").read_text(),
        "baseline_accepted": False,
        "status": "running",
        "note": "pilot and correctness runs are not a published baseline",
    }
    write(args.output / "environment.json", metadata)
    schedule = []
    artifacts = {}
    for case in args.cases:
        inputs = (
            list(checks(case))
            if args.action == "verify"
            else [
                (
                    args.scenario,
                    fixture(
                        case,
                        args.size,
                        args.variant,
                        args.batches,
                        args.retain,
                        args.fanout,
                        args.delay_ms,
                        args.seed,
                    ),
                )
            ]
        )
        for lang in args.languages:
            record = load(case, lang, args.backend)
            artifacts[f"{case}/{lang}"] = record
            for relative in record["sources"]:
                snapshot = args.output / "sources" / relative
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, snapshot)
            configs = (
                [(level, args.sink) for level in args.levels]
                if lang == "baml"
                else [("not_applicable", "not_applicable")]
            )
            for label, raw in inputs:
                for level, sink in configs:
                    for repeat in range(args.trials):
                        schedule.append((case, lang, label, raw, level, sink, repeat))
    random.Random(args.seed).shuffle(schedule)
    write(args.output / "artifacts.json", artifacts)
    rows = []
    for n, (case, lang, label, raw, level, sink, repeat) in enumerate(schedule):
        record = artifacts[f"{case}/{lang}"]
        directory = args.output / case / "trials" / f"{n:05d}-{lang}-{level}"
        try:
            row = trial(
                record,
                raw,
                case,
                lang,
                level,
                sink,
                1 if args.action == "verify" else args.jobs,
                0 if args.action == "verify" else args.warmup,
                directory,
                args,
            )
        except Exception as error:
            row = dict(
                schema=1,
                case=case,
                language=lang,
                backend=record["backend"],
                level=level,
                sink=sink,
                status="harness_error",
                error=str(error),
            )
            write(directory / "sample.json", row)
        row.update(scenario=label, trial=repeat)
        rows.append(row)
        write(directory / "sample.json", row)
        csv_write(
            args.output / case / "samples.csv",
            [r for r in rows if r["case"] == case],
            FIELDS,
        )
        print(
            f"{n + 1}/{len(schedule)} {case}/{lang}/{level}/{label}: {row['status']} {row.get('coverage', '')}",
            flush=True,
        )
    failed = any(r["status"] != "ok" for r in rows)
    metadata.update(status="failed" if failed else "passed", trials=len(rows))
    write(args.output / "environment.json", metadata)
    if failed:
        raise SystemExit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["build", "verify", "run"])
    p.add_argument(
        "--cases",
        nargs="+",
        choices=CASES,
        default=["00_startup", "01_array_traversal", "04_allocation_retention"],
    )
    p.add_argument("--languages", nargs="+", choices=list(EXT), default=list(EXT))
    p.add_argument("--backend", default="baml-release")
    p.add_argument("--baml-host")
    p.add_argument("--baml-revision", default=pins()["baml_revision"])
    p.add_argument("--baml-profile", default="release")
    p.add_argument(
        "--cpus",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[min(os.sched_getaffinity(0))],
    )
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--timeout", type=float, default=110)
    p.add_argument("--output", type=Path)
    p.add_argument(
        "--levels",
        nargs="+",
        choices=["off", "low", "medium", "high"],
        default=["off", "low", "medium", "high"],
    )
    p.add_argument("--sink", choices=["local", "none"], default="local")
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--warmup", type=int, default=0)
    p.add_argument("--size", type=int, default=64)
    p.add_argument("--batches", type=int, default=8)
    p.add_argument("--retain", type=int, default=2)
    p.add_argument("--fanout", type=int, default=8)
    p.add_argument("--delay-ms", type=int, default=10)
    p.add_argument("--variant", default="iterator")
    p.add_argument("--scenario", default="pilot")
    p.add_argument("--seed", type=int, default=1729)
    args = p.parse_args()
    if (
        args.jobs < 1
        or args.trials < 1
        or args.workers < 1
        or min(
            args.warmup,
            args.size,
            args.batches,
            args.retain,
            args.fanout,
            args.delay_ms,
        )
        < 0
    ):
        p.error("counts must be nonnegative; jobs/trials/workers positive")
    if not args.cpus or not set(args.cpus) <= os.sched_getaffinity(0):
        p.error("CPUs must belong to the allowed affinity")
    if args.action != "build" and not args.output:
        p.error("--output is required and must be new")
    if args.action == "build":
        build(args)
    else:
        args.created_output = False
        try:
            execute(args)
        except Exception as error:
            metadata_path = args.output / "environment.json"
            if args.created_output and metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())
                if metadata.get("status") == "running":
                    metadata.update(status="setup_error", error=str(error))
                    write(metadata_path, metadata)
            raise


if __name__ == "__main__":
    main()
