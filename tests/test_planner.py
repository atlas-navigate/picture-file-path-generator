from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from organizer import metadata, planner
from organizer.models import FileCategory, ScanError
from organizer.planner import scan_source


def _build_source_tree(tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime):
    """Builds:
      src/2012_batch/june_photo.jpg      -- EXIF 2012-06-15
      src/2020_batch/aug_photo.jpg       -- EXIF 2020-08-01
      src/no_exif/plain.jpg              -- no EXIF, forced mtime 2019-03-10
      src/misc_stuff/notes.txt           -- misc, grouped under Misc/txt
      src/misc_stuff/report.pdf          -- misc, grouped under Misc/pdf
      src/misc_stuff/LICENSE             -- misc, no extension -> Misc/no_extension
      src/conflict_a/dup.jpg             -- EXIF 2021-01-05 (same month as conflict_b)
      src/conflict_b/dup.jpg             -- EXIF 2021-01-20 (same month -> collides)
    """
    src = tmp_path / "src"
    dest = tmp_path / "dest"

    (src / "2012_batch").mkdir(parents=True)
    (src / "2020_batch").mkdir(parents=True)
    (src / "no_exif").mkdir(parents=True)
    (src / "misc_stuff").mkdir(parents=True)
    (src / "conflict_a").mkdir(parents=True)
    (src / "conflict_b").mkdir(parents=True)

    june_photo = src / "2012_batch" / "june_photo.jpg"
    make_jpeg_with_exif_datetime(june_photo, datetime(2012, 6, 15, 10, 0, 0))

    aug_photo = src / "2020_batch" / "aug_photo.jpg"
    make_jpeg_with_exif_datetime(aug_photo, datetime(2020, 8, 1, 9, 30, 0))

    plain_photo = src / "no_exif" / "plain.jpg"
    from PIL import Image
    Image.new("RGB", (8, 8), color="yellow").save(plain_photo)
    forced_mtime = datetime(2019, 3, 10, 12, 0, 0)
    set_mtime(plain_photo, forced_mtime)

    notes = src / "misc_stuff" / "notes.txt"
    notes.write_text("just some notes")

    report = src / "misc_stuff" / "report.pdf"
    report.write_text("not a real pdf, just bytes for the test")

    no_ext_file = src / "misc_stuff" / "LICENSE"
    no_ext_file.write_text("no extension on this one")

    dup_a = src / "conflict_a" / "dup.jpg"
    make_jpeg_with_exif_datetime(dup_a, datetime(2021, 1, 5, 8, 0, 0))

    dup_b = src / "conflict_b" / "dup.jpg"
    make_jpeg_with_exif_datetime(dup_b, datetime(2021, 1, 20, 8, 0, 0))

    return src, dest, {
        "june_photo": june_photo,
        "aug_photo": aug_photo,
        "plain_photo": plain_photo,
        "forced_mtime": forced_mtime,
        "notes": notes,
        "report": report,
        "no_ext_file": no_ext_file,
        "dup_a": dup_a,
        "dup_b": dup_b,
    }


