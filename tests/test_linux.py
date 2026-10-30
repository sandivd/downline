"""Linux bootstrap integrity, offline relaunch, and real-media integration."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux launcher")
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def setup():
    return load("downline_linux_setup", ROOT / "setup-linux.py")


def test_corrupt_download_does_not_replace_existing_tool(setup, tmp_path, monkeypatch):
    target = tmp_path / "yt-dlp"
    target.write_bytes(b"working version")
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: io.BytesIO(b"corrupt download"))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        setup.install_binary("https://example.invalid/tool", "0" * 64, target)
    assert target.read_bytes() == b"working version"
    assert list(tmp_path.iterdir()) == [target]


def test_verified_archive_installs_only_named_binary(setup, tmp_path, monkeypatch):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("deno", b"verified executable")
        archive.writestr("../escaped.txt", b"do not extract")
    content = data.getvalue()
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: io.BytesIO(content))
    target = tmp_path / "tools/deno"
    setup.install_binary("https://example.invalid/deno.zip", hashlib.sha256(content).hexdigest(), target, "deno")
    assert target.read_bytes() == b"verified executable"
    assert target.stat().st_mode & 0o111 == 0o111
    assert not (tmp_path / "escaped.txt").exists()
    assert list(target.parent.iterdir()) == [target]


def test_partial_network_download_is_cleaned_up(setup, tmp_path, monkeypatch):
    class Interrupted(io.BytesIO):
        def read(self, size):
            if self.tell():
                raise OSError("connection lost")
            return super().read(size)
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: Interrupted(b"partial"))
    target = tmp_path / "yt-dlp"
    with pytest.raises(OSError, match="connection lost"):
        setup.install_binary("https://example.invalid/tool", "0" * 64, target)
    assert list(tmp_path.iterdir()) == []


def test_relaunch_reuses_installed_tools_and_refreshes_ffmpeg_links(setup, tmp_path, monkeypatch):
    tools = tmp_path / "app with spaces/runtime/tools"
    tools.mkdir(parents=True)
    for name in ("yt-dlp", "deno"):
        path = tools / name
        path.write_text("#!/bin/sh\necho version\n")
        path.chmod(0o755)
    system = tmp_path / "system"
    system.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        path = system / name
        path.write_text("#!/bin/sh\necho ffmpeg\n")
        path.chmod(0o755)
        (tools / name).symlink_to(tmp_path / "old removed location")
    monkeypatch.setattr(setup.shutil, "which", lambda name: str(system / name))
    monkeypatch.setattr(setup, "install_binary", lambda *a, **k: pytest.fail("Offline relaunch attempted a download"))
    setup.setup_tools(tools, "x86_64")
    assert (tools / "ffmpeg").resolve() == system / "ffmpeg"
    assert (tools / "ffprobe").resolve() == system / "ffprobe"


@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_supported_architectures(setup, monkeypatch, arch):
    monkeypatch.setattr(setup.platform, "machine", lambda: arch)
    monkeypatch.setattr(setup.platform, "libc_ver", lambda: ("glibc", "2.35"))
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    assert setup.check_system() == arch


def test_missing_ffmpeg_is_reported_before_downloading(setup, monkeypatch):
    monkeypatch.setattr(setup.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(setup.platform, "libc_ver", lambda: ("glibc", "2.35"))
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Install these system tools first: ffmpeg, ffprobe, xdg-open"):
        setup.check_system()


@pytest.mark.parametrize("libc,version", [("musl", "1.2"), ("glibc", "2.31"), ("", "")])
def test_incompatible_linux_is_reported(setup, monkeypatch, libc, version):
    monkeypatch.setattr(setup.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(setup.platform, "libc_ver", lambda: (libc, version))
    with pytest.raises(RuntimeError, match="glibc 2.35"):
        setup.check_system()


@pytest.mark.parametrize("fmt", ["mp4", "mkv", "mp3"])
def test_real_linux_tools_download_and_convert(tmp_path, monkeypatch, fmt):
    tools = ROOT / "runtime/tools"
    if not all((tools / name).is_file() for name in ("yt-dlp", "deno", "ffmpeg", "ffprobe")):
        pytest.skip("Run bash start-downline.sh --setup-only for real-tool checks")
    app = load("downline_linux_media", ROOT / "app.py")
    fixture = tmp_path / "fixture.mp4"
    subprocess.run([str(tools / "ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=160x90:r=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(fixture)], check=True)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    engine = app.Engine(tmp_path / "state", tools)
    engine.settings.update(destination=str(tmp_path / "downloads"), concurrency=1)
    # Permit localhost solely inside this fixture; production validation is unchanged.
    monkeypatch.setattr(app, "validate_url", lambda url: url)
    try:
        assert engine.dependencies() == {"engine": True, "ffmpeg": True, "javascript": True}
        engine.enqueue({"urls": [f"http://127.0.0.1:{server.server_port}/fixture.mp4"], "format": fmt, "quality": "1080"})
        deadline = time.monotonic() + 30
        while engine.jobs[0]["status"] not in app.TERMINAL and time.monotonic() < deadline:
            time.sleep(0.05)
        job = engine.jobs[0]
        assert job["status"] == "completed", job["error"]
        output = Path(job["path"])
        assert output.suffix == "." + fmt
        probe = subprocess.run([str(tools / "ffprobe"), "-v", "quiet", "-show_streams", "-of", "json", str(output)],
                               check=True, capture_output=True, text=True)
        streams = json.loads(probe.stdout)["streams"]
        assert any(s["codec_type"] == "audio" for s in streams)
        assert any(s["codec_type"] == "video" for s in streams) == (fmt != "mp3")
    finally:
        engine.close()
        server.shutdown()
        server.server_close()
