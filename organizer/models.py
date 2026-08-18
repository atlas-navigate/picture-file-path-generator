"""Plain data models shared across the organizer engine.

No Qt / GUI imports belong in this module -- it must remain usable
headlessly (e.g. from tests or a future CLI) with zero GUI dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class FileCategory(Enum):
    PICTURE = "PICTURE"
    VIDEO = "VIDEO"
    MISC = "MISC"


@dataclass
class PlannedFile:
    source_path: Path
    dest_path: Path  # final, already-disambiguated
    category: FileCategory
    capture_dt: datetime
    date_source: str  # "exif" | "video_metadata" | "filesystem_mtime"
    size_bytes: int
    was_renamed_for_conflict: bool


@dataclass
class ScanError:
    source_path: Path
    stage: str  # "stat" | "classify" | "metadata" | "plan"
    message: str


@dataclass
class ScanSummary:
    counts_by_category: dict[FileCategory, int] = field(default_factory=dict)
    counts_by_year_month: dict[tuple[FileCategory, int, int], int] = field(default_factory=dict)
    total_conflicts: int = 0
    total_size_bytes: int = 0
    error_count: int = 0


@dataclass
class CopyPlan:
    files: list[PlannedFile]
    errors: list[ScanError]
    summary: ScanSummary


@dataclass
class CopyError:
    source_path: Path
    dest_path: Path
    reason: str


@dataclass
class CopyResult:
    copied_count: int
    error_count: int
    errors: list[CopyError]
    total_bytes_copied: int
    elapsed_seconds: float
    aborted: bool
    abort_reason: str | None
    log_file_path: Path | None
