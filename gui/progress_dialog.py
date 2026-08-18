"""Wraps QProgressDialog to track a CopyWorker's progress.

Thin wrapper: QProgressDialog already gives us a progress bar, a label,
and a Cancel button for free. All we add is wiring the CopyWorker's
progress signal to update it, and its Cancel button to request
cancellation on the worker.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog, QWidget


class ProgressDialog(QProgressDialog):
    def __init__(self, total_files: int, copy_worker, parent: QWidget | None = None) -> None:
        super().__init__("Copying files...", "Cancel", 0, max(total_files, 0), parent)
        self.setWindowTitle("Copying files")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumDuration(0)
        # We drive value/label entirely from the worker's progress
        # signal and control when this dialog closes from MainWindow
        # (once the "finished" signal arrives), so disable
        # QProgressDialog's own auto-close/auto-reset behavior.
        self.setAutoClose(False)
        self.setAutoReset(False)

        self.canceled.connect(copy_worker.cancel)

    def on_progress(self, current: int, total: int, filename: str) -> None:
        if total != self.maximum():
            self.setMaximum(total)
        self.setValue(current)
        self.setLabelText(f"Copying {filename}... ({current}/{total})")
