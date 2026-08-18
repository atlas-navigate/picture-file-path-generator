from __future__ import annotations

import errno
import shutil
from pathlib import Path

import pytest

from organizer.copier import execute_plan
from organizer.models import CopyPlan, FileCategory, PlannedFile, ScanSummary
from datetime import datetime


def _make_plan(tmp_path: Path, filenames: list[str]) -> tuple[CopyPlan, dict[str, PlannedFile]]:
    """Builds a simple CopyPlan copying each named file from
    tmp_path/src/<name> to tmp_path/dest/<name>, with real distinct
    byte content per file so byte-identity checks are meaningful."""
    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()

    files = []
    by_name = {}
    for name in filenames:
        source_path = src_dir / name
        content = f"content-of-{name}".encode() * 100  # non-trivial size
        source_path.write_bytes(content)

        dest_path = dest_dir / name
        pf = PlannedFile(
            source_path=source_path,
            dest_path=dest_path,
            category=FileCategory.MISC,
            capture_dt=datetime(2020, 1, 1),
            date_source="filesystem_mtime",
            size_bytes=len(content),
            was_renamed_for_conflict=False,
        )
        files.append(pf)
        by_name[name] = pf

    plan = CopyPlan(files=files, errors=[], summary=ScanSummary())
    return plan, by_name


def test_happy_path_copies_files_byte_identical(tmp_path: Path) -> None:
    plan, by_name = _make_plan(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])

    result = execute_plan(plan)

    assert result.copied_count == 3
    assert result.error_count == 0
    assert result.errors == []
    assert result.aborted is False

    for pf in plan.files:
        assert pf.dest_path.exists()
        assert pf.dest_path.read_bytes() == pf.source_path.read_bytes()

    assert result.total_bytes_copied == sum(pf.size_bytes for pf in plan.files)


def test_recoverable_error_does_not_stop_other_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, by_name = _make_plan(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    failing_source = by_name["b.jpg"].source_path

    real_copy2 = shutil.copy2

    def fake_copy2(src, dst, *args, **kwargs):
        if Path(src) == failing_source:
            raise OSError("simulated generic copy failure")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr("organizer.copier.shutil.copy2", fake_copy2)

    result = execute_plan(plan)

    assert result.aborted is False
    assert result.error_count == 1
    assert result.copied_count == 2

    failed_errors = [e for e in result.errors if e.source_path == failing_source]
    assert len(failed_errors) == 1

    # The other two files must still have been copied successfully.
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        pf = by_name[name]
        if pf.source_path == failing_source:
            assert not pf.dest_path.exists()
        else:
            assert pf.dest_path.exists()
            assert pf.dest_path.read_bytes() == pf.source_path.read_bytes()


def test_enospc_aborts_and_preserves_already_copied_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, by_name = _make_plan(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    failing_source = by_name["b.jpg"].source_path

    real_copy2 = shutil.copy2

    def fake_copy2(src, dst, *args, **kwargs):
        if Path(src) == failing_source:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr("organizer.copier.shutil.copy2", fake_copy2)

    result = execute_plan(plan)

    assert result.aborted is True
    assert result.abort_reason
    assert result.copied_count == 1
    assert str(result.copied_count) in result.abort_reason  # mentions how many succeeded

    # File "a.jpg" (copied before the failure) must remain present and
    # byte-identical -- zero data loss even on a fatal abort.
    a_pf = by_name["a.jpg"]
    assert a_pf.dest_path.exists()
    assert a_pf.dest_path.read_bytes() == a_pf.source_path.read_bytes()

    # The file that triggered ENOSPC must not leave a partial file behind.
    b_pf = by_name["b.jpg"]
    assert not b_pf.dest_path.exists()

    # Processing stopped: "c.jpg" (comes after the failure in plan order)
    # must never have been attempted.
    c_pf = by_name["c.jpg"]
    assert not c_pf.dest_path.exists()

    # Source files are never touched, regardless of outcome.
    for pf in plan.files:
        assert pf.source_path.exists()


def test_cancel_event_stops_processing(tmp_path: Path) -> None:
    import threading

    plan, by_name = _make_plan(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    cancel_event = threading.Event()
    cancel_event.set()  # already cancelled before we even start

    result = execute_plan(plan, cancel_event=cancel_event)

    assert result.aborted is True
    assert result.abort_reason == "Cancelled by user"
    assert result.copied_count == 0
    for pf in plan.files:
        assert not pf.dest_path.exists()


def test_progress_callback_invoked_per_file(tmp_path: Path) -> None:
    plan, _by_name = _make_plan(tmp_path, ["a.jpg", "b.jpg"])

    calls = []
    execute_plan(plan, progress_callback=lambda i, total, name: calls.append((i, total, name)))

    assert calls == [(1, 2, "a.jpg"), (2, 2, "b.jpg")]


def test_log_file_path_passed_through(tmp_path: Path) -> None:
    plan, _by_name = _make_plan(tmp_path, ["a.jpg"])
    log_path = tmp_path / "somelog.txt"

    result = execute_plan(plan, log_file_path=log_path)

    assert result.log_file_path == log_path
