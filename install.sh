#!/usr/bin/env bash
# Local installer for Photo & Video Organizer: sets up the venv and
# dependencies, and installs a Linux .desktop app-menu launcher.
# Safe to re-run any time (e.g. after `git pull`).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

echo "==> Setting up virtual environment"
if [ ! -d ".venv" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Error: python3 is not installed on this system." >&2
        echo "On Debian/Ubuntu, install it first with:" >&2
        echo "    sudo apt install python3" >&2
        exit 1
    fi

    if ! python3 -m venv .venv; then
        VENV_PKG="$(python3 -c 'import sys; print(f"python3.{sys.version_info.minor}-venv")')"
        echo "Error: failed to create .venv (python3 is installed, but its" >&2
        echo "'venv' module appears to be missing). On Debian/Ubuntu try:" >&2
        echo "    sudo apt install $VENV_PKG" >&2
        exit 1
    fi
fi

if [ ! -x ".venv/bin/pip" ]; then
    echo "Error: .venv exists but has no pip (python3-pip may be missing from" >&2
    echo "this system, so ensurepip silently produced no pip binary during venv" >&2
    echo "creation). On Debian/Ubuntu try:" >&2
    echo "    sudo apt install python3-pip" >&2
    echo "then re-run this script (delete .venv first for a fully clean retry" >&2
    echo "if problems persist)." >&2
    exit 1
fi

echo "==> Installing dependencies"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Checking Qt/X11 runtime libraries"
XCB_CURSOR_OK=1
.venv/bin/python3 -c "import ctypes; ctypes.CDLL('libxcb-cursor.so.0')" >/dev/null 2>&1 || XCB_CURSOR_OK=0

if [ "$XCB_CURSOR_OK" -eq 1 ]; then
    echo "    libxcb-cursor0 (or equivalent) already present -- nothing to do."
elif command -v apt-get >/dev/null 2>&1; then
    echo "==> libxcb-cursor0 is missing. Qt's 'xcb' platform plugin needs it to"
    echo "    run under X11 sessions (not needed under Wayland). Installing it"
    echo "    now -- this changes system packages and may prompt for your"
    echo "    sudo password."
    APT_CMD=(apt-get install -y libxcb-cursor0)
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            APT_CMD=(sudo "${APT_CMD[@]}")
        else
            APT_CMD=()
            echo "Warning: not running as root and 'sudo' is not available --" >&2
            echo "skipping automatic install. If you use this app under an X11" >&2
            echo "session, install libxcb-cursor0 manually." >&2
        fi
    fi
    if [ "${#APT_CMD[@]}" -gt 0 ] && ! "${APT_CMD[@]}"; then
        echo "Warning: automatic install of libxcb-cursor0 failed. If you use" >&2
        echo "this app under an X11 session, install it manually, e.g.:" >&2
        echo "    sudo apt-get install libxcb-cursor0" >&2
    fi
else
    echo "Warning: libxcb-cursor0 (or equivalent) not found, and apt-get is not" >&2
    echo "available to install it automatically. If you use this app under an" >&2
    echo "X11 session (not Wayland), install the package providing" >&2
    echo "libxcb-cursor.so.0 for your distro." >&2
fi

echo "==> Making run.sh executable"
chmod +x run.sh

echo "==> Installing desktop launcher"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
DESKTOP_FILE="$APPS_DIR/photo-video-organizer.desktop"

sed "s|__REPO_ROOT__|$REPO_ROOT|g" \
    "$REPO_ROOT/packaging/photo-video-organizer.desktop.template" \
    > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR"
fi

# Best-effort: also drop a copy on the Desktop for a literal
# double-clickable icon, if the user has a Desktop folder.
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/photo-video-organizer.desktop"
    chmod +x "$HOME/Desktop/photo-video-organizer.desktop"
fi

echo "==> Done. Launch \"Photo & Video Organizer\" from your application"
echo "    menu (or Desktop icon), or run ./run.sh directly."
