"""QObject worker that runs organizer.copier.execute_plan() off the GUI thread.

Same moveToThread() pattern as ScanWorker -- see MainWindow for wiring.
Supports cancellation via a threading.Event, which is what
execute_plan()'s cancel_event parameter expects.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from organizer.copier import execute_plan
from organizer.models import CopyPlan, CopyResult


class CopyWorker(QObject):
    """Runs execute_plan(plan) on a background thread.

    Signals:
        progress(int, int, str): (current index, total files, current
            filename) -- forwarded straight from execute_plan's own
            progress_callback shape.
        finished(object, object): (CopyResult or None, error message or
            None). execute_plan() reports per-file failures inside the
            CopyResult itself and normally doesn't raise, but this
            mirrors ScanWorker's (result, error) shape as a defensive
            guard against a genuinely unexpected exception, so the GUI
            thread is never left waiting on a finished signal that
            would otherwise never arrive.
    """

    progress = Signal(int, int, str)
    finished = Signal(object, object)

    def __init__(
        self,
        plan: CopyPlan,
        log_file_path: Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._log_file_path = log_file_path
        self._logger = logger
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation. Safe to call from the GUI thread at any
        time -- threading.Event is thread-safe, and execute_plan() only
        checks it between files so this never touches a widget."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result: CopyResult = execute_plan(
                self._plan,
                progress_callback=self._on_progress,
                cancel_event=self._cancel_event,
                log_file_path=self._log_file_path,
            )
        except Exception as exc:  # noqa: BLE001 - defensive; see class docstring
            self.finished.emit(None, str(exc))
            return

        if self._logger is not None:
            try:
                self._log_summary(result)
            except Exception:
                # Logging must never prevent `finished` from being
                # emitted -- see class docstring. The copy itself already
                # completed; losing the summary log entry is far better
                # than leaving the GUI thread waiting forever.
                pass

        self.finished.emit(result, None)

    def _on_progress(self, current: int, total: int, filename: str) -> None:
        self.progress.emit(current, total, filename)

    def _log_summary(self, result: CopyResult) -> None:
        # Python's logging module is thread-safe, so writing here (on
        # the worker thread) rather than deferring to the GUI thread is
        # fine -- this is a plain stdlib call, not a widget touch.
        self._logger.info(
            "Copy finished: %d copied, %d errors, %d bytes, %.1fs elapsed, aborted=%s",
            result.copied_count,
            result.error_count,
            result.total_bytes_copied,
            result.elapsed_seconds,
            result.aborted,
        )
        if result.aborted:
            self._logger.warning("Copy aborted: %s", result.abort_reason)
        for err in result.errors:
            self._logger.error("FAILED %s -> %s: %s", err.source_path, err.dest_path, err.reason)
