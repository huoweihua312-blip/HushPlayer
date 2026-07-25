"""Launch the isolated UI V2 preview without changing the stable main entry."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.ui_v2.shell.preview_window import PreviewWindow


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    window = PreviewWindow()
    window.show()
    smoke_exit_text = str(os.environ.get("HUSHPLAYER_UI_V2_SMOKE_EXIT_MS") or "").strip()
    if smoke_exit_text:
        try:
            smoke_exit_ms = max(100, int(smoke_exit_text))
        except ValueError:
            smoke_exit_ms = 0
        if smoke_exit_ms:
            QTimer.singleShot(smoke_exit_ms, window.close)
            QTimer.singleShot(smoke_exit_ms + 50, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
