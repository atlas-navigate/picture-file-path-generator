"""Modal dialog summarizing a finished CopyResult."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from organizer.models import CopyResult
from gui.format_utils import format_bytes, format_duration


class ReportDialog(QDialog):
    def __init__(self, result: CopyResult, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Copy complete")
        self.resize(520, 480)

        layout = QVBoxLayout(self)

        if result.aborted:
            warning = QLabel(f"⚠ Copy was aborted: {result.abort_reason or 'Unknown reason'}")
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #b91c1c; font-weight: bold; font-size: 14px;")
            layout.addWidget(warning)

        layout.addWidget(self._build_summary_box(result))

        if result.errors:
            layout.addWidget(self._build_errors_box(result), stretch=1)

        if result.log_file_path is not None:
            log_label = QLabel(f"Full details logged to:\n{result.log_file_path}")
            log_label.setWordWrap(True)
            log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(log_label)

        layout.addLayout(self._build_button_row())

    def _build_summary_box(self, result: CopyResult) -> QGroupBox:
        box = QGroupBox("Summary")
        v = QVBoxLayout(box)
        v.addWidget(QLabel(f"Files copied: {result.copied_count}"))
        v.addWidget(QLabel(f"Errors: {result.error_count}"))
        v.addWidget(QLabel(f"Total copied: {format_bytes(result.total_bytes_copied)}"))
        v.addWidget(QLabel(f"Elapsed time: {format_duration(result.elapsed_seconds)}"))
        return box

    def _build_errors_box(self, result: CopyResult) -> QGroupBox:
        box = QGroupBox(f"Errors ({len(result.errors)})")
        v = QVBoxLayout(box)
        listw = QListWidget()
        for err in result.errors:
            listw.addItem(f"{err.source_path} -> {err.reason}")
        v.addWidget(listw)
        return box

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        row.addWidget(close_button)
        return row
