"""Read a capture datetime out of an image's embedded EXIF metadata.

This module must NEVER raise -- ``get_image_datetime`` is called on
arbitrary, possibly corrupt/truncated files pulled from a messy source
folder, and a single bad file must never abort a scan. Every failure
mode degrades to returning ``None`` so the caller can fall back to the
filesystem mtime.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PIL import Image

try:
    from PIL.ExifTags import IFD
    _EXIF_IFD_TAG = IFD.Exif
except ImportError:  # pragma: no cover - very old Pillow
    _EXIF_IFD_TAG = 0x8769

# Register HEIC/HEIF support with Pillow if pillow_heif is installed.
# Degrade gracefully if it isn't: image classification/copying still
# works fine, we just won't be able to read EXIF out of HEIC files.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# exifread is used as a fallback when Pillow can't find a usable date.
try:
    import exifread
    # exifread's own process_file() catches its internal parsing
    # exceptions (e.g. "no EXIF data" for most PNGs, "file format not
    # recognized" for formats like HEIC/WEBP) and logs them via
    # logging.getLogger("exifread").warning(...) instead of raising.
    # Since this app never calls logging.basicConfig(), those warnings
    # would otherwise leak to stderr on nearly every non-JPEG image --
    # get_image_datetime() already degrades to None/mtime correctly
    # either way, so silence the noise here.
    logging.getLogger("exifread").setLevel(logging.ERROR)
    _EXIFREAD_AVAILABLE = True
except ImportError:
    _EXIFREAD_AVAILABLE = False

_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

# EXIF tag numbers.
_TAG_DATETIME_ORIGINAL = 36867
_TAG_DATETIME_DIGITIZED = 36868
_TAG_DATETIME = 306  # base-IFD "DateTime" (last-modified, not capture, but
                      # still better than nothing as a final EXIF fallback)


def _parse_exif_datetime(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="ignore")
        value = str(value).strip()
        return datetime.strptime(value, _EXIF_DATETIME_FORMAT)
    except (ValueError, TypeError):
        return None


def _get_via_pillow(path: Path) -> datetime | None:
    with Image.open(path) as img:
        exif = img.getexif()
        if exif is None:
            return None

        # DateTimeOriginal / DateTimeDigitized live in the Exif sub-IFD,
        # NOT in the base IFD that getexif() returns directly.
        try:
            exif_ifd = exif.get_ifd(_EXIF_IFD_TAG)
        except Exception:
            exif_ifd = {}

        dt = _parse_exif_datetime(exif_ifd.get(_TAG_DATETIME_ORIGINAL))
        if dt is not None:
            return dt

        dt = _parse_exif_datetime(exif_ifd.get(_TAG_DATETIME_DIGITIZED))
        if dt is not None:
            return dt

        # Last-resort EXIF fallback: base-IFD DateTime (file modified time
        # as recorded by the camera, not the original capture time, but
        # still embedded metadata rather than filesystem mtime).
        dt = _parse_exif_datetime(exif.get(_TAG_DATETIME))
        if dt is not None:
            return dt

        return None


def _get_via_exifread(path: Path) -> datetime | None:
    if not _EXIFREAD_AVAILABLE:
        return None
    with open(path, "rb") as f:
        tags = exifread.process_file(f, details=False)
    for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        value = tags.get(key)
        if value is not None:
            dt = _parse_exif_datetime(str(value))
            if dt is not None:
                return dt
    return None


def get_image_datetime(path: Path) -> datetime | None:
    """Best-effort extraction of a capture datetime from image EXIF data.

    Returns ``None`` (never raises) if no usable EXIF datetime could be
    found, including when the file is missing, corrupt, unsupported, or
    simply has no EXIF data at all.
    """
    try:
        try:
            dt = _get_via_pillow(path)
            if dt is not None:
                return dt
        except Exception:
            pass

        try:
            dt = _get_via_exifread(path)
            if dt is not None:
                return dt
        except Exception:
            pass

        return None
    except Exception:
        # Last-resort safety net: this function must never raise.
        return None
