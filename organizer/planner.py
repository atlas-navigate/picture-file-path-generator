"""Pass 1: build a full copy plan by scanning the source tree.

This pass is entirely READ-ONLY -- it never creates, modifies, or
deletes anything on disk. That's what makes the resulting CopyPlan
trustworthy as a preview and makes Cancel free/safe: nothing has
happened yet by the time a plan exists.
"""
from __future__ import annotations

import os
from pathlib import Path

from organizer import metadata, metadata_pool
from organizer.classifier import classify_file
from organizer.conflict import NameClaimTracker
from organizer.crash_diagnostics import get_logger
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

    def _bump_progress() -> None:
        nonlocal files_seen
        files_seen += 1
        if progress_callback is not None and files_seen % _PROGRESS_INTERVAL == 0:
            progress_callback(files_seen)

    def _on_walk_error(os_error: OSError) -> None:
        errors.append(ScanError(
            source_path=Path(getattr(os_error, "filename", None) or source_root),
            stage="scan",
            message=str(os_error),
        ))

    def _plan_one(
        path: Path, category: FileCategory, dest_dir: Path,
        capture_dt, date_source,
    ) -> None:
        try:
            stat_result = path.stat()
        except OSError as e:
            errors.append(ScanError(source_path=path, stage="stat", message=str(e)))
            return

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

    # Phase 1: walk and classify only. No metadata is read here -- that
    # happens in Phase 2, off in worker subprocesses, so a native crash
    # in a metadata parser can't take down the directory walk. Each
    # directory's (media files, misc filenames) are stashed for replay
    # in Phase 3 once capture datetimes are known.
    dir_records: list[tuple[Path, list[tuple[Path, FileCategory]], list[str]]] = []
    all_media_items: list[tuple[Path, FileCategory]] = []

    for dirpath, dirnames, filenames in os.walk(
        source_root, onerror=_on_walk_error, followlinks=False
    ):
        dirpath_p = Path(dirpath)
        media_files: list[tuple[Path, FileCategory]] = []
        misc_filenames: list[str] = []

        for filename in filenames:
            path = dirpath_p / filename
            category = classify_file(path)
            if category in (FileCategory.PICTURE, FileCategory.VIDEO):
                media_files.append((path, category))
                all_media_items.append((path, category))
            else:
                misc_filenames.append(filename)

        dir_records.append((dirpath_p, media_files, misc_filenames))

    logger = get_logger()
    logger.info(
        "Directory walk done: %d directories, %d media files -- starting metadata phase",
        len(dir_records), len(all_media_items),
    )

    # Phase 2: resolve capture datetimes for every PICTURE/VIDEO file in
    # parallel, isolated in worker subprocesses -- see metadata_pool for
    # why. A file whose metadata parser crashes ends up in
    # metadata_errors instead of aborting the scan.
    precomputed, metadata_errors = metadata_pool.resolve_capture_datetimes(
        all_media_items, on_item_resolved=_bump_progress,
    )
    errors.extend(metadata_errors)

    logger.info(
        "Metadata phase done: %d resolved, %d errors -- building plan",
        len(precomputed), len(metadata_errors),
    )

    # Phase 3: replay the per-directory grouping (PICTURE/VIDEO first, so
    # a MISC sidecar sharing a video's filename stem -- e.g. a camcorder's
    # "clip1.VOD" plus its "clip1.MOI" index file -- can be grouped into
    # that video's destination folder) using the datetimes resolved above.
    for dirpath_p, media_files, misc_filenames in dir_records:
        video_stem_dest: dict[str, Path] = {}

        for path, category in media_files:
            resolved = precomputed.get(path)
            if resolved is None:
                # Metadata extraction crashed on this file; it's already
                # recorded in errors (stage="metadata"). If it was a
                # VIDEO, any MISC sidecar below simply won't find it in
                # video_stem_dest and falls back to plain Misc/<ext>/
                # grouping instead -- no data loss, just a grouping-
                # quality regression limited to this exceptional case.
                continue
            capture_dt, date_source = resolved
            dest_dir = (
                dest_root
                / _category_subdir(category)
                / str(capture_dt.year)
                / f"{MONTH_NAMES[capture_dt.month]} {capture_dt.year}"
            )
            _plan_one(path, category, dest_dir, capture_dt, date_source)
            if category is FileCategory.VIDEO:
                video_stem_dest[path.stem.lower()] = dest_dir

        for filename in misc_filenames:
            path = dirpath_p / filename
            _bump_progress()

            companion_dest_dir = video_stem_dest.get(path.stem.lower())
            if companion_dest_dir is not None:
                dest_dir = companion_dest_dir
            else:
                # Not a sidecar of any video in this directory: group by
                # file extension under dest/Misc so that similar non-media
                # file types land together (e.g. Misc/pdf/, Misc/txt/),
                # regardless of where they lived in the source tree.
                # Lowercased to match the convention classify_file()
                # already uses for extension comparisons. Extensionless
                # files (and dotfiles like ".bashrc", whose Path.suffix is
                # also "") go into a fixed "no_extension" bucket.
                ext = path.suffix.lower().lstrip(".")
                dest_dir = dest_root / "Misc" / (ext if ext else "no_extension")

            # MISC files never touch Pillow/hachoir -- get_capture_datetime()
            # falls straight through to the mtime fallback for this
            # category -- so it's safe to resolve in-process here rather
            # than routing through the subprocess pool. capture_dt/
            # date_source aren't used for MISC path placement, but
            # PlannedFile still needs them fully populated.
            capture_dt, date_source = metadata.get_capture_datetime(path, FileCategory.MISC)
            _plan_one(path, FileCategory.MISC, dest_dir, capture_dt, date_source)

    if progress_callback is not None and files_seen % _PROGRESS_INTERVAL != 0:
        # Make sure the caller sees the final count even if it doesn't
        # land on an exact interval boundary.
        progress_callback(files_seen)

    summary.error_count = len(errors)

    return CopyPlan(files=files, errors=errors, summary=summary)
