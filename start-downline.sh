#!/usr/bin/env bash
# Run from any directory, including paths containing spaces.
set -u
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Downline needs Python 3.10 or newer."
    echo "Ubuntu / Debian: sudo apt install python3 ffmpeg xdg-utils"
    exit 1
fi
python3 setup-linux.py "$@"
result=$?
if [ "$result" -ne 0 ] && [ -t 0 ]; then
    read -r -p "Press Enter to close..." _
fi
exit "$result"
