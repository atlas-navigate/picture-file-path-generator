"""Entry point for the Photo & Video Organizer GUI application."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from organizer import crash_diagnostics, metadata_pool


def main() -> int:
    # Both of these must run before QApplication exists: warming up the
    # forkserver helper here keeps its bootstrap fork single-threaded
    # (see metadata_pool.warm_up_forkserver), and enabling crash
    # diagnostics first means even a crash during Qt's own startup gets
    # captured. See organizer/crash_diagnostics.py for why this matters
    # -- the app is normally launched with no visible stdout/stderr.
    metadata_pool.warm_up_forkserver()
    crash_diagnostics.enable_crash_diagnostics()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
