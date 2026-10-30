import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("downline_app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
URL = "https://www.youtube.com/watch?v=AAAAAAAAAAA"


def wait_for(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.03)
    raise AssertionError("Condition did not become true in time")


@pytest.fixture
def engine(tmp_path):
    e = app.Engine(tmp_path / "data", tmp_path / "missing-tools",
                   [sys.executable, str(ROOT / "tests/fake_engine.py")])
    e.settings.update(destination=str(tmp_path / "downloads"), concurrency=1)
    yield e
    e.close()
    wait_for(lambda: not e.processes)


@pytest.mark.parametrize("url,expected", [
    ("https://youtu.be/AAAAAAAAAAA?si=tracking", URL),
    ("youtube.com/shorts/AAAAAAAAAAA?feature=share", URL),
    ("https://www.youtube.com/watch?v=AAAAAAAAAAA&list=secret&index=5", URL),
    ("https://m.youtube.com/live/AAAAAAAAAAA", URL),
    ("https://m.pornhub.com/view_video.php?viewkey=ph1234567&tracking=x",
     "https://www.pornhub.com/view_video.php?viewkey=ph1234567"),
])
def test_supported_video_urls_are_canonicalized(url, expected):
    assert app.validate_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/video", "file:///tmp/test.mp4", "https://youtube.com.evil.example/watch?v=AAAAAAAAAAA",
    "https://user:password@youtube.com/watch?v=AAAAAAAAAAA", "https://youtube.com:444/watch?v=AAAAAAAAAAA",
    "https://youtube.com/playlist?list=abc", "https://youtube.com/watch?v=bad",
    "https://pornhub.com/", "https://youtube.com/watch?v=AAAAAAAAAAA\n--exec=bad",
])
def test_other_urls_and_command_injection_are_rejected(url):
    with pytest.raises(ValueError):
        app.validate_url(url)


def test_metadata_and_duplicate_queue_entries(engine):
    info = engine.analyze(URL)
    assert info["title"] == "A quiet afternoon <test>"
    assert info["qualities"] == [1080, 720]
    engine.paused = True
    assert engine.enqueue({"urls": [URL, "https://youtu.be/AAAAAAAAAAA"]}) == {"added": 1}
    assert engine.enqueue({"urls": [URL]}) == {"added": 0}
    assert engine.enqueue({"urls": [URL], "format": "mp3"}) == {"added": 1}
    assert all(j["status"] == "queued" for j in engine.jobs)


def test_download_completion_uses_final_file_path(engine):
    engine.enqueue({"urls": [URL]})
    wait_for(lambda: engine.jobs[0]["status"] in app.TERMINAL)
    job = engine.jobs[0]
    assert job["status"] == "completed", job["error"]
    assert job["progress"] == 100
    assert Path(job["path"]).read_bytes() == b"local test media"
    assert job["title"] == "A quiet afternoon <test>"


def test_failure_is_visible_and_retry_does_not_duplicate(engine):
    engine.enqueue({"urls": ["https://youtu.be/FFFFFFFFFFF"]})
    wait_for(lambda: engine.jobs[0]["status"] == "failed")
    job = engine.jobs[0]
    assert "unavailable" in job["error"]
    engine.paused = True
    engine.action("retry", job["id"])
    assert len(engine.jobs) == 1
    assert job["status"] == "queued"
    assert job["error"] == ""


def test_cancel_stops_active_process_and_paused_queue(engine):
    engine.enqueue({"urls": ["https://youtu.be/BBBBBBBBBBB", URL]})
    wait_for(lambda: engine.jobs[0]["status"] == "downloading")
    proc = engine.processes[engine.jobs[0]["id"]]
    engine.action("pause")
    engine.action("cancel", engine.jobs[0]["id"])
    wait_for(lambda: engine.jobs[0]["status"] == "cancelled")
    assert proc.poll() is not None
    assert engine.jobs[1]["status"] == "queued"
    engine.action("pause")
    wait_for(lambda: engine.jobs[1]["status"] == "completed")