def test_scan_source_builds_correct_dest_paths(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    june_pf = by_source[files["june_photo"]]
    assert june_pf.category == FileCategory.PICTURE
    assert june_pf.date_source == "exif"
    assert june_pf.dest_path == dest / "Pictures" / "2012" / "June 2012" / "june_photo.jpg"

    aug_pf = by_source[files["aug_photo"]]
    assert aug_pf.dest_path == dest / "Pictures" / "2020" / "August 2020" / "aug_photo.jpg"

    plain_pf = by_source[files["plain_photo"]]
    assert plain_pf.date_source == "filesystem_mtime"
    assert plain_pf.capture_dt == files["forced_mtime"]
    assert plain_pf.dest_path == dest / "Pictures" / "2019" / "March 2019" / "plain.jpg"


def test_scan_source_misc_groups_by_extension(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    notes_pf = by_source[files["notes"]]
    assert notes_pf.category == FileCategory.MISC
    assert notes_pf.dest_path == dest / "Misc" / "txt" / "notes.txt"

    report_pf = by_source[files["report"]]
    assert report_pf.category == FileCategory.MISC
    assert report_pf.dest_path == dest / "Misc" / "pdf" / "report.pdf"

    no_ext_pf = by_source[files["no_ext_file"]]
    assert no_ext_pf.category == FileCategory.MISC
    assert no_ext_pf.dest_path == dest / "Misc" / "no_extension" / "LICENSE"


def test_scan_source_misc_file_grouped_with_matching_video_stem(
    tmp_path: Path, set_mtime
) -> None:
    """A MISC file sharing a video's filename stem in the same directory
    (e.g. a JVC .VOD clip plus its .MOI index/thumbnail file) should land
    next to that video, not in Misc/<ext>/."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "camcorder").mkdir(parents=True)

    clip = src / "camcorder" / "clip1.VOD"
    clip.write_bytes(b"not a real video, just bytes for the test")
    set_mtime(clip, datetime(2015, 7, 4, 12, 0, 0))

    # Case differs from the clip's stem on purpose, to also exercise
    # case-insensitive stem matching.
    companion = src / "camcorder" / "CLIP1.moi"
    companion.write_bytes(b"companion index file")

    unrelated = src / "camcorder" / "notes.txt"
    unrelated.write_text("unrelated misc file, no stem match")

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    clip_pf = by_source[clip]
    assert clip_pf.category == FileCategory.VIDEO
    assert clip_pf.dest_path == dest / "Videos" / "2015" / "July 2015" / "clip1.VOD"

    companion_pf = by_source[companion]
    assert companion_pf.category == FileCategory.MISC
    assert companion_pf.dest_path == dest / "Videos" / "2015" / "July 2015" / "CLIP1.moi"

    unrelated_pf = by_source[unrelated]
    assert unrelated_pf.category == FileCategory.MISC
    assert unrelated_pf.dest_path == dest / "Misc" / "txt" / "notes.txt"

    # Grouping is per-directory only: counts_by_category still reflects
    # the companion as MISC, not VIDEO.
    assert plan.summary.counts_by_category[FileCategory.VIDEO] == 1
    assert plan.summary.counts_by_category[FileCategory.MISC] == 2


def test_scan_source_misc_stem_match_scoped_to_same_directory(
    tmp_path: Path, set_mtime
) -> None:
    """A MISC file must NOT be grouped with a same-named video that lives
    in a different source directory."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "dir_a").mkdir(parents=True)
    (src / "dir_b").mkdir(parents=True)

    clip = src / "dir_a" / "clip1.VOD"
    clip.write_bytes(b"video bytes")
    set_mtime(clip, datetime(2015, 7, 4, 12, 0, 0))

    lookalike = src / "dir_b" / "clip1.moi"
    lookalike.write_bytes(b"unrelated file with a coincidentally matching stem")

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    lookalike_pf = by_source[lookalike]
    assert lookalike_pf.category == FileCategory.MISC
    assert lookalike_pf.dest_path == dest / "Misc" / "moi" / "clip1.moi"


def test_scan_source_conflict_produces_disambiguated_names(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    dup_a_pf = by_source[files["dup_a"]]
    dup_b_pf = by_source[files["dup_b"]]

    # Both land in the same Pictures/2021/January 2021 dir since both
    # dated to January 2021 -> must collide and be disambiguated.
    assert dup_a_pf.dest_path.parent == dup_b_pf.dest_path.parent
    dest_names = sorted([dup_a_pf.dest_path.name, dup_b_pf.dest_path.name])
    assert dest_names == ["dup.1.jpg", "dup.jpg"]

    # Exactly one of the two should be flagged as renamed for conflict.
    renamed_flags = sorted([dup_a_pf.was_renamed_for_conflict, dup_b_pf.was_renamed_for_conflict])
    assert renamed_flags == [False, True]

    # Neither source file is lost: both appear in the plan with distinct
    # dest paths.
    assert dup_a_pf.dest_path != dup_b_pf.dest_path


def test_scan_source_summary_counts(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    plan = scan_source(src, dest)
    summary = plan.summary

    # 5 pictures total: june_photo, aug_photo, plain_photo, dup_a, dup_b
    assert summary.counts_by_category[FileCategory.PICTURE] == 5
    assert summary.counts_by_category[FileCategory.MISC] == 3
    assert FileCategory.VIDEO not in summary.counts_by_category or summary.counts_by_category[FileCategory.VIDEO] == 0

    assert summary.counts_by_year_month[(FileCategory.PICTURE, 2012, 6)] == 1
    assert summary.counts_by_year_month[(FileCategory.PICTURE, 2020, 8)] == 1
    assert summary.counts_by_year_month[(FileCategory.PICTURE, 2019, 3)] == 1
    assert summary.counts_by_year_month[(FileCategory.PICTURE, 2021, 1)] == 2

    assert summary.total_conflicts == 1
    assert summary.error_count == 0

    total_size = sum(pf.size_bytes for pf in plan.files)
    assert summary.total_size_bytes == total_size

    # Sanity: number of PlannedFiles matches total file count on disk.
    assert len(plan.files) == 8


def test_scan_source_all_source_files_accounted_for(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    """Zero-data-loss sanity check: every real file under source_root
    must appear exactly once in the plan (or once in errors)."""
    src, dest, _files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    all_source_files = {p for p in src.rglob("*") if p.is_file()}

    plan = scan_source(src, dest)
    planned_sources = {pf.source_path for pf in plan.files}
    error_sources = {e.source_path for e in plan.errors}

    # Every real file is accounted for exactly once, either in the plan
    # or in errors -- nothing is silently dropped.
    assert planned_sources | error_sources == all_source_files
    assert planned_sources.isdisjoint(error_sources)
    assert not plan.errors  # nothing should have errored in this scenario


def test_scan_source_progress_callback_invoked(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, _files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    calls = []
    scan_source(src, dest, progress_callback=lambda n: calls.append(n))

    assert len(calls) >= 1
    # Final call should report the true total number of files seen.
    total_files = sum(1 for p in src.rglob("*") if p.is_file())
    assert calls[-1] == total_files


def test_scan_source_never_writes_to_disk(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime
) -> None:
    src, dest, _files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)

    scan_source(src, dest)

    # Pass 1 must be entirely read-only: dest_root must not have been
    # created just from planning.
    assert not dest.exists()


def test_scan_source_metadata_crash_recorded_as_error_and_scan_continues(
    tmp_path: Path, make_jpeg_with_exif_datetime, set_mtime, monkeypatch
) -> None:
    """If metadata extraction crashes a worker for one file (see
    organizer.metadata_pool), scan_source() must record it as a
    ScanError(stage="metadata") rather than losing it or aborting the
    whole scan -- every other file must still be planned normally."""
    src, dest, files = _build_source_tree(tmp_path, make_jpeg_with_exif_datetime, set_mtime)
    crashed_path = files["june_photo"]

    def fake_resolve(media_items, on_item_resolved=None, **kwargs):
        results = {}
        errors = []
        for path, category in media_items:
            if path == crashed_path:
                errors.append(ScanError(
                    source_path=path, stage="metadata",
                    message="Parser crashed (native error) while reading metadata; file skipped",
                ))
            else:
                results[path] = metadata.get_capture_datetime(path, category)
            if on_item_resolved is not None:
                on_item_resolved()
        return results, errors

    monkeypatch.setattr(planner.metadata_pool, "resolve_capture_datetimes", fake_resolve)

    plan = scan_source(src, dest)

    crashed_errors = [e for e in plan.errors if e.source_path == crashed_path]
    assert len(crashed_errors) == 1
    assert crashed_errors[0].stage == "metadata"

    planned_sources = {pf.source_path for pf in plan.files}
    assert crashed_path not in planned_sources
    # Everything else in the fixture tree still made it into the plan.
    assert files["aug_photo"] in planned_sources
    assert files["plain_photo"] in planned_sources
    assert files["dup_a"] in planned_sources
    assert files["dup_b"] in planned_sources
    assert len(plan.files) == 7  # 8 total fixture files minus the 1 crashed one


def test_scan_source_video_metadata_crash_degrades_sidecar_grouping(
    tmp_path: Path, set_mtime, monkeypatch
) -> None:
    """Documents the accepted edge case: if a VIDEO file's metadata
    extraction crashes, its MISC sidecar can't be grouped next to it
    (the video's dest folder is never known) and falls back to plain
    Misc/<ext>/ grouping instead. No data loss -- the sidecar is still
    fully accounted for."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "camcorder").mkdir(parents=True)

    clip = src / "camcorder" / "clip1.VOD"
    clip.write_bytes(b"not a real video, just bytes for the test")
    set_mtime(clip, datetime(2015, 7, 4, 12, 0, 0))

    companion = src / "camcorder" / "CLIP1.moi"
    companion.write_bytes(b"companion index file")

    def fake_resolve(media_items, on_item_resolved=None, **kwargs):
        results = {}
        errors = []
        for path, category in media_items:
            if path == clip:
                errors.append(ScanError(
                    source_path=path, stage="metadata",
                    message="Parser crashed (native error) while reading metadata; file skipped",
                ))
            else:
                results[path] = metadata.get_capture_datetime(path, category)
            if on_item_resolved is not None:
                on_item_resolved()
        return results, errors

    monkeypatch.setattr(planner.metadata_pool, "resolve_capture_datetimes", fake_resolve)

    plan = scan_source(src, dest)
    by_source = {pf.source_path: pf for pf in plan.files}

    assert clip not in by_source
    assert any(e.source_path == clip and e.stage == "metadata" for e in plan.errors)

    # Sidecar is still fully accounted for, just not grouped with the
    # (unresolvable) video's destination folder.
    companion_pf = by_source[companion]
    assert companion_pf.category == FileCategory.MISC
    assert companion_pf.dest_path == dest / "Misc" / "moi" / "CLIP1.moi"
