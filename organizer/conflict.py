"""Destination filename collision handling.

Zero data loss requires that no two distinct source files ever be
copied to the same destination path. Destination drives are commonly
exFAT or NTFS (typical formats for external drives), which are
case-insensitive filesystems, so collisions must be detected
case-insensitively even though this app itself runs fine on
case-sensitive Linux filesystems.
"""
from __future__ import annotations

import os
from pathlib import Path


def insert_suffix(filename: str, n: int) -> str:
    """Insert a ``.<n>`` disambiguation suffix before the extension.

    ``insert_suffix("IMG_0001.jpg", 1) == "IMG_0001.1.jpg"``
    ``insert_suffix("README", 1) == "README.1"`` (no extension to preserve)
    """
    if "." in filename:
        stem, ext = filename.rsplit(".", 1)
        return f"{stem}.{n}.{ext}"
    return f"{filename}.{n}"


class NameClaimTracker:
    """Tracks claimed destination filenames per directory across a scan.

    One instance is meant to be shared across an entire scan_source()
    call so that conflicts are detected globally, not just within a
    single os.walk() directory visit.
    """

    def __init__(self) -> None:
        self._claimed: dict[Path, set[str]] = {}
        self._seeded: set[Path] = set()

    def _ensure_seeded(self, dest_dir: Path) -> None:
        if dest_dir in self._seeded:
            return
        claimed_set = self._claimed.setdefault(dest_dir, set())
        if dest_dir.exists():
            for existing_name in os.listdir(dest_dir):
                claimed_set.add(existing_name.lower())
        self._seeded.add(dest_dir)

    def claim(self, dest_dir: Path, desired_filename: str) -> str:
        """Claim a filename in dest_dir, returning a collision-free name.

        The first call for a given dest_dir lazily seeds the claimed set
        from whatever already exists on disk there (exactly once, even
        if the directory doesn't exist yet -- we don't want to re-stat
        it on every subsequent call).
        """
        self._ensure_seeded(dest_dir)
        claimed_set = self._claimed.setdefault(dest_dir, set())

        if desired_filename.lower() not in claimed_set:
            claimed_set.add(desired_filename.lower())
            return desired_filename

        n = 1
        while True:
            candidate = insert_suffix(desired_filename, n)
            if candidate.lower() not in claimed_set:
                claimed_set.add(candidate.lower())
                return candidate
            n += 1
