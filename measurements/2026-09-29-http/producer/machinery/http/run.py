"""Build, verify and measure loopback services separately from the batch runner."""

import argparse
import csv
import json
import hashlib
import os
from pathlib import Path
import queue
import random
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host
import measure
import run as batch
from fixtures import checks, fixture, oracle

ROOT = batch.ROOT
HERE = Path(__file__).resolve().parent
CACHE = batch.CACHE / "http"
LANGUAGES = list(batch.EXT)


def source_files():
    return (
        [
            p
            for p in HERE.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.name != "README.txt"
        ]
        + [
            ROOT / "machinery" / name
            for name in (
                "adapters/baml_http.rs",
                "observer.c",
                "fixtures.py",
                "run.py",
                "measure.py",
                "host.py",
                "tools.json",
                "build_baml.py",
            )
        ]
        + list((ROOT / "cases/06_http_service").glob("workload.*"))
        + list((ROOT / "cases/03_json_aggregate").glob("workload.*"))
    )


def build(output, baml_host, repeats, cpus):
    t = batch.tools()
    environment = batch.env(2)
    py = CACHE / "python/bin/python"
    if not py.exists():
        subprocess.run(
            ["uv", "venv", "--python", t["python"], str(py.parents[1])], check=True
        )
    subprocess.run(
        ["uv", "pip", "sync", "--python", str(py), str(HERE / "requirements.txt")],
        check=True,
    )
    rows = []
    manifest = {}
    for repeat in range(repeats):
        for lang in LANGUAGES:
            dest = CACHE / "build" / str(repeat) / lang
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            ext = batch.EXT[lang]
            source = ROOT / "cases/06_http_service" / f"workload.{ext}"
            aggregate = ROOT / "cases/03_json_aggregate" / f"workload.{ext}"
            env = dict(environment)
            command = None
            record = dict(
                language=lang,
                version=batch.pins()["tools"][lang if lang != "rust" else "rust"][
                    "version"
                ],
                sources={
                    str(p.relative_to(ROOT)): batch.digest(p) for p in source_files()
                },
                backend="baml-release" if lang == "baml" else lang,
            )
            if lang == "baml":
                probe = Path(baml_host).resolve()
                metadata = json.loads(probe.with_suffix(".json").read_text())
                if metadata["binary_sha256"] != batch.digest(probe) or metadata[
                    "probe_sha256"
                ] != batch.digest(ROOT / "machinery/adapters/baml_http.rs"):
                    raise ValueError("HTTP host provenance mismatch")
                merged = dest / "service.baml"
                merged.write_text(aggregate.read_text() + "\n" + source.read_text())
                binary = dest / "program"
                command = [str(probe), "compile", str(merged), str(binary)]
                invocation = [str(probe), "run", str(binary)]
                record.update(
                    host=str(probe),
                    host_provenance=metadata,
                    shared_host_bytes=probe.stat().st_size,
                    artifact_kind="BAML Program bytecode; shared HTTP host excluded",
                )
            elif lang == "rust":
                for name in ("Cargo.toml", "Cargo.lock"):
                    shutil.copyfile(HERE / name, dest / name)
                shutil.copyfile(source, dest / "main.rs")
                shutil.copyfile(aggregate, dest / "aggregate.rs")
                fetch = dict(env)
                fetch.pop("CARGO_NET_OFFLINE", None)
                subprocess.run(
                    [
                        t["cargo"],
                        "fetch",
                        "--locked",
                        "--manifest-path",
                        str(dest / "Cargo.toml"),
                    ],
                    env=fetch,
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
                    "2",
                    "--manifest-path",
                    str(dest / "Cargo.toml"),
                ]
                binary = dest / "target/release/workload"
                invocation = [str(binary)]
                record.update(
                    artifact_kind="native executable with axum 0.8.9 and Tokio"
                )
            elif lang == "go":
                shutil.copyfile(source, dest / "main.go")
                shutil.copyfile(aggregate, dest / "aggregate.go")
                (dest / "go.mod").write_text(
                    "module instrumentation-http\n\ngo 1.27.1\n"
                )
                binary = dest / "program"
                env.update(
                    GOCACHE=str(dest / "go-cache"), GO111MODULE="on", CGO_ENABLED="0"
                )
                command = [
                    t["go"],
                    "-C",
                    str(dest),
                    "build",
                    "-trimpath",
                    "-ldflags=-s -w",
                    "-o",
                    str(binary),
                    ".",
                ]
                invocation = [str(binary)]
                record.update(artifact_kind="native executable with net/http")
            else:
                binary = py if lang == "python" else Path(t[lang])
                invocation = [str(binary), str(source), str(aggregate)]
                record.update(
                    artifact_kind="service and aggregation source; shared interpreter excluded",
                    runtime_executable_bytes=binary.stat().st_size,
                )
            record.update(
                runtime_environment=environment,
                command=invocation,
                artifact=str(binary),
                artifact_sha256=batch.digest(binary) if not command else None,
                compile_command=command,
                build_environment=env,
                cpu_affinity=cpus,
                workers=2,
                observer_sha256=batch.digest(measure.observer()),
            )
            measured = (
                measure.run(
                    command, output / "compilation" / str(repeat) / lang, env, cpus
                )
                if command
                else {}
            )
            if command and measured["status"] != "ok":
                raise RuntimeError(
                    f"{lang} build failed: {output}/compilation/{repeat}/{lang}/stderr.txt"
                )
            record.update(
                artifact_sha256=batch.digest(binary),
                artifact_bytes=binary.stat().st_size
                if command
                else source.stat().st_size + aggregate.stat().st_size,
            )
            row = dict(
                repeat=repeat,
                language=lang,
                **measured,
                artifact_bytes=record["artifact_bytes"],
                artifact_sha256=record["artifact_sha256"],
                artifact_kind=record["artifact_kind"],
                shared_host_bytes=record.get("shared_host_bytes"),
                runtime_executable_bytes=record.get("runtime_executable_bytes"),
            )
            rows.append(row)
            manifest[lang] = record
            batch.write(output / "artifacts.json", manifest)
            batch.csv_write(
                output / "compilation.csv",
                rows,
                [
                    "repeat",
                    "language",
                    "status",
                    "artifact_kind",
                    "artifact_bytes",
                    "artifact_sha256",
                    "shared_host_bytes",
                    "runtime_executable_bytes",
                    "process_wall_ns",
                    "process_cpu_ns",
                    "peak_rss_bytes",
                ],
            )
            print(f"built {repeat + 1}/{repeats} {lang}", flush=True)
    return manifest


