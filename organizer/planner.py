"""Pass 1: build a full copy plan by scanning the source tree.

This pass is entirely READ-ONLY -- it never creates, modifies, or
deletes anything on disk. That's what makes the resulting CopyPlan
trustworthy as a preview and makes Cancel free/safe: nothing has
happened yet by the time a plan exists.
"""
from __future__ import annotations

import os
from pathlib import Path

from organizer import metadata
from organizer.classifier import classify_file
from organizer.conflict import NameClaimTracker
from organizer.models import CopyPlan, FileCategory, PlannedFile, ScanError, ScanSummary

# Hardcoded English month names. Deliberately NOT using calendar.month_name
# or strftime("%B"), both of which are locale-dependent and could silently
# produce non-English folder names on a non-English system locale. The
# destination folder naming convention ("June 2012") must be stable
# regardless of the host OS's locale settings.
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

# How often to invoke progress_callback, in files-seen. Calling back on
# every single file is unnecessary overhead on huge trees (hundreds of
# thousands of files); every 25 files keeps the UI responsive without
# flooding it with updates.
_PROGRESS_INTERVAL = 25


def _category_subdir(category: FileCategory) -> str:
    return "Pictures" if category is FileCategory.PICTURE else "Videos"


def scan_source(source_root: Path, dest_root: Path, progress_callback=None) -> CopyPlan:
    source_root = Path(source_root)
    dest_root = Path(dest_root)

    files: list[PlannedFile] = []
    errors: list[ScanError] = []
    summary = ScanSummary()
    tracker = NameClaimTracker()
    files_seen = 0

    def _on_walk_error(os_error: OSError) -> None:
        errors.append(ScanError(
            source_path=Path(getattr(os_error, "filename", None) or source_root),
            stage="scan",
            message=str(os_error),
        ))

    for dirpath, dirnames, filenames in os.walk(
        source_root, onerror=_on_walk_error, followlinks=False
    ):
        dirpath_p = Path(dirpath)
        for filename in filenames:
            path = dirpath_p / filename
            files_seen += 1

            try:
                stat_result = path.stat()
            except OSError as e:
                errors.append(ScanError(source_path=path, stage="stat", message=str(e)))
                if progress_callback is not None and files_seen % _PROGRESS_INTERVAL == 0:
                    progress_callback(files_seen)
                continue

            category = classify_file(path)

            if category in (FileCategory.PICTURE, FileCategory.VIDEO):
                capture_dt, date_source = metadata.get_capture_datetime(path, category)
                dest_dir = (
                    dest_root
                    / _category_subdir(category)
                    / str(capture_dt.year)
                    / f"{MONTH_NAMES[capture_dt.month]} {capture_dt.year}"
                )
            else:
                # MISC: not date-sorted. Mirror the file's directory
                # structure relative to source_root under dest/Misc, to
                # preserve whatever organization the user already had
                # for non-media files.
                relative_parent_dir = path.parent.relative_to(source_root)
                dest_dir = dest_root / "Misc" / relative_parent_dir
                # capture_dt/date_source aren't used for MISC path
                # placement, but PlannedFile still needs them fully
                # populated so callers never have to special-case None.
                capture_dt, date_source = metadata.get_capture_datetime(path, category)

            final_filename = tracker.claim(dest_dir, path.name)
            was_renamed_for_conflict = final_filename != path.name

            files.append(PlannedFile(
                source_path=path,
                dest_path=dest_dir / final_filename,
                category=category,
                capture_dt=capture_dt,
                date_source=date_source,
                size_bytes=stat_result.st_size,
                was_renamed_for_conflict=was_renamed_for_conflict,
            ))

            summary.counts_by_category[category] = summary.counts_by_category.get(category, 0) + 1
            if category in (FileCategory.PICTURE, FileCategory.VIDEO):
                key = (category, capture_dt.year, capture_dt.month)
                summary.counts_by_year_month[key] = summary.counts_by_year_month.get(key, 0) + 1
            if was_renamed_for_conflict:
                summary.total_conflicts += 1
            summary.total_size_bytes += stat_result.st_size

            if progress_callback is not None and files_seen % _PROGRESS_INTERVAL == 0:
                progress_callback(files_seen)

    if progress_callback is not None and files_seen % _PROGRESS_INTERVAL != 0:
        # Make sure the caller sees the final count even if it doesn't
        # land on an exact interval boundary.
        progress_callback(files_seen)

    summary.error_count = len(errors)

    return CopyPlan(files=files, errors=errors, summary=summary)
