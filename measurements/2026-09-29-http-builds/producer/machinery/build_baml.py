"""Build the probe in an isolated checkout of an explicit BAML revision."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkout", type=Path, required=True)
    p.add_argument("--revision")
    p.add_argument("--profile", choices=["release", "dev"], default="release")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument(
        "--timeout", type=int, default=0, help="seconds; 0 disables the cutoff"
    )
    p.add_argument("--worktree-name")
    p.add_argument("--probe", choices=["runtime", "http"], default="runtime")
    a = p.parse_args()
    pins = json.loads((ROOT / "machinery/tools.json").read_text())
    tools = json.loads((ROOT / ".cache/tools.local.json").read_text())
    revision = a.revision or pins["baml_revision"]
    checkout = a.checkout.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", revision + "^{commit}"], text=True
    ).strip()
    name = a.worktree_name or f"instrumentation-{revision[:12]}"
    if name in (".", "..") or Path(name).name != name:
        p.error("--worktree-name must be a single directory name")
    work = checkout / ".worktrees" / name
    if not work.exists():
        subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "worktree",
                "add",
                "--detach",
                str(work),
                revision,
            ],
            check=True,
        )
    if (
        subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "HEAD"], text=True
        ).strip()
        != revision
    ):
        raise ValueError("source revision mismatch")
    dirty = subprocess.check_output(
        ["git", "-C", str(work), "diff", "--name-only", "HEAD"], text=True
    ).strip()
    if dirty:
        raise ValueError("source worktree has tracked modifications")
    example = "instrumentation_http" if a.probe == "http" else "instrumentation"
    probe = (
        ROOT
        / "machinery/adapters"
        / ("baml_http.rs" if a.probe == "http" else "baml.rs")
    )
    shutil.copy(
        probe, work / "baml_language/crates/bex_engine/examples" / (example + ".rs")
    )
    target = checkout / "baml_language/target"
    e = dict(os.environ, RUSTC=tools["rustc"], CARGO_TARGET_DIR=str(target))
    for key in list(e):
        if key.startswith("CARGO_PROFILE_") or key in (
            "RUSTFLAGS",
            "CARGO_ENCODED_RUSTFLAGS",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
        ):
            e.pop(key)
    command = [
        tools["cargo"],
        "build",
        "--manifest-path",
        str(work / "baml_language/Cargo.toml"),
        "-p",
        "bex_engine",
        "--example",
        example,
        "--locked",
        "--jobs",
        str(a.jobs),
    ]
    if a.profile == "release":
        command += ["--release"]
    process = subprocess.Popen(command, env=e, start_new_session=True)
    try:
        code = process.wait(timeout=a.timeout or None)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise SystemExit(
            "Build reached its time limit; rerun to resume cached compilation."
        )
    if code:
        raise SystemExit(code)
    built = (
        target
        / ("release" if a.profile == "release" else "debug")
        / "examples"
        / example
    )
    binary = ROOT / ".cache/hosts" / revision / a.profile / example
    binary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, binary)
    metadata = dict(
        revision=revision,
        profile=a.profile,
        command=command,
        compiler=subprocess.check_output([tools["rustc"], "-Vv"], text=True),
        probe_sha256=sha(probe),
        binary_sha256=sha(binary),
        cargo_lock_sha256=sha(work / "baml_language/Cargo.lock"),
        source_changes="added measurement example only",
    )
    binary.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(binary)


if __name__ == "__main__":
    main()
