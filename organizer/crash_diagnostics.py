"""Process-wide crash visibility for the GUI app.

The app is normally launched via a desktop icon (Terminal=false in
packaging/photo-video-organizer.desktop.template), so stdout/stderr --
and with it, any Python traceback -- is invisible to the user. Worse,
a native crash (segfault) in the C extensions this app depends on
(Pillow, pillow-heif, exifread, hachoir) takes the whole interpreter
down with no Python exception at all. Without this module, a crash
during scanning leaves no trace anywhere for the user to find or
report.

enable_crash_diagnostics() must be called once, as early as possible
in main() -- before QApplication is constructed, so it also covers a
crash during Qt's own startup.
"""
from __future__ import annotations

import faulthandler
import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".photo-video-organizer" / "logs"

# faulthandler requires its target file object to stay open for as
# long as the handler is enabled, which is the app's whole lifetime --
# so this is intentionally a module-level reference, not a local.
_crash_log_file = None

_logger = logging.getLogger("photo_video_organizer")


def _log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    _logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def enable_crash_diagnostics() -> Path:
    """Set up faulthandler, a top-level excepthook, and an app log file.

    Returns the log directory so callers can surface it in the UI if
    they want to (e.g. "logs are at ...") -- not required for the
    crash-visibility fix itself.
    """
    global _crash_log_file

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    _crash_log_file = open(LOG_DIR / "crash.log", "a", encoding="utf-8")
    faulthandler.enable(file=_crash_log_file, all_threads=True)

    _logger.setLevel(logging.INFO)
    if not _logger.handlers:
        handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        _logger.addHandler(handler)
        _logger.propagate = False

    sys.excepthook = _log_uncaught_exception

    return LOG_DIR


def get_logger() -> logging.Logger:
    """The shared app logger, for start/end markers around risky phases
    (e.g. scan start/end) so crash.log's traceback can be matched up
    against what the app was doing at the time."""
    return _logger
