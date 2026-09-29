"""Install checksum-pinned benchmark tools into the ignored local cache."""

import hashlib
import json
import os
import platform
from pathlib import Path
import ssl
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"


def download(url, destination, expected=None):
    context = ssl.create_default_context(
        cafile=os.environ.get("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt")
    )
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "boundary-instrumentation"}),
        context=context,
        timeout=60,
    ) as src:
        data = src.read()
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest != expected:
        raise ValueError(f"checksum mismatch: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return digest


def main():
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        raise SystemExit(
            "These tool pins target Linux aarch64; add platform-specific pins before running elsewhere."
        )
    pins = json.loads((ROOT / "machinery/tools.json").read_text())
    tools = {}
    for name, pin in pins["tools"].items():
        if name == "rust":
            executable = subprocess.check_output(
                ["rustup", "which", "--toolchain", pin["version"], "rustc"], text=True
            ).strip()
            tools["rustc"] = executable
            tools["cargo"] = str(Path(executable).with_name("cargo"))
            continue
        dest = CACHE / "tools" / name
        executable = dest / pin["executable"]
        archive = CACHE / "downloads" / pin["filename"]
        if not archive.exists():
            download(pin["url"], archive, pin["sha256"])
        if hashlib.sha256(archive.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError(f"cached archive checksum mismatch: {name}")
        if not executable.exists():
            dest.mkdir(parents=True, exist_ok=True)
            if archive.suffix == ".zip":
                with zipfile.ZipFile(archive) as z:
                    z.extractall(dest)
                executable.chmod(0o755)
            else:
                with tarfile.open(archive) as t:
                    t.extractall(dest, filter="data")
        tools[name] = str(executable)
    (CACHE / "tools.local.json").write_text(json.dumps(tools, indent=2) + "\n")
    for name, path in tools.items():
        if name == "cargo":
            continue
        flag = "version" if name == "go" else "--version"
        print(name, subprocess.check_output([path, flag], text=True).strip())


if __name__ == "__main__":
    main()
