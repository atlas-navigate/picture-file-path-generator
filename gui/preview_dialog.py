"""Modal dialog previewing a CopyPlan before any files are copied.

Read-only by construction: scan_source() (which produced this plan)
never writes to disk, so Cancel here is always free and safe -- nothing
has happened yet.
"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from organizer.models import CopyPlan, FileCategory
from organizer.planner import MONTH_NAMES
from gui.format_utils import format_bytes


class PreviewDialog(QDialog):
    """Shown after a scan completes. exec() returns QDialog.Accepted if
    the user clicked "Confirm & Copy", QDialog.Rejected if they clicked
    "Cancel" (or closed the dialog) -- the standard Qt modal pattern."""

    def __init__(self, plan: CopyPlan, parent=None) -> None:
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle("Preview changes")
        self.resize(560, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_summary_box())

        layout.addWidget(QLabel("Breakdown by date:"))
        layout.addWidget(self._build_tree(), stretch=1)

        if plan.errors:
            layout.addWidget(self._build_errors_box(), stretch=0)

        layout.addLayout(self._build_button_row())

    # ---- sections -------------------------------------------------------

    def _build_summary_box(self) -> QGroupBox:
        summary = self._plan.summary
        pictures = summary.counts_by_category.get(FileCategory.PICTURE, 0)
        videos = summary.counts_by_category.get(FileCategory.VIDEO, 0)
        misc = summary.counts_by_category.get(FileCategory.MISC, 0)
        total_files = pictures + videos + misc

        box = QGroupBox("Summary")
        v = QVBoxLayout(box)
        v.addWidget(QLabel(f"Pictures: {pictures}"))
        v.addWidget(QLabel(f"Videos: {videos}"))
        v.addWidget(QLabel(f"Misc (not date-sorted): {misc}"))
        v.addWidget(QLabel(f"Total files: {total_files}"))
        v.addWidget(QLabel(f"Total size: {format_bytes(summary.total_size_bytes)}"))
        v.addWidget(QLabel(f"Filename conflicts (auto-renamed to avoid overwrite): {summary.total_conflicts}"))

        error_label = QLabel(f"Files skipped due to scan errors: {summary.error_count}")
        if summary.error_count:
            error_label.setStyleSheet("color: #b45309; font-weight: bold;")
        v.addWidget(error_label)

        return box

    def _build_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)

        # Group counts_by_year_month -> {category: {year: {month: count}}}
        by_cat_year: dict[FileCategory, dict[int, dict[int, int]]] = {}
        for (category, year, month), count in self._plan.summary.counts_by_year_month.items():
            by_cat_year.setdefault(category, {}).setdefault(year, {})[month] = count

        for category, label in ((FileCategory.PICTURE, "Pictures"), (FileCategory.VIDEO, "Videos")):
            years = by_cat_year.get(category, {})
            cat_total = sum(sum(months.values()) for months in years.values())
            cat_item = QTreeWidgetItem([f"{label} ({cat_total} files)"])
            tree.addTopLevelItem(cat_item)

            for year in sorted(years):
                months = years[year]
                year_total = sum(months.values())
                year_item = QTreeWidgetItem([f"{year} ({year_total} files)"])
                cat_item.addChild(year_item)

                for month in sorted(months):
                    count = months[month]
                    month_item = QTreeWidgetItem([f"{MONTH_NAMES[month]} {year} ({count} files)"])
                    year_item.addChild(month_item)

            cat_item.setExpanded(True)

        return tree

    def _errors_text(self) -> str:
        return "\n".join(
            f"[{err.stage}] {err.source_path}: {err.message}" for err in self._plan.errors
        )

    def _build_errors_box(self) -> QGroupBox:
        box = QGroupBox(f"Scan errors ({len(self._plan.errors)}) -- these files were skipped")
        v = QVBoxLayout(box)
        listw = QListWidget()
        for err in self._plan.errors:
            listw.addItem(f"[{err.stage}] {err.source_path}: {err.message}")
        listw.setMaximumHeight(120)
        v.addWidget(listw)

        button_row = QHBoxLayout()
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._errors_text()))
        button_row.addWidget(copy_button)

        save_button = QPushButton("Save to File...")
        save_button.clicked.connect(self._save_errors_to_file)
        button_row.addWidget(save_button)

        button_row.addStretch(1)
        v.addLayout(button_row)

        return box

    def _save_errors_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save scan errors", "scan_errors.txt", "Text files (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._errors_text())

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)

        self.copy_button = QPushButton("Confirm && Copy")
        self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self.accept)
        row.addWidget(self.copy_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)

        return row
