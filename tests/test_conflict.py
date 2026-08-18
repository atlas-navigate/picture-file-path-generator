from __future__ import annotations

from pathlib import Path

import pytest

from organizer.conflict import NameClaimTracker, insert_suffix


# --- insert_suffix -----------------------------------------------------

def test_insert_suffix_basic() -> None:
    assert insert_suffix("IMG_0001.jpg", 1) == "IMG_0001.1.jpg"
    assert insert_suffix("IMG_0001.jpg", 2) == "IMG_0001.2.jpg"


def test_insert_suffix_extensionless() -> None:
    assert insert_suffix("README", 1) == "README.1"
    assert insert_suffix("README", 2) == "README.2"


def test_insert_suffix_multiple_dots_preserves_last_extension() -> None:
    # Only the LAST dot separates stem/extension.
    assert insert_suffix("archive.tar.gz", 1) == "archive.tar.1.gz"


def test_insert_suffix_dotfile_with_a_dot_in_it() -> None:
    # ".bashrc" DOES contain a dot (the leading one), so rsplit('.', 1)
    # splits it into stem="" / ext="bashrc" and the suffix is inserted
    # in that slot -- this documents the concrete, well-defined behavior
    # for that edge case (a genuinely extensionless name like "README"
    # is covered separately above).
    assert insert_suffix(".bashrc", 1) == ".1.bashrc"


# --- NameClaimTracker ----------------------------------------------------

def test_two_conflicting_files_second_gets_suffix(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    tracker = NameClaimTracker()

    first = tracker.claim(dest_dir, "a.jpg")
    second = tracker.claim(dest_dir, "a.jpg")

    assert first == "a.jpg"
    assert second == "a.1.jpg"


def test_three_conflicting_files_incrementing_suffixes(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    tracker = NameClaimTracker()

    results = [tracker.claim(dest_dir, "a.jpg") for _ in range(3)]

    assert results == ["a.jpg", "a.1.jpg", "a.2.jpg"]


def test_case_insensitive_collision(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    tracker = NameClaimTracker()

    first = tracker.claim(dest_dir, "A.jpg")
    second = tracker.claim(dest_dir, "a.JPG")

    assert first == "A.jpg"
    # Must be treated as a collision even though the case differs,
    # because destination drives are often case-insensitive (exFAT/NTFS).
    assert second != "a.JPG"
    assert second.lower() == "a.1.jpg"


def test_seeds_from_preexisting_files_on_disk(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "existing.jpg").write_bytes(b"already here")

    tracker = NameClaimTracker()
    result = tracker.claim(dest_dir, "existing.jpg")

    assert result == "existing.1.jpg"
    # The pre-existing file on disk must not have been touched.
    assert (dest_dir / "existing.jpg").read_bytes() == b"already here"


def test_seeds_from_preexisting_files_case_insensitively(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "Existing.JPG").write_bytes(b"already here")

    tracker = NameClaimTracker()
    result = tracker.claim(dest_dir, "existing.jpg")

    assert result != "existing.jpg"
    assert result.lower() == "existing.1.jpg"


def test_seeding_happens_once_even_if_dir_created_later(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    tracker = NameClaimTracker()

    # First claim call: dir doesn't exist yet, seeds as "no pre-existing
    # files" and marks the dir seeded.
    first = tracker.claim(dest_dir, "a.jpg")
    assert first == "a.jpg"

    # Now a file magically appears on disk with the same name (simulating
    # some other process). The tracker should NOT re-seed / notice it,
    # since seeding happens exactly once per directory by design.
    dest_dir.mkdir()
    (dest_dir / "b.jpg").write_bytes(b"data")

    second = tracker.claim(dest_dir, "b.jpg")
    # Not seeded again, so "b.jpg" is considered unclaimed and granted
    # directly (this documents the tracker's actual, deliberate behavior).
    assert second == "b.jpg"


def test_different_directories_do_not_collide(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    tracker = NameClaimTracker()

    result_a = tracker.claim(dir_a, "photo.jpg")
    result_b = tracker.claim(dir_b, "photo.jpg")

    assert result_a == "photo.jpg"
    assert result_b == "photo.jpg"
