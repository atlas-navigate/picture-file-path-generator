#!/usr/bin/env bash
# Self-locating launcher for Photo & Video Organizer.
#
# main.py is not an installed package -- it's run as `python main.py`
# with a relative script name, which makes Python resolve
# `from gui.main_window import MainWindow` against the current working
# directory at import time. That's why the process's cwd must be the
# repo root. Resolving that root from this script's own location
# (rather than trusting the caller's cwd) is what lets a .desktop
# launcher invoke this script from anywhere on the system.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

if [ ! -x ".venv/bin/python" ]; then
    echo "Error: .venv not found in $REPO_ROOT. Run ./install.sh first." >&2
    exit 1
fi

exec .venv/bin/python main.py
