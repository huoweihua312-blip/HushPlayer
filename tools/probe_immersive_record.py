"""Record a real screen capture while entering/leaving immersive mode (BUG-01)."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, ".")
_ROOT = os.path.abspath("artifacts/qa/immflash")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.join(_ROOT, "data"))
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.services.library import LibraryQuery
from hushplayer.ui.context import ctx

T0 = time.monotonic()


def stamp(message: str) -> None:
    print(f"[{time.monotonic() - T0:6.2f}s] {message}", flush=True)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme_to_app(app, preference="dark")
    hush = HushApp(app)
    hush.start()
    stamp("app started")

    if hush.library.stats.track_count == 0:
        paths = []
        for root, _dirs, files in os.walk(os.path.abspath("tests/fixtures/audio")):
            paths += [os.path.join(root, f) for f in files]
        hush.library.import_files(paths)
    tracks = hush.library.tracks_page(LibraryQuery(sort="title", limit=10))
    hush.player.play_tracks(tracks, 0, context="flash-probe")
    hush.player.seek(3000)

    def show_main() -> None:
        hush.window.show()
        hush.window.raise_()
        hush.window.activateWindow()
        stamp("main shown")

    def open_imm() -> None:
        hush.window.open_immersive()
        stamp("immersive opened")

    def close_imm() -> None:
        win = ctx().immersive
        if win is not None:
            win.close_immersive()
        stamp("immersive closed")

    def finish() -> None:
        stamp("quit")
        hush.shutdown()
        app.quit()

    QTimer.singleShot(2000, show_main)
    QTimer.singleShot(4000, open_imm)
    QTimer.singleShot(7000, close_imm)
    QTimer.singleShot(8500, finish)
    QTimer.singleShot(60000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
