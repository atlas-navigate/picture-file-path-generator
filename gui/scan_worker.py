"""QObject worker that runs organizer.planner.scan_source() off the GUI thread.

Instances are meant to be moved to a QThread via moveToThread() -- see
MainWindow for how it's wired up. The worker itself must never touch a
QWidget; it only calls into the plain organizer/ engine and reports
back via Qt signals, with one deliberate exception described below.

Progress is NOT reported via a Qt signal. Emitting a live per-file
Signal(int) from this worker thread while Pillow/pillow-heif/hachoir
are actively parsing files on the same thread was found (empirically,
via repeated crash isolation) to reliably corrupt the process heap in
this app's PySide6 6.11.1 / Python 3.14 environment -- observed as
`malloc(): unaligned tcache chunk detected` and SIGSEGV shortly after,
specifically when a connected slot on the GUI thread touches a QWidget
(QProgressDialog.setLabelText) in response. It reproduced consistently
across unrelated corrupt-file scenarios and disappeared consistently
once the live progress signal was removed, so `files_scanned` below is
a plain int the GUI thread polls with a QTimer instead -- CPython's GIL
makes a bare int attribute read/write safe enough for a progress
counter without needing an explicit lock. `finished` still uses a
normal Qt signal (that cross-thread pattern was verified safe in
isolation); only the tight, per-file progress path is affected.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from organizer.models import CopyPlan
from organizer.planner import scan_source


class ScanWorker(QObject):
    """Runs scan_source(source_root, dest_root) on a background thread.

    Attributes:
        files_scanned (int): number of files scanned so far. Written
            from the worker thread, read by the GUI thread via polling
            (see MainWindow) -- not signal-based, see module docstring.

    Signals:
        finished(object, object): (CopyPlan or None, error message or
            None) -- exactly one of the two is None. scan_source() is
            designed to capture per-file problems as ScanError entries
            inside the returned CopyPlan rather than raising, so the
            error slot here is reserved for a scan that failed to
            produce any plan at all (e.g. an unexpected exception).
    """

    finished = Signal(object, object)

    def __init__(self, source_root: Path, dest_root: Path) -> None:
        super().__init__()
        self._source_root = Path(source_root)
        self._dest_root = Path(dest_root)
        self.files_scanned = 0

    @Slot()
    def run(self) -> None:
        try:
            plan: CopyPlan = scan_source(
                self._source_root,
                self._dest_root,
                progress_callback=self._on_progress,
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI thread
            self.finished.emit(None, str(exc))
            return
        self.finished.emit(plan, None)

    def _on_progress(self, files_seen: int) -> None:
        # Runs on the worker thread. Plain attribute write only -- see
        # module docstring for why this isn't a Qt signal.
        self.files_scanned = files_seen
