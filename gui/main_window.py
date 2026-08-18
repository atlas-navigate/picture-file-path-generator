"""Main application window for the file organizer GUI.

Owns all QWidgets. Long-running work (scanning, copying) always runs on
a background QThread via ScanWorker / CopyWorker; this module never
calls into the organizer engine directly on the GUI thread (aside from
the quick, synchronous setup_logger() call, which just opens a log
file), and the workers never touch a QWidget directly -- everything
crosses back to the GUI thread through Qt signals only.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.copy_worker import CopyWorker
from gui.preview_dialog import PreviewDialog
from gui.progress_dialog import ProgressDialog
from gui.report_dialog import ReportDialog
from gui.scan_worker import ScanWorker
from organizer.logging_utils import setup_logger
from organizer.models import CopyPlan, CopyResult


def _paths_overlap(a: Path, b: Path) -> bool:
    """True if the two resolved paths are identical, or one is an
    ancestor of the other.

    Source and destination must never overlap: copying INTO a subfolder
    of the tree being scanned (or scanning a tree that contains the
    destination) could make the read-only scan pass see files that the
    copy pass is actively writing, corrupting the plan/copy.
    """
    a = a.resolve()
    b = b.resolve()
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo & Video Organizer")
        self.resize(600, 220)

        self._source_path: Path | None = None
        self._dest_path: Path | None = None

        # Kept as attributes so the QThread/worker objects aren't
        # garbage-collected mid-run -- nothing else holds a strong
        # reference to them once _on_scan_clicked()/_start_copy() return.
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._copy_thread: QThread | None = None
        self._copy_worker: CopyWorker | None = None
        self._scan_progress_dialog: QProgressDialog | None = None
        self._copy_progress_dialog: ProgressDialog | None = None
        # Polls ScanWorker.files_scanned on a timer rather than connecting
        # to a live per-file Qt signal -- see gui/scan_worker.py's module
        # docstring for why (a reproducible heap-corruption crash in this
        # PySide6/Python 3.14 environment).
        self._scan_poll_timer: QTimer | None = None

        self._build_ui()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.source_browse_button = QPushButton("Browse...")
        self.source_browse_button.clicked.connect(self._browse_source)
        layout.addLayout(self._make_row("Source folder:", self.source_edit, self.source_browse_button))

        self.dest_edit = QLineEdit()
        self.dest_edit.setReadOnly(True)
        self.dest_browse_button = QPushButton("Browse...")
        self.dest_browse_button.clicked.connect(self._browse_dest)
        layout.addLayout(self._make_row("Destination folder:", self.dest_edit, self.dest_browse_button))

        self.scan_button = QPushButton("Scan / Preview")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self._on_scan_clicked)
        layout.addWidget(self.scan_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addStretch(1)

    @staticmethod
    def _make_row(label_text: str, edit: QLineEdit, browse_button: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        row.addWidget(edit, stretch=1)
        row.addWidget(browse_button)
        return row

    # ---- Folder selection -------------------------------------------------

    def _browse_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select source folder")
        if path:
            self._source_path = Path(path)
            self.source_edit.setText(path)
            self._update_scan_button_enabled()

    def _browse_dest(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if path:
            self._dest_path = Path(path)
            self.dest_edit.setText(path)
            self._update_scan_button_enabled()

    def _update_scan_button_enabled(self) -> None:
        self.scan_button.setEnabled(self._source_path is not None and self._dest_path is not None)

    # ---- Scan phase ---------------------------------------------------

    def _on_scan_clicked(self) -> None:
        assert self._source_path is not None and self._dest_path is not None
        source, dest = self._source_path, self._dest_path

        if _paths_overlap(source, dest):
            QMessageBox.critical(
                self,
                "Invalid folders",
                "The source and destination folders must not be the same folder, "
                "and neither may be inside the other.\n\n"
                "Copying into a subfolder of the folder being scanned (or vice "
                "versa) could cause the scan to pick up files that the copy is "
                "actively writing.",
            )
            return

        self._set_controls_enabled(False)
        self.status_label.setText("Scanning...")

        self._scan_progress_dialog = QProgressDialog("Scanning...", None, 0, 0, self)
        self._scan_progress_dialog.setWindowTitle("Scanning")
        self._scan_progress_dialog.setWindowModality(Qt.WindowModal)
        self._scan_progress_dialog.setMinimumDuration(0)
        self._scan_progress_dialog.setAutoClose(False)
        self._scan_progress_dialog.setAutoReset(False)
        self._scan_progress_dialog.show()

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(source, dest)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)

        self._scan_poll_timer = QTimer(self)
        self._scan_poll_timer.timeout.connect(self._on_scan_poll)
        self._scan_poll_timer.start(150)

        self._scan_thread.start()

    def _on_scan_poll(self) -> None:
        # GUI-thread timer tick -- reads ScanWorker.files_scanned directly
        # rather than reacting to a cross-thread signal. See ScanWorker's
        # module docstring for why.
        if self._scan_progress_dialog is not None and self._scan_worker is not None:
            files_seen = self._scan_worker.files_scanned
            self._scan_progress_dialog.setLabelText(f"Scanning... ({files_seen} files seen)")

    def _on_scan_finished(self, plan: CopyPlan | None, error: str | None) -> None:
        if self._scan_poll_timer is not None:
            self._scan_poll_timer.stop()
            self._scan_poll_timer = None
        if self._scan_progress_dialog is not None:
            self._scan_progress_dialog.close()
            self._scan_progress_dialog = None
        self._scan_thread = None
        self._scan_worker = None
        self._set_controls_enabled(True)
        self.status_label.setText("")

        if error is not None:
            QMessageBox.critical(
                self,
                "Scan failed",
                f"Scanning failed and no plan could be built:\n\n{error}",
            )
            return

        assert plan is not None
        preview = PreviewDialog(plan, self)
        if preview.exec() == QDialog.Accepted:
            self._start_copy(plan)
        # Otherwise cancelled: the scan never wrote anything, so there
        # is nothing to undo -- just return to the main window.

    # ---- Copy phase -----------------------------------------------------

    def _start_copy(self, plan: CopyPlan) -> None:
        assert self._dest_path is not None
        logger, log_file_path = setup_logger(self._dest_path)
        logger.info("Starting copy: %d files planned", len(plan.files))

        self._set_controls_enabled(False)
        self.status_label.setText("Copying...")

        self._copy_thread = QThread(self)
        self._copy_worker = CopyWorker(plan, log_file_path=log_file_path, logger=logger)
        self._copy_worker.moveToThread(self._copy_thread)

        self._copy_progress_dialog = ProgressDialog(len(plan.files), self._copy_worker, self)
        self._copy_progress_dialog.show()

        self._copy_thread.started.connect(self._copy_worker.run)
        self._copy_worker.progress.connect(self._copy_progress_dialog.on_progress)
        self._copy_worker.finished.connect(self._on_copy_finished)
        self._copy_worker.finished.connect(self._copy_thread.quit)
        self._copy_worker.finished.connect(self._copy_worker.deleteLater)
        self._copy_thread.finished.connect(self._copy_thread.deleteLater)
        self._copy_thread.start()

    def _on_copy_finished(self, result: CopyResult | None, error: str | None) -> None:
        if self._copy_progress_dialog is not None:
            self._copy_progress_dialog.close()
            self._copy_progress_dialog = None
        self._copy_thread = None
        self._copy_worker = None
        self._set_controls_enabled(True)
        self.status_label.setText("")

        if error is not None:
            QMessageBox.critical(self, "Copy failed", f"Copying failed unexpectedly:\n\n{error}")
            return

        assert result is not None
        ReportDialog(result, self).exec()

    # ---- Window lifecycle -----------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Refuse to close while a scan or copy is still running.

        MainWindow is the app's only top-level window, so closing it
        (e.g. via the title-bar X) while _scan_thread/_copy_thread is
        still active would tear down a running QThread and crash the
        process -- possibly mid-write on a file copy.
        """
        for thread in (self._scan_thread, self._copy_thread):
            if thread is not None and thread.isRunning():
                QMessageBox.warning(
                    self,
                    "Operation in progress",
                    "A scan or copy is still in progress. Please wait for "
                    "it to finish (or cancel it) before closing the window.",
                )
                event.ignore()
                return
        event.accept()

    # ---- Shared helpers -----------------------------------------------

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.source_browse_button.setEnabled(enabled)
        self.dest_browse_button.setEnabled(enabled)
        self.scan_button.setEnabled(
            enabled and self._source_path is not None and self._dest_path is not None
        )
