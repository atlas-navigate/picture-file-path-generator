# Photo & Video Organizer

A desktop app that scans a messy source folder (on your laptop or an external
drive), and copies its contents into a new, organized folder structure:

```
<destination>/
  Pictures/<year>/<Month year>/    e.g. Pictures/2012/June 2012/
  Videos/<year>/<Month year>/
  Misc/<extension>/                e.g. Misc/pdf/, Misc/txt/, Misc/no_extension/
```

Pictures and videos are sorted by capture date (EXIF for photos, embedded
metadata for videos), falling back to the file's last-modified date when no
usable metadata is found — every picture/video always lands in a Year/Month
folder. Files are **copied**, never moved: the source folder is never
modified. If two files would land at the same destination path, both are
kept — one is renamed with a `.1`, `.2`, ... suffix rather than overwritten.
Zero data loss is the top priority of this app; duplicated output is
acceptable, a lost or silently overwritten file is not.

Misc files (anything that isn't a recognized picture or video extension)
are grouped into a subfolder per file extension, lowercased and without
the leading dot — e.g. `Misc/pdf/`, `Misc/txt/`. Files with no extension
at all are grouped under `Misc/no_extension/`.

Exception: if a Misc file shares its filename (stem) with a video in the
*same* source folder — e.g. a camcorder writing `clip1.VOD` alongside a
`clip1.MOI` index/thumbnail file — that companion file is kept next to
the video instead of being split off into `Misc/<ext>/`.

## Setup

```
python3 -m venv .venv      # if this fails, the required package is
                            # python3.<minor>-venv for your system's python3
                            # (e.g. python3.12-venv on Ubuntu 24.04) -- or just
                            # run ./install.sh, which detects this for you.
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```
python3 main.py
```

Pick a source folder and a separate destination folder, then click
**Scan / Preview**. Review the summary (file counts, Year/Month breakdown,
filename conflicts) before confirming the copy — nothing is written to disk
until you click **Confirm & Copy**.

## Desktop shortcut (Linux)

To install a clickable app-menu launcher (so you don't need a terminal to
run the app after initial setup):

```
./install.sh
```

This creates/updates `.venv` and installs dependencies (same as **Setup**
above), checks for the `libxcb-cursor0` system library that Qt's X11 backend
needs and installs it via `apt` if missing and available (harmless to skip
under Wayland-only setups or non-Debian/Ubuntu distros -- the app may still
work fine there), makes `run.sh` executable, and installs a `.desktop` file
(using a bundled icon at `packaging/icon.svg`) into
`~/.local/share/applications/` (and onto `~/Desktop/` if you have one)
pointing at this repo's `run.sh`. Afterward, "Photo & Video Organizer"
should appear in your desktop environment's application menu with its own
icon. Safe to re-run any time (e.g. after `git pull`, to refresh
dependencies).

## Tests

```
pytest
```

## Known limitation

Re-running the app into a destination folder that already contains output
from a previous run will treat those existing files as name collisions
against themselves, producing spurious `.1`-suffixed duplicates (there's no
content-identity check in this version — only filename collisions are
detected). Copy into a fresh, empty destination folder each run to avoid
this.
