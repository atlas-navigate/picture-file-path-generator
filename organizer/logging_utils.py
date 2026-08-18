"""Logger setup for the copy phase.

Design choice: rather than reusing a single module-level logger across
repeated calls (which risks stacking up duplicate FileHandlers if
setup_logger() is invoked more than once in a long-lived process, e.g.
the GUI running multiple copy jobs in one session), we create a fresh
Logger instance per call, named uniquely per log file, and explicitly
clear any handlers before attaching the new one. This keeps each
returned logger's output isolated to its own log file with no risk of
cross-talk or duplicate log lines between runs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logger(dest_root: Path) -> tuple[logging.Logger, Path]:
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file_path = dest_root / f"_copy_log_{timestamp}.txt"

    logger_name = f"photo_organizer.{timestamp}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # Guard against duplicate handlers if this ever gets called twice
    # for the same logger name (e.g. same-second timestamp collision).
    if logger.handlers:
        logger.handlers.clear()

    handler = logging.FileHandler(log_file_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger, log_file_path
