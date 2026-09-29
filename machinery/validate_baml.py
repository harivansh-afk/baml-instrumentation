"""Prove that recording validation rejects missing, truncated and mismatched data."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run import write, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sample = json.loads((args.trial / "sample.json").read_text())
    assert sample["status"] == "ok" and sample["level"] == "high"
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.trial / "recordings"
    expected = sample["jobs"] + sample["warmup"]
    names = json.dumps(sample["function_names"])
    checks = []
    for name in (
        "valid",
        "wrong_count",
        "wrong_names",
        "missing",
        "truncated",
        "duplicate_sequence",
    ):
        destination = args.output / name / "recordings"
        if name == "missing":
            destination.mkdir(parents=True)
        else:
            shutil.copytree(source, destination)
            files = sorted(destination.glob("*/*.btel"))
            assert files
            if name == "truncated":
                files[-1].write_bytes(files[-1].read_bytes()[:5])
            if name == "duplicate_sequence":
                shutil.copyfile(
                    files[0], files[0].with_name("00000000000000000999.btel")
                )
        command = [
            args.host,
            "inspect",
            str(destination),
            str(expected + (name == "wrong_count")),
            "high",
            "{}" if name == "wrong_names" else names,
        ]
        result = subprocess.run(command, text=True, capture_output=True, env=env())
        (destination.parent / "stdout.txt").write_text(result.stdout)
        (destination.parent / "stderr.txt").write_text(result.stderr)
        decoded = json.loads(result.stdout) if result.stdout else {}
        accepted = result.returncode == 0 and decoded.get("valid") is True
        checks.append(
            dict(
                check=name,
                expected_acceptance=name == "valid",
                accepted=accepted,
                passed=accepted == (name == "valid"),
                command=command,
                exit_code=result.returncode,
            )
        )
    artifact = json.loads((args.trial.parents[2] / "artifacts.json").read_text())[
        sample["case"] + "/baml"
    ]
    blocked = args.output / "blocked-destination"
    blocked.write_text("A file cannot be used as a recordings directory.\n")
    fixture = args.trial.parent / (args.trial.name + ".input.json")
    command = artifact["command"] + [
        str(fixture.resolve()),
        "1",
        "0",
        "local",
        str(blocked.resolve()),
    ]
    environment = env(2)
    environment["BAML_TELEMETRY"] = "high"
    result = subprocess.run(command, text=True, capture_output=True, env=environment)
    (args.output / "delivery-failure.stdout.txt").write_text(result.stdout)
    (args.output / "delivery-failure.stderr.txt").write_text(result.stderr)
    checks.append(
        dict(
            check="unwritable_destination",
            passed=result.returncode != 0,
            exit_code=result.returncode,
            command=command,
        )
    )
    write(args.output / "checks.json", checks)
    print(json.dumps(checks, indent=2))
    if not all(check["passed"] for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
