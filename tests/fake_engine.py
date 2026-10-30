"""Offline lifecycle fixture; not used by the shipped application."""
import json
from pathlib import Path
import sys
import time

args = sys.argv[1:]
url = args[-1] if args else ""
if "--dump-single-json" in args:
    print(json.dumps({"title": "A quiet afternoon <test>", "uploader": "Studio", "duration": 187,
                      "formats": [{"height": 1080}, {"height": 720}, {"height": None}]}), flush=True)
elif "--update" in args:
    print("Already up to date")
else:
    if "FFFFFFFFFFF" in url:
        print("ERROR: This fixture video is unavailable", flush=True)
        sys.exit(1)
    home = next(a[5:] for a in args if a.startswith("home:"))
    name = "Test video [fixture].mp4"
    output = Path(home) / name
    output.parent.mkdir(parents=True, exist_ok=True)
    print('DL_META:' + json.dumps({"title": "A quiet afternoon <test>", "duration": 187}), flush=True)
    for i in range(1, 5):
        time.sleep(1 if "BBBBBBBBBBB" in url else .06)
        print('DL_PROGRESS:' + json.dumps({"status": "downloading", "downloaded_bytes": i * 25,
                                         "total_bytes": 100, "speed": 2048, "eta": 4-i}), flush=True)
    output.write_bytes(b"local test media")
    print('DL_PROGRESS:' + json.dumps({"status": "finished", "downloaded_bytes": 100, "total_bytes": 100}), flush=True)
    print('DL_FILE:' + json.dumps(str(output)), flush=True)
