from __future__ import annotations

import functools
import os
from datetime import datetime
from pathlib import Path

from organizer import metadata_pool
from organizer.metadata import get_capture_datetime
from organizer.models import FileCategory


def _touch_jpegs(tmp_path: Path, count: int, make_jpeg_with_exif_datetime) -> list[tuple[Path, FileCategory]]:
    items = []
    for i in range(count):
        p = tmp_path / f"f{i}.jpg"
        make_jpeg_with_exif_datetime(p, datetime(2020, 1, 1 + (i % 27), 12, 0, 0))
        items.append((p, FileCategory.PICTURE))
    return items


def test_happy_path_resolves_every_file(tmp_path: Path, make_jpeg_with_exif_datetime) -> None:
    items = _touch_jpegs(tmp_path, 12, make_jpeg_with_exif_datetime)

    results, errors = metadata_pool.resolve_capture_datetimes(items, batch_size=5)

    assert errors == []
    assert set(results.keys()) == {path for path, _category in items}
    for path, _category in items:
        dt, source = results[path]
        assert source == "exif"
        assert isinstance(dt, datetime)


def test_on_item_resolved_called_once_per_item(tmp_path: Path, make_jpeg_with_exif_datetime) -> None:
    items = _touch_jpegs(tmp_path, 23, make_jpeg_with_exif_datetime)

    calls = []
    metadata_pool.resolve_capture_datetimes(
        items, on_item_resolved=lambda: calls.append(1), batch_size=7,
    )

    assert len(calls) == len(items)


def test_empty_input_returns_empty(tmp_path: Path) -> None:
    results, errors = metadata_pool.resolve_capture_datetimes([])
    assert results == {}
    assert errors == []


# ---- Worker-crash recovery -------------------------------------------------
#
# These simulate a real dead worker process (BrokenProcessPool) rather than
# a Python exception, since that's the exact failure mode this module
# exists to contain -- a Python exception from get_capture_datetime() is
# already handled long before it would reach here (see test_metadata.py /
# test_planner.py). `_worker_fn` is a test-only seam on
# resolve_capture_datetimes(); it must stay a top-level, picklable callable
# since it crosses into a real subprocess -- a closure won't pickle, and
# monkeypatching organizer.metadata from the test process does NOT
# propagate into forkserver-spawned workers (verified empirically: the
# forkserver helper does its own fresh import). functools.partial() of
# this module-level function is what makes a parameterized crash trigger
# picklable across the process boundary.

def _crash_on_names_worker(poison_names: set[str], items: list[tuple[Path, FileCategory]]):
    out = []
    for path, category in items:
        if path.name in poison_names:
            os._exit(1)
        out.append(get_capture_datetime(path, category))
    return out


def test_single_worker_crash_isolated_and_bisected(tmp_path: Path, make_jpeg_with_exif_datetime) -> None:
    """A batch containing one poison file: the crash must not lose or
    mis-blame any of its innocent batch-mates."""
    items = _touch_jpegs(tmp_path, 30, make_jpeg_with_exif_datetime)
    poison_path, _ = items[15]

    results, errors = metadata_pool.resolve_capture_datetimes(
        items, batch_size=10,
        _worker_fn=functools.partial(_crash_on_names_worker, {poison_path.name}),
    )

    assert len(errors) == 1
    assert errors[0].source_path == poison_path
    assert errors[0].stage == "metadata"

    assert set(results.keys()) == {path for path, _c in items if path != poison_path}


def test_crash_in_one_batch_does_not_affect_other_batches(
    tmp_path: Path, make_jpeg_with_exif_datetime,
) -> None:
    """Even though CPython's ProcessPoolExecutor marks every in-flight
    work item BrokenProcessPool when one worker dies (collateral damage
    across concurrently-submitted batches), every non-poison file must
    still end up resolved -- none silently dropped as collateral."""
    items = _touch_jpegs(tmp_path, 40, make_jpeg_with_exif_datetime)
    poison_path, _ = items[5]

    results, errors = metadata_pool.resolve_capture_datetimes(
        items, batch_size=10, max_workers=4,
        _worker_fn=functools.partial(_crash_on_names_worker, {poison_path.name}),
    )

    assert [e.source_path for e in errors] == [poison_path]
    assert len(results) == 39
    assert set(results.keys()) | {poison_path} == {p for p, _c in items}


def test_multiple_independent_crashes_each_isolated(
    tmp_path: Path, make_jpeg_with_exif_datetime,
) -> None:
    items = _touch_jpegs(tmp_path, 25, make_jpeg_with_exif_datetime)
    poison_a = items[3][0].name
    poison_b = items[18][0].name

    results, errors = metadata_pool.resolve_capture_datetimes(
        items, batch_size=6,
        _worker_fn=functools.partial(_crash_on_names_worker, {poison_a, poison_b}),
    )

    error_names = sorted(e.source_path.name for e in errors)
    assert error_names == sorted([poison_a, poison_b])
    assert len(results) == 23
