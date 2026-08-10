"""Launch the standalone immersive-lyrics visual experiment."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.ui_v2.experiments.immersive_lyrics_preview import ImmersiveLyricsPreview


def main() -> int:
    app = QApplication(sys.argv)
    window = ImmersiveLyricsPreview()
    window.resize(1400, 850)
    window.show()
    smoke_exit_text = str(os.environ.get("HUSHPLAYER_IMMERSIVE_PREVIEW_SMOKE_EXIT_MS") or "").strip()
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
