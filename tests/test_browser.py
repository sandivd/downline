"""System-default browser dispatch and local service lifecycle regressions."""
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("downline_browser_app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


@pytest.fixture
def windows(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "os", SimpleNamespace(name="nt", replace=os.replace, startfile=Mock()))
    monkeypatch.setattr(app, "default_data_dir", lambda: tmp_path / "data")
    return tmp_path


def test_windows_uses_system_http_association(windows, monkeypatch):
    popen = Mock()
    opener = Mock()
    monkeypatch.setattr(app.subprocess, "Popen", popen)
    monkeypatch.setattr(app.webbrowser, "open", opener)
    url = "http://127.0.0.1:12345/#private-session"
    app.launch_window(url)
    app.os.startfile.assert_called_once_with(url)
    popen.assert_not_called()
    opener.assert_not_called()
    assert not (windows / "data/browser-launch.json").exists()


@pytest.mark.parametrize("saved", [{"executable": "removed/browser.exe"},
                                   {"mode": "custom", "executable": "other/browser.exe"},
                                   {"mode": "default"}, [], None])
def test_saved_browser_preferences_are_ignored(windows, saved):
    config = windows / "data/browser.json"
    app.atomic_json(config, saved)
    original = config.read_bytes()
    url = "http://127.0.0.1:12345/#session"
    app.launch_window(url)
    app.os.startfile.assert_called_once_with(url)
    assert config.read_bytes() == original


def test_default_browser_error_is_actionable(windows):
    app.os.startfile.side_effect = OSError("No association")
    with pytest.raises(RuntimeError, match="default web browser in Windows Settings"):
        app.launch_window("http://127.0.0.1:12345/")


def test_non_windows_uses_default_browser_and_reports_failure(monkeypatch):
    monkeypatch.setattr(app, "os", SimpleNamespace(name="posix"))
    opener = Mock(return_value=True)
    monkeypatch.setattr(app.webbrowser, "open", opener)
    url = "http://127.0.0.1:12345/#session"
    app.launch_window(url)
    opener.assert_called_once_with(url)
    opener.return_value = False
    with pytest.raises(RuntimeError, match="default browser"):
        app.launch_window(url)


def test_reusing_service_does_not_swallow_launch_error_or_start_second_engine(windows, monkeypatch):
    app.atomic_json(windows / "data/instance.json", {"port": 12345, "token": "test-token"})
    monkeypatch.setattr(app.sys, "argv", ["app.py"])
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: io.BytesIO(b'{"app":"Downline"}'))
    launch = Mock(side_effect=OSError("blocked"))
    monkeypatch.setattr(app, "launch_window", launch)
    engine = Mock()
    monkeypatch.setattr(app, "Engine", engine)
    with pytest.raises(OSError, match="blocked"):
        app.main()
    launch.assert_called_once_with("http://127.0.0.1:12345/#test-token")
    engine.assert_not_called()
    assert (windows / "data/instance.json").exists()


def test_first_launch_failure_closes_new_service(windows, monkeypatch):
    monkeypatch.setattr(app.sys, "argv", ["app.py"])
    monkeypatch.setattr(app, "launch_window", Mock(side_effect=RuntimeError("blocked")))
    engine = SimpleNamespace(close=Mock())
    server = SimpleNamespace(server_port=12345, server_close=Mock(), serve_forever=Mock())
    monkeypatch.setattr(app, "Engine", lambda: engine)
    monkeypatch.setattr(app, "ThreadingHTTPServer", lambda *a: server)
    with pytest.raises(RuntimeError, match="blocked"):
        app.main()
    server.serve_forever.assert_not_called()
    engine.close.assert_called_once()
    server.server_close.assert_called_once()
    assert not (windows / "data/instance.json").exists()


def test_no_browser_mode_starts_service_without_opening_a_window(windows, monkeypatch):
    monkeypatch.setattr(app.sys, "argv", ["app.py", "--no-browser"])
    engine = SimpleNamespace(close=Mock())
    server = SimpleNamespace(server_port=12345, server_close=Mock(), serve_forever=Mock())
    monkeypatch.setattr(app, "Engine", lambda: engine)
    monkeypatch.setattr(app, "ThreadingHTTPServer", lambda *a: server)
    app.main()
    app.os.startfile.assert_not_called()
    server.serve_forever.assert_called_once()
    engine.close.assert_called_once()
    server.server_close.assert_called_once()
    assert not (windows / "data/instance.json").exists()
