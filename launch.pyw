"""Windows launcher: log unexpected startup failures and show a useful dialog."""
import ctypes
import os
from pathlib import Path
import runpy
import sys
import traceback

try:
    runpy.run_path(str(Path(__file__).resolve().parent / "app.py"), run_name="__main__")
except Exception:
    data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Downline"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "startup.log"
    log_path.write_text(traceback.format_exc(), encoding="utf-8")
    ctypes.windll.user32.MessageBoxW(None, "Downline could not start.\n\nDetails were saved to:\n" + str(log_path), "Downline", 0x10)
    sys.exit(1)
