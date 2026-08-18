"""Pass 2: actually copy files according to a previously-built CopyPlan.

Files are always COPIED (shutil.copy2, which preserves metadata),
never moved -- the source tree is never modified. Per-file failures are
recoverable (log and continue); running out of destination space is
fatal (abort immediately, don't keep failing through the rest of the
plan) since it means every subsequent copy would fail anyway.
"""
from __future__ import annotations

import errno
import shutil
import time
from pathlib import Path

from organizer.models import CopyError, CopyPlan, CopyResult


def execute_plan(
    plan: CopyPlan,
    progress_callback=None,
    cancel_event=None,
    log_file_path: Path | None = None,
) -> CopyResult:
    start_time = time.monotonic()

    copied_count = 0
    total_bytes_copied = 0
    errors: list[CopyError] = []
    aborted = False
    abort_reason: str | None = None

    total = len(plan.files)

    for i, pf in enumerate(plan.files):
        if cancel_event is not None and cancel_event.is_set():
            aborted = True
            abort_reason = "Cancelled by user"
            break

        try:
            pf.dest_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append(CopyError(
                source_path=pf.source_path,
                dest_path=pf.dest_path,
                reason=f"Could not create destination directory: {e}",
            ))
            if progress_callback is not None:
                progress_callback(i + 1, total, pf.source_path.name)
            continue

        if pf.dest_path.exists():
            # The plan was built against a snapshot of the destination
            # (Pass 1 is read-only and happens before the user reviews
            # the preview dialog); if something has since created a file
            # at this exact path, copying over it would silently destroy
            # its contents. Refuse and record it as a per-file error
            # instead.
            errors.append(CopyError(
                source_path=pf.source_path,
                dest_path=pf.dest_path,
                reason="Destination file already exists; skipped to avoid overwriting it",
            ))
            if progress_callback is not None:
                progress_callback(i + 1, total, pf.source_path.name)
            continue

        try:
            shutil.copy2(pf.source_path, pf.dest_path)
            copied_count += 1
            total_bytes_copied += pf.size_bytes
        except OSError as e:
            if e.errno == errno.ENOSPC:
                # Fatal: destination ran out of space. Attempt to clean
                # up the partially-written file, then stop entirely --
                # every remaining copy would fail the same way, and
                # source files are never modified so nothing has been
                # lost by stopping here.
                try:
                    pf.dest_path.unlink(missing_ok=True)
                except OSError:
                    pass
                aborted = True
                abort_reason = (
                    f"Destination ran out of space after copying "
                    f"{copied_count} of {total} files. "
                    f"No source files were modified."
                )
                break
            # Any other OSError (permission denied, source vanished,
            # I/O error mid-write, etc.) is a recoverable per-file
            # failure: clean up whatever partial file copy2 may have
            # left behind (so a truncated/corrupt file doesn't sit at
            # the final filename looking like a good copy), then log
            # and move on.
            try:
                pf.dest_path.unlink(missing_ok=True)
            except OSError:
                pass
            errors.append(CopyError(
                source_path=pf.source_path,
                dest_path=pf.dest_path,
                reason=str(e),
            ))
        except Exception as e:
            # Belt-and-braces: never let one bad file abort the whole
            # run for a non-OSError failure either. Same partial-file
            # cleanup as above.
            try:
                pf.dest_path.unlink(missing_ok=True)
            except OSError:
                pass
            errors.append(CopyError(
                source_path=pf.source_path,
                dest_path=pf.dest_path,
                reason=str(e),
            ))

        if progress_callback is not None:
            progress_callback(i + 1, total, pf.source_path.name)

    elapsed_seconds = time.monotonic() - start_time

    return CopyResult(
        copied_count=copied_count,
        error_count=len(errors),
        errors=errors,
        total_bytes_copied=total_bytes_copied,
        elapsed_seconds=elapsed_seconds,
        aborted=aborted,
        abort_reason=abort_reason,
        log_file_path=log_file_path,
    )
