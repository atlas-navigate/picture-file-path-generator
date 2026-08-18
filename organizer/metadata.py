"""The single seam that owns the mtime-fallback POLICY.

Nothing else in the codebase should apply the "fall back to filesystem
mtime" rule -- that decision lives here, and only here, so it can never
drift out of sync between pictures and videos.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from organizer import image_metadata, video_metadata
from organizer.models import FileCategory


def get_capture_datetime(path: Path, category: FileCategory) -> tuple[datetime, str]:
    """Determine the best-known capture datetime for a file.

    Never raises and never returns ``None`` for the datetime half of the
    tuple: if no embedded metadata date can be found (or the file isn't
    a picture/video at all), the filesystem mtime is used as a
    guaranteed-available fallback.
    """
    dt = None

    # Defense in depth: image_metadata / video_metadata are already
    # hardened to never raise, but this function is the linchpin of the
    # zero-data-loss guarantee (every file must end up with SOME
    # datetime), so guard the calls here too.
    try:
        if category is FileCategory.PICTURE:
            dt = image_metadata.get_image_datetime(path)
        elif category is FileCategory.VIDEO:
            dt = video_metadata.get_video_datetime(path)
        # category is MISC (or anything else): skip straight to the
        # mtime fallback below, dt stays None.
    except Exception:
        dt = None

    if dt is not None:
        if category is FileCategory.PICTURE:
            return dt, "exif"
        if category is FileCategory.VIDEO:
            return dt, "video_metadata"

    try:
        mtime_dt = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        # Even the filesystem fallback can fail (file deleted/moved/
        # inaccessible between the caller's stat() and this call). This
        # function must still honor its "never raises" contract, so fall
        # back to the current time rather than letting the exception
        # propagate and abort the whole scan.
        mtime_dt = datetime.now()
    return mtime_dt, "filesystem_mtime"
