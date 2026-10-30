"""Regressions for exact browser selection and silent-fallback failures."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("downline_browser_app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


@pytest.fixture
def windows(tmp_path, monkeypatch):
    roots = {name: str(tmp_path / str(i)) for i, name in enumerate(
        ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"))}
    monkeypatch.setattr(app, "os", SimpleNamespace(name="nt", environ=roots, replace=os.replace))
    monkeypatch.setattr(app, "default_data_dir", lambda: tmp_path / "data")
    fallback = Mock()
    monkeypatch.setattr(app.webbrowser, "open", fallback)
    return tmp_path, roots, fallback


def browser_file(folder):
    path = folder / "brave.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path.resolve()


def test_custom_executable_is_remembered_and_launched_exactly(windows, monkeypatch):
    tmp, roots, fallback = windows
    custom = browser_file(tmp / "Custom applications/Brave Beta/Application")
    picker = Mock(return_value=custom)
    popen = Mock()
    monkeypatch.setattr(app, "pick_brave_beta", picker)
    monkeypatch.setattr(app.subprocess, "Popen", popen)
    selected = app.resolve_brave_beta(force_choose=True)
    assert selected == custom
    picker.reset_mock()
    assert app.resolve_brave_beta() == custom
    picker.assert_not_called()
    app.launch_window("http://127.0.0.1:12345/#private-session", selected)
    assert popen.call_args.args[0][0] == str(custom)
    assert "--app=http://127.0.0.1:12345/#private-session" in popen.call_args.args[0]
    log = (tmp / "data/browser-launch.json").read_text()
    assert json.loads(log)["executable"] == str(custom)
    assert "private-session" not in log
    fallback.assert_not_called()


def test_force_chooser_overrides_saved_and_detected_locations(windows, monkeypatch):
    tmp, roots, fallback = windows
    old = browser_file(Path(roots["PROGRAMFILES"]) / "BraveSoftware/Brave-Browser-Beta/Application")
    app.atomic_json(tmp / "data/browser.json", {"executable": str(old)})
    custom = browser_file(tmp / "Other Beta/Application")
    picker = Mock(return_value=custom)
    monkeypatch.setattr(app, "pick_brave_beta", picker)
    assert app.resolve_brave_beta(force_choose=True) == custom
    picker.assert_called_once_with(old)
    assert json.loads((tmp / "data/browser.json").read_text())["executable"] == str(custom)


def test_missing_beta_and_cancelled_chooser_never_launch_default(windows, monkeypatch):
    tmp, roots, fallback = windows
    # The ordinary Brave install is intentionally present. It must not be used.
    browser_file(Path(roots["PROGRAMFILES"]) / "BraveSoftware/Brave-Browser/Application")
    picker = Mock(side_effect=RuntimeError("No browser selected"))
    popen = Mock()
    monkeypatch.setattr(app, "pick_brave_beta", picker)
    monkeypatch.setattr(app.subprocess, "Popen", popen)
    with pytest.raises(RuntimeError, match="No browser selected"):
        app.launch_window("http://127.0.0.1:12345/")
    fallback.assert_not_called()
    popen.assert_not_called()
    assert not (tmp / "data/browser.json").exists()


def test_failed_selected_browser_never_launches_default(windows, monkeypatch):
    tmp, roots, fallback = windows
    custom = browser_file(tmp / "Beta/Application")
    monkeypatch.setattr(app.subprocess, "Popen", Mock(side_effect=OSError("cannot launch")))
    with pytest.raises(RuntimeError, match="Choose Brave Beta.cmd"):
        app.launch_window("http://127.0.0.1:12345/", custom)
    fallback.assert_not_called()


def test_removed_saved_executable_prompts_for_replacement(windows, monkeypatch):
    tmp, roots, fallback = windows
    app.atomic_json(tmp / "data/browser.json", {"executable": str(tmp / "removed/brave.exe")})
    custom = browser_file(tmp / "Moved Beta/Application")
    picker = Mock(return_value=custom)
    monkeypatch.setattr(app, "pick_brave_beta", picker)
    assert app.resolve_brave_beta() == custom
    picker.assert_called_once()


def test_invalid_selection_keeps_existing_choice(windows, monkeypatch):
    tmp, roots, fallback = windows
    custom = browser_file(tmp / "Beta/Application")
    app.atomic_json(tmp / "data/browser.json", {"executable": str(custom)})
    wrong = tmp / "setup.exe"
    wrong.touch()
    monkeypatch.setattr(app, "pick_brave_beta", Mock(return_value=wrong))
    with pytest.raises(RuntimeError, match="brave.exe"):
        app.resolve_brave_beta(force_choose=True)
    assert json.loads((tmp / "data/browser.json").read_text())["executable"] == str(custom)


def test_reusing_service_does_not_swallow_launch_error_or_start_second_engine(windows, monkeypatch):
    tmp, roots, fallback = windows
    app.atomic_json(tmp / "data/instance.json", {"port": 12345, "token": "test-token"})
    monkeypatch.setattr(app.sys, "argv", ["app.py"])
    monkeypatch.setattr(app, "resolve_brave_beta", Mock(return_value=tmp / "brave.exe"))
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: io.BytesIO(b'{"app":"Downline"}'))
    monkeypatch.setattr(app, "launch_window", Mock(side_effect=OSError("blocked")))
    engine = Mock()
    monkeypatch.setattr(app, "Engine", engine)
    with pytest.raises(OSError, match="blocked"):
        app.main()
    engine.assert_not_called()
    assert (tmp / "data/instance.json").exists()


def test_first_launch_failure_closes_new_service(windows, monkeypatch):
    tmp, roots, fallback = windows
    monkeypatch.setattr(app.sys, "argv", ["app.py"])
    monkeypatch.setattr(app, "resolve_brave_beta", Mock(return_value=tmp / "brave.exe"))
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
    assert not (tmp / "data/instance.json").exists()
