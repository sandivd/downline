"""Set up Downline's private Linux tools, then open the local app.

Requires system Python 3.10+, FFmpeg/ffprobe, xdg-open and glibc 2.35+.
No pip, administrator access or system PATH changes are used by this script.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
YTDLP_VERSION = "2026.10.26"
DENO_VERSION = "v2.9.8"
# SHA-256 values from the exact assets in the official GitHub releases.
ASSETS = {
    "x86_64": (
        "yt-dlp_linux", "767ba9dce7052aa196f8b12652f433d76de128ba168966fa84b6394d5e6c6795",
        "deno-x86_64-unknown-linux-gnu.zip", "e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609",
    ),
    "aarch64": (
        "yt-dlp_linux_aarch64", "e87e9533e89fe5889abaa21f5114dfe7756d6aa6219b83551add04d48b18e483",
        "deno-aarch64-unknown-linux-gnu.zip", "d49596c20b9788cf8f5d8ddf644103d4bde56ed239753f0bdb92ba9361d51905",
    ),
}
INSTALL_HINT = "Ubuntu / Debian: sudo apt install python3 ffmpeg xdg-utils"


def check_system(no_browser=False):
    if sys.platform != "linux" or sys.version_info < (3, 10):
        raise RuntimeError("Use Linux with Python 3.10 or newer.")
    arch = platform.machine().lower()
    if arch not in ASSETS:
        raise RuntimeError("This Linux package supports x86_64 and aarch64 (ARM64).")
    libc, version = platform.libc_ver()
    try:
        compatible = libc == "glibc" and tuple(map(int, version.split(".")[:2])) >= (2, 35)
    except ValueError:
        compatible = False
    if not compatible:
        raise RuntimeError("Use a glibc 2.35+ desktop distribution, such as Ubuntu 22.04 or newer. Alpine/musl is not supported.")
    names = ["ffmpeg", "ffprobe"] + ([] if no_browser else ["xdg-open"])
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError("Install these system tools first: " + ", ".join(missing) + ".\n" + INSTALL_HINT)
    return arch


def install_binary(url, expected_hash, destination, member=None):
    """Verify all bytes before atomically installing one executable."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = []
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            archive = Path(stream.name)
            temporary.append(archive)
            digest = hashlib.sha256()
            total = 0
            request = Request(url, headers={"User-Agent": "Downline-Linux-Setup"})
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 256 * 1024 * 1024:
                        raise RuntimeError("The tool download is unexpectedly large. Setup stopped.")
                    digest.update(chunk)
                    stream.write(chunk)
        if digest.hexdigest() != expected_hash:
            raise RuntimeError("Tool checksum mismatch. Nothing was installed. Run the launcher again.")
        executable = archive
        if member:
            with zipfile.ZipFile(archive) as bundle:
                info = bundle.getinfo(member)
                if info.file_size > 256 * 1024 * 1024:
                    raise RuntimeError("The tool archive is unexpectedly large.")
                # Copy only the named binary; never extract archive paths.
                with bundle.open(info) as source, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
                    executable = Path(out.name)
                    temporary.append(executable)
                    shutil.copyfileobj(source, out)
        executable.chmod(0o755)
        os.replace(executable, destination)
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def setup_tools(tools, arch):
    tools = Path(tools)
    tools.mkdir(parents=True, exist_ok=True)
    # FFmpeg is installed by the user's package manager. Links also let the
    # backend's explicit --ffmpeg-location find the system binaries.
    for name in ("ffmpeg", "ffprobe"):
        destination = tools / name
        if destination.is_symlink():
            destination.unlink()
        if not destination.exists():
            destination.symlink_to(Path(shutil.which(name)).resolve())
    engine, engine_hash, deno, deno_hash = ASSETS[arch]
    if not (tools / "yt-dlp").is_file():
        print("Downloading the video engine...", flush=True)
        install_binary(f"https://github.com/yt-dlp/yt-dlp/releases/download/{YTDLP_VERSION}/{engine}",
                       engine_hash, tools / "yt-dlp")
    if not (tools / "deno").is_file():
        print("Downloading the JavaScript runtime...", flush=True)
        install_binary(f"https://github.com/denoland/deno/releases/download/{DENO_VERSION}/{deno}",
                       deno_hash, tools / "deno", member="deno")
    for name in ("yt-dlp", "deno", "ffmpeg", "ffprobe"):
        result = subprocess.run([str(tools / name), "--version" if name in {"yt-dlp", "deno"} else "-version"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"{name} could not start. Check your system dependencies.\n{result.stderr[:500]}")


def main():
    parser = argparse.ArgumentParser(description="Start Downline on Linux")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening a browser")
    parser.add_argument("--setup-only", action="store_true", help="Install and check tools without starting Downline")
    args = parser.parse_args()
    arch = check_system(args.no_browser or args.setup_only)
    runtime = ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    # Two launchers must not install over one another. Release before serving.
    with (runtime / ".linux-setup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        setup_tools(runtime / "tools", arch)
    if args.setup_only:
        print("Downline's Linux tools are ready.")
        return 0
    print("Opening Downline. Keep this terminal open while using the app.\nQuit with Downline's sidebar power button.", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "app.py"), *(["--no-browser"] if args.no_browser else [])])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nDownline could not start: {exc}", file=sys.stderr)
        raise SystemExit(1)
