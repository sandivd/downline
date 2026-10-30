"""Verify setup pins against real upstream downloads, never mock digests.

Set DOWNLINE_BOOTSTRAP_CHECK_DIR to a directory containing python.zip and
python-manifest.json fetched directly from the URLs in setup.ps1.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

import pytest


def test_python_runtime_pin_matches_official_manifest_and_real_archive():
    cached = os.environ.get("DOWNLINE_BOOTSTRAP_CHECK_DIR")
    if not cached:
        pytest.skip("Set DOWNLINE_BOOTSTRAP_CHECK_DIR for the upstream archive check")
    cache = Path(cached)
    setup = (Path(__file__).resolve().parents[1] / "setup.ps1").read_text()
    url = re.search(r"Fetch-File '(https://www\.python\.org/[^']+\.zip)' \$PythonZip", setup)[1]
    expected = re.search(r"\$ExpectedPythonHash = '([a-f0-9]{64})'", setup)[1]
    manifest = json.loads((cache / "python-manifest.json").read_text())
    release = next(item for item in manifest["versions"] if item["id"] == "pythonembed-3.13-64")
    assert url == release["url"], "The pinned archive must be the exact upstream filename"
    assert expected == release["hash"]["sha256"], "The pin must match the hash for that exact URL"
    archive = cache / "python.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert {"python.exe", "pythonw.exe", "python313.dll", "python313.zip", "python313._pth"} <= set(z.namelist())
