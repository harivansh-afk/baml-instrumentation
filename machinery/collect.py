"""Execute a frozen protocol serially and preserve each build and runtime trial."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from run import CACHE, ROOT, csv_write, digest, write


def execution_sources():
    paths = [
        ROOT / "machinery" / name
        for name in (
            "run.py",
            "measure.py",
            "host.py",
            "observer.c",
            "fixtures.py",
            "pack.py",
            "build_baml.py",
            "Cargo.toml",
            "Cargo.lock",
            "tools.json",
        )
    ]
    paths += [p for p in (ROOT / "machinery/adapters").iterdir() if p.is_file()]
    paths += list((ROOT / "cases").glob("*/workload.*"))
    return paths


def invoke(arguments, log, allow_failure=False):
    log.parent.mkdir(parents=True, exist_ok=True)
    print(" ".join(arguments), flush=True)
    with log.open("w") as stream:
        return subprocess.run(
            arguments, stdout=stream, stderr=subprocess.STDOUT, check=not allow_failure
        ).returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--baml-host", required=True)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    protocol = json.loads(a.protocol.read_text())
    out = a.output.resolve()
    if a.resume:
        if digest(out / "protocol.json") != digest(a.protocol):
            raise ValueError("Cannot resume a changed protocol")
        previous = json.loads((out / "collection.json").read_text())
        if (out / "producer.json").exists():
            for name, expected in json.loads(
                (out / "producer.json").read_text()
            ).items():
                if digest(ROOT / name) != expected:
                    raise ValueError(f"Measured source changed: {name}")
        # Report/document changes may resume; changes to measured code may not.
        for path in out.glob("runtime/*/environment.json"):
            for name, expected in json.loads(path.read_text())[
                "machinery_hashes"
            ].items():
                if name.startswith("machinery/adapters/") or name in (
                    "machinery/run.py",
                    "machinery/measure.py",
                    "machinery/host.py",
                    "machinery/observer.c",
                    "machinery/fixtures.py",
                    "machinery/tools.json",
                ):
                    if digest(ROOT / name) != expected:
                        raise ValueError(f"Measured machinery changed: {name}")
    else:
        out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(a.protocol, out / "protocol.json")
        hashes = {}
        for source in execution_sources():
            relative = source.relative_to(ROOT)
            destination = out / "producer" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            hashes[str(relative)] = digest(source)
        write(out / "producer.json", hashes)
        previous = {}
    state = dict(
        status="running", protocol_sha256=digest(a.protocol), baseline_accepted=False
    )
    if previous:
        state["previous_attempts"] = previous.get("previous_attempts", []) + [
            {k: v for k, v in previous.items() if k != "previous_attempts"}
        ]
    write(out / "collection.json", state)
    common = [
        "--cpus",
        protocol["cpus"],
        "--workers",
        str(protocol["workers"]),
        "--backend",
        protocol["backend"],
        "--timeout",
        "0",
        "--seed",
        str(protocol["seed"]),
    ]
    cases = list(dict.fromkeys(s["case"] for s in protocol["scenarios"]))
    runner = [sys.executable, str(ROOT / "machinery/run.py")]
    failed_scenarios = []
    try:
        for repeat in range(protocol["compile_trials"]):
            source = CACHE / "build" / protocol["backend"]
            destination = out / "compilation" / str(repeat)
            if not (destination / "manifest.json").exists():
                invoke(
                    runner
                    + ["build", "--cases", *cases, "--baml-host", a.baml_host, *common],
                    destination / "build.txt",
                )
                for case in cases:
                    for language in ("baml", "rust", "go"):
                        shutil.copytree(
                            source / case / language / "compile",
                            destination / case / language,
                        )
                for name in ("compile.csv", "manifest.json"):
                    shutil.copyfile(source / name, destination / name)
            packed = out / "packed" / str(repeat)
            if packed.exists():
                if (
                    json.loads((packed / "environment.json").read_text())["status"]
                    != "passed"
                ):
                    raise ValueError(
                        "An incomplete or failed pack run needs a new collection"
                    )
                continue
            invoke(
                [
                    sys.executable,
                    str(ROOT / "machinery/pack.py"),
                    "--cases",
                    *cases,
                    "--cpus",
                    protocol["cpus"],
                    "--output",
                    str(out / "packed" / str(repeat)),
                ],
                out / "packed" / f"{repeat}.txt",
            )
        for scenario in protocol["scenarios"]:
            name = scenario["name"]
            existing = out / "runtime" / name / "environment.json"
            if existing.exists():
                status = json.loads(existing.read_text())["status"]
                if status not in ("passed", "failed"):
                    raise ValueError(
                        "An incomplete runtime scenario needs a new collection"
                    )
                if status == "failed":
                    failed_scenarios.append(name)
                print("Retained completed scenario: " + name, flush=True)
                continue
            arguments = [
                "run",
                "--cases",
                scenario["case"],
                "--scenario",
                name,
                "--trials",
                str(protocol["runtime_trials"]),
                "--output",
                str(out / "runtime" / name),
                *common,
            ]
            for key, value in scenario.items():
                if key not in ("name", "case", "claim", "requires_gc"):
                    arguments += ["--" + key.replace("_", "-")]
                    arguments += (
                        list(map(str, value))
                        if isinstance(value, list)
                        else [str(value)]
                    )
            if invoke(
                runner + arguments,
                out / "runtime" / (name + ".txt"),
                allow_failure=True,
            ):
                failed_scenarios.append(name)
        state.update(
            status="failed" if failed_scenarios else "passed",
            failed_scenarios=failed_scenarios,
        )
    except (Exception, KeyboardInterrupt) as error:
        state.update(
            status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
            error=str(error),
        )
        raise
    finally:
        write(out / "collection.json", state)
    rows = []
    for path in sorted(out.glob("compilation/*/manifest.json")):
        for key, artifact in json.loads(path.read_text()).items():
            case, language = key.split("/")
            if case not in cases:
                continue
            row = dict(
                repeat=int(path.parent.name),
                case=case,
                language=language,
                backend=artifact["backend"],
                artifact_bytes=artifact["artifact_bytes"],
                artifact_kind=artifact["artifact_kind"],
                artifact_sha256=artifact["artifact_sha256"],
                shared_host_bytes=artifact.get("shared_host_bytes"),
                runtime_executable_bytes=artifact.get("runtime_executable_bytes"),
            )
            row.update(artifact.get("compile", {}))
            rows.append(row)
    csv_write(
        out / "compilation.csv",
        rows,
        [
            "repeat",
            "case",
            "language",
            "backend",
            "artifact_kind",
            "artifact_bytes",
            "shared_host_bytes",
            "runtime_executable_bytes",
            "artifact_sha256",
            "status",
            "process_wall_ns",
            "process_cpu_ns",
            "peak_rss_bytes",
        ],
    )


if __name__ == "__main__":
    main()