def test_clearing_history_keeps_downloaded_files(engine):
    engine.enqueue({"urls": [URL]})
    wait_for(lambda: engine.jobs[0]["status"] == "completed")
    path = Path(engine.jobs[0]["path"])
    engine.action("clear")
    assert not engine.jobs
    assert path.is_file()


def test_original_cookie_export_is_not_modified_and_copy_is_removed(engine, tmp_path):
    cookie_file = tmp_path / "account.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    engine.settings["cookies"] = str(cookie_file)
    original = cookie_file.read_bytes()
    engine.analyze(URL)
    engine.enqueue({"urls": [URL]})
    wait_for(lambda: engine.jobs[0]["status"] == "completed")
    wait_for(lambda: not engine.processes)
    assert cookie_file.read_bytes() == original
    assert not list(Path(engine.settings["destination"]).rglob("cookies.txt"))


def test_disabling_history_does_not_persist_video_urls(engine):
    engine.paused = True
    engine.enqueue({"urls": [URL]})
    engine.update_settings({"remember_history": False})
    data = json.loads((engine.data_dir / "state.json").read_text())
    assert data["jobs"] == []
    assert len(engine.jobs) == 1


def test_restart_does_not_autostart_interrupted_downloads(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "state.json").write_text(json.dumps({"settings": {}, "jobs": [
        {"id": "fixture", "status": "downloading"}, {"id": "fixture2", "status": "queued"}]}))
    e = app.Engine(data_dir, tmp_path / "tools")
    try:
        assert all(j["status"] == "cancelled" for j in e.jobs)
    finally:
        e.close()


def test_local_api_requires_token_and_correct_origin(engine):
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    server.engine, server.token = engine, "test-session-token"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(HTTPError) as err:
            urlopen(base + "/api/state")
        assert err.value.code == 401
        with pytest.raises(HTTPError) as err:
            urlopen(Request(base + "/api/state", headers={"X-Downline-Token": server.token, "Origin": "https://evil.example"}))
        assert err.value.code == 403
        with urlopen(Request(base + "/api/state", headers={"X-Downline-Token": server.token})) as response:
            assert "jobs" in json.load(response)
        with urlopen(base + "/") as response:
            assert b"Save it for later" in response.read()
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with pytest.raises(HTTPError) as err:
            urlopen(base + "/app.py")
        assert err.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("fmt", ["mp4", "mkv", "mp3"])
def test_real_yt_dlp_download_and_ffmpeg_conversion(tmp_path, monkeypatch, fmt):
    pytest.importorskip("yt_dlp")
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for the real-media integration test")
    media = tmp_path / "fixture.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)], check=True)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    e = app.Engine(tmp_path / "data", tmp_path / "not-present", [sys.executable, "-m", "yt_dlp"])
    e.settings.update(destination=str(tmp_path / "output"), concurrency=1)
    local_url = f"http://127.0.0.1:{server.server_port}/fixture.mp4"
    # Only this isolated test allows localhost as a source. Production validation
    # accepts video URLs from the six supported platforms exclusively.
    monkeypatch.setattr(app, "validate_url", lambda u: u)
    try:
        e.enqueue({"urls": [local_url], "format": fmt, "quality": "1080"})
        wait_for(lambda: e.jobs[0]["status"] in app.TERMINAL, timeout=20)
        job = e.jobs[0]
        assert job["status"] == "completed", job["error"]
        output = Path(job["path"])
        assert output.suffix == "." + fmt
        probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_streams", "-of", "json", str(output)],
                               check=True, capture_output=True, text=True)
        streams = json.loads(probe.stdout)["streams"]
        assert any(s["codec_type"] == "audio" for s in streams)
        assert (any(s["codec_type"] == "video" for s in streams)) == (fmt != "mp3")
        if fmt == "mp4":
            assert output.read_bytes() == media.read_bytes()
        if fmt == "mp3":
            assert streams[0]["codec_name"] == "mp3"
    finally:
        e.close()
        server.shutdown()
        server.server_close()
