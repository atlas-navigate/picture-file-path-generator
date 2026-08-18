"""Read a capture datetime out of a video's embedded container metadata.

Like image_metadata.py, this module must NEVER raise. hachoir is known
to throw a wide variety of parser errors on malformed or simply unusual
container files, so every step is defensively wrapped.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

try:
    from hachoir.core import log as hachoir_log
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    # hachoir has its own independent diagnostic-print system (a
    # module-level Log() singleton, not Python's logging module) that
    # writes straight to stderr by default, e.g. "[warn] Skip parser
    # 'MP4File': Unknown MOV file type" while probing a .mov before a
    # later fallback path inside hachoir succeeds. get_video_datetime()
    # already degrades to None/mtime correctly either way, so silence
    # the noise here.
    hachoir_log.log.use_print = False
    _HACHOIR_AVAILABLE = True
except ImportError:
    _HACHOIR_AVAILABLE = False


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # hachoir builds container "creation date" fields (e.g. the
            # MP4/QuickTime seconds-since-1904 creation_time box) straight
            # from the raw UTC-based epoch with no timezone conversion, so
            # the naive datetime it hands back is UTC-valued -- unlike
            # EXIF dates and the mtime fallback elsewhere in this
            # codebase, which are local wall-clock time. Localize it here
            # so all capture-datetime sources agree, then strip tzinfo
            # again to keep the naive-local-datetime shape callers expect.
            value = value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        return value
    try:
        # hachoir sometimes exposes dates as strings; try a couple of
        # common formats before giving up.
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def get_video_datetime(path: Path) -> datetime | None:
    """Best-effort extraction of a capture datetime from video metadata.

    Returns ``None`` (never raises) if hachoir isn't installed, the file
    can't be parsed, or no creation date field is present.
    """
    if not _HACHOIR_AVAILABLE:
        return None

    try:
        parser = createParser(str(path))
        if parser is None:
            return None

        try:
            metadata = extractMetadata(parser)
        except Exception:
            metadata = None

        if metadata is None:
            return None

        try:
            value = metadata.get('creation_date')
        except Exception:
            value = None

        return _coerce_datetime(value)
    except Exception:
        # Last-resort safety net: this function must never raise.
        return None
