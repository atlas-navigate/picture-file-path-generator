"""Shared pytest fixtures for the organizer test suite."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest


def _write_jpeg_with_datetime_original(path: Path, dt: datetime) -> None:
    """Write a tiny real JPEG with EXIF DateTimeOriginal set to `dt`.

    Uses Pillow's own Exif/get_ifd API rather than piexif, so it works
    even in environments where piexif isn't installed. piexif is only
    required by tests that explicitly want to exercise the piexif
    write path (those use pytest.importorskip('piexif') themselves).
    """
    from PIL import Image
    from PIL.ExifTags import IFD

    img = Image.new("RGB", (8, 8), color="blue")
    exif = img.getexif()
    exif_ifd = exif.get_ifd(IFD.Exif)
    exif_ifd[36867] = dt.strftime("%Y:%m:%d %H:%M:%S")  # DateTimeOriginal
    exif[IFD.Exif] = exif_ifd
    img.save(path, exif=exif)


@pytest.fixture
def make_jpeg_with_exif_datetime():
    """Factory fixture: make_jpeg_with_exif_datetime(path, dt) -> None.

    Writes a small real JPEG file to `path` with EXIF DateTimeOriginal
    set to `dt` (a datetime with second-level precision, matching the
    EXIF string format).
    """
    return _write_jpeg_with_datetime_original


@pytest.fixture
def make_plain_jpeg():
    """Factory fixture: make_plain_jpeg(path) -> None.

    Writes a small real JPEG file with no EXIF data at all.
    """
    def _make(path: Path) -> None:
        from PIL import Image
        img = Image.new("RGB", (8, 8), color="green")
        img.save(path)
    return _make


@pytest.fixture
def set_mtime():
    """Factory fixture: set_mtime(path, dt) -> None.

    Forces a file's filesystem mtime (and atime) to an exact datetime,
    for deterministic assertions against the mtime-fallback behavior.
    """
    def _set(path: Path, dt: datetime) -> None:
        ts = dt.timestamp()
        os.utime(path, (ts, ts))
    return _set


@pytest.fixture
def piexif_module():
    """Import piexif or skip the test cleanly if it isn't installed."""
    return pytest.importorskip("piexif")