def client(config, directory, name, cpus):
    inp = directory / (name + ".input.json")
    out = directory / (name + ".json")
    batch.write(inp, config)
    subprocess.run(
        [sys.executable, str(HERE / "client.py"), str(inp), str(out), "--cpus", cpus],
        check=True,
    )
    return json.loads(out.read_text())


def trial(record, level, scenario, directory, protocol, verify=False):
    directory.mkdir(parents=True, exist_ok=False)
    lang = record["language"]
    env = batch.env(2)
    env["BAML_TELEMETRY"] = level if lang == "baml" else "off"
    command = list(record["command"])
    recordings = directory / "recordings"
    if lang == "baml":
        command.append(str(recordings))
    # Loopback ephemeral port. Bind failure is a retained failed trial, never a hidden retry.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    pidfile = directory / "pid.txt"
    usagefile = directory / "usage.json"
    cpus = protocol["server_cpus"]
    clientcpus = protocol["client_cpus"]
    events = []
    rss = []
    before = host.snapshot(cpus)
    started = time.monotonic_ns()
    ready = None
    pid = None
    lines = queue.Queue()
    stop = threading.Event()
    child = None
    row = dict(
        language=lang,
        level=level,
        scenario=scenario["name"],
        artifact_sha256=record["artifact_sha256"],
        input_sha256=batch.digest(directory.parent.parent / "protocol.json")
        if (directory.parent.parent / "protocol.json").exists()
        else None,
        status="harness_error",
    )
    stderr = (directory / "stderr.txt").open("wb")
    stdout = (directory / "stdout.txt").open("w")

    def reader():
        for line in child.stdout:
            stdout.write(line)
            stdout.flush()
            lines.put(line.strip())

    def sample():
        nonlocal pid
        while not stop.wait(0.01):
            try:
                if pid is None:
                    pid = int(pidfile.read_text())
                fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                rss.append(
                    dict(
                        elapsed_ns=time.monotonic_ns() - started,
                        rss_bytes=int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
                    )
                )
            except (OSError, ValueError):
                pass

    try:
        child = subprocess.Popen(
            [
                str(measure.observer()),
                str(pidfile),
                str(usagefile),
                str(directory),
                ",".join(map(str, cpus)),
                *command,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            env=env,
            start_new_session=True,
        )
        reader_thread = threading.Thread(target=reader)
        reader_thread.start()
        sampler = threading.Thread(target=sample)
        sampler.start()
        child.stdin.write(f"127.0.0.1:{port}\n")
        child.stdin.flush()
        while ready is None:
            if child.poll() is not None:
                raise RuntimeError("server exited before ready")
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line == "@ready":
                ready = time.monotonic_ns() - started
            else:
                events.append(line)
        if verify:
            corpus = [
                dict(
                    method="GET",
                    path="/hello",
                    body="",
                    expected={"message": "Hello, world!"},
                )
            ]
            corpus += [
                dict(
                    method="POST",
                    path="/aggregate",
                    body=raw,
                    expected=oracle("06_http_service", raw),
                    expected_status=400
                    if oracle("06_http_service", raw) == {"error": "invalid"}
                    else 200,
                )
                for _, raw in checks("06_http_service")
            ]
            result = client(
                dict(port=port, checks=corpus), directory, "checks", clientcpus
            )
            count = len(result)
            failed = sum(r["status"] != "ok" for r in result)
            row.update(
                requests=count,
                failed=failed,
                status="ok" if failed == 0 else "wrong_response",
            )
        else:
            body = (
                fixture("06_http_service", size=scenario.get("size", 64))
                if scenario["path"] == "/aggregate"
                else ""
            )
            expected = (
                oracle("06_http_service", body)
                if body
                else {"message": "Hello, world!"}
            )
            spec = dict(
                method="POST" if body else "GET",
                path=scenario["path"],
                body=body,
                expected=expected,
            )
            warmup = client(
                dict(port=port, checks=[spec] * protocol["warmup_requests"]),
                directory,
                "warmup",
                clientcpus,
            )
            if any(r["status"] != "ok" for r in warmup):
                raise RuntimeError("warmup correctness failure")
            config = dict(
                port=port,
                **spec,
                rate=scenario["rate"],
                requests=round(scenario["rate"] * protocol["duration_s"]),
                deadline_s=protocol["request_deadline_s"],
                max_inflight=protocol["max_inflight"],
            )
            result = client(config, directory, "requests", clientcpus)
            count = len(warmup) + len(
                [r for r in result["requests"] if "dispatch_ns" in r]
            )
            row.update({k: v for k, v in result.items() if k != "requests"})
            row.update(
                requests=config["requests"],
                offered_rate=scenario["rate"],
                status="ok" if result["failed"] == 0 else "request_failure",
                client_schedule_valid=result["client_lag_p99_ns"] is not None
                and result["client_lag_p99_ns"] <= protocol["max_client_lag_ms"] * 1e6,
                input_sha256=hashlib.sha256(
                    json.dumps(
                        {k: v for k, v in config.items() if k != "port"}, sort_keys=True
                    ).encode()
                ).hexdigest(),
            )
        child.stdin.write("\n")
        child.stdin.flush()
        child.stdin.close()
        code = child.wait()
        reader_thread.join()
        while not lines.empty():
            events.append(lines.get_nowait())
        if code:
            row["status"] = "server_exit_error"
        if lang == "baml":
            drains = [json.loads(line) for line in events if line.startswith("{")]
            drain = next((x for x in drains if x.get("event") == "drained"), {})
            row.update(drain)
            if not drain.get("telemetry_ok") or drain.get("delivery_loss", 0):
                row["status"] = "telemetry_failure"
            if level != "off":
                check = subprocess.run(
                    [
                        record["host"],
                        "inspect",
                        str(recordings),
                        str(count),
                        level,
                        json.dumps(drain.get("function_names", {})),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                (directory / "telemetry.json").write_text(check.stdout)
                (directory / "telemetry.stderr.txt").write_text(check.stderr)
                evidence = json.loads(check.stdout) if check.stdout else {}
                row["telemetry_valid"] = check.returncode == 0 and evidence.get(
                    "valid", False
                )
            else:
                row["telemetry_valid"] = not recordings.exists() or not any(
                    p.is_file() for p in recordings.rglob("*")
                )
            if not row["telemetry_valid"]:
                row["status"] = "telemetry_coverage_failure"
            row["recording_bytes"] = sum(
                p.stat().st_size for p in recordings.rglob("*") if p.is_file()
            )
        usage = json.loads(usagefile.read_text())
        row.update(
            process_wall_ns=usage["wall_ns"],
            process_cpu_ns=round((usage["user_cpu_s"] + usage["system_cpu_s"]) * 1e9),
            peak_rss_bytes=usage["peak_rss_bytes"],
            launch_to_ready_ns=ready,
        )
    except Exception as error:
        row.update(status="harness_error", error=f"{type(error).__name__}: {error}")
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        stop.set()
        if child is not None:
            sampler.join()
            reader_thread.join()
            child.stdout.close()
        stderr.close()
        stdout.close()
        batch.write(directory / "rss.json", rss)
        batch.write(
            directory / "host.json", dict(before=before, after=host.snapshot(cpus))
        )
        batch.write(directory / "events.json", events)
        batch.write(directory / "sample.json", row)
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["build", "verify", "run"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--artifacts", type=Path)
    p.add_argument("--baml-host")
    p.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    p.add_argument("--repeats", type=int, default=1)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(a.protocol.read_text())
    batch.write(out / "protocol.json", protocol)
    hashes = {
        str(path.relative_to(ROOT)): batch.digest(path) for path in source_files()
    }
    for name in hashes:
        dest = out / "producer" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    batch.write(out / "producer.json", hashes)
    if a.action == "build":
        build(out, a.baml_host, a.repeats, protocol["server_cpus"])
        return
    records = json.loads(a.artifacts.read_text())
    batch.write(out / "artifacts.json", records)
    for record in records.values():
        if batch.digest(record["artifact"]) != record["artifact_sha256"]:
            raise ValueError("stale HTTP artifact")
        if (
            record["language"] == "baml"
            and batch.digest(record["host"])
            != record["host_provenance"]["binary_sha256"]
        ):
            raise ValueError("stale HTTP host")
        for name, expected in record["sources"].items():
            if batch.digest(ROOT / name) != expected:
                raise ValueError("stale HTTP source: " + name)
    schedule = [
        (lang, level, scenario, repeat)
        for scenario in (
            [{"name": "correctness"}] if a.action == "verify" else protocol["scenarios"]
        )
        for lang in LANGUAGES
        for level in (
            ["off", "low", "medium", "high"] if lang == "baml" else ["not_applicable"]
        )
        for repeat in range(1 if a.action == "verify" else protocol["trials"])
    ]
    random.Random(protocol["seed"]).shuffle(schedule)
    rows = []
    batch.write(
        out / "collection.json", dict(status="running", baseline_accepted=False)
    )
    for i, (lang, level, scenario, repeat) in enumerate(schedule):
        directory = out / "trials" / f"{i:04d}-{lang}-{level}"
        row = trial(
            records[lang], level, scenario, directory, protocol, a.action == "verify"
        )
        row.update(trial=repeat, trial_path=str(directory.relative_to(out)))
        rows.append(row)
        batch.write(directory / "sample.json", row)
        batch.csv_write(
            out / "http.csv",
            rows,
            sorted(set().union(*(r.keys() for r in rows)) - {"function_names"}),
        )
        print(
            f"{i + 1}/{len(schedule)} {scenario['name']}/{lang}/{level}: {row['status']}",
            flush=True,
        )
    batch.write(
        out / "collection.json",
        dict(
            status="passed" if all(r["status"] == "ok" for r in rows) else "failed",
            baseline_accepted=False,
            trials=len(rows),
            failures=sum(r["status"] != "ok" for r in rows),
            client_schedule_failures=sum(
                r.get("client_schedule_valid") is False for r in rows
            ),
        ),
    )
    if any(r["status"] != "ok" for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
