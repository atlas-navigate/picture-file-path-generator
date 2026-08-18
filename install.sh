#!/usr/bin/env bash
# Local installer for Photo & Video Organizer: sets up the venv and
# dependencies, and installs a Linux .desktop app-menu launcher.
# Safe to re-run any time (e.g. after `git pull`).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

echo "==> Setting up virtual environment"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || {
        echo "Failed to create .venv -- on Debian/Ubuntu try:" >&2
        echo "    sudo apt install python3.14-venv" >&2
        exit 1
    }
fi

echo "==> Installing dependencies"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

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
