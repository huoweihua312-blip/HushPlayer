"""Dynamic check for BUG-01: no black/white flash when entering immersive mode."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, ".")
_ROOT = os.path.abspath("artifacts/qa/immflash")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.join(_ROOT, "data"))
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.services.library import LibraryQuery

FRAMES = os.path.join(_ROOT, "frames")


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme_to_app(app, preference="dark")
    hush = HushApp(app)
    hush.start()
    os.makedirs(FRAMES, exist_ok=True)
    for old in os.listdir(FRAMES):
        os.remove(os.path.join(FRAMES, old))

    fixtures = os.path.abspath("tests/fixtures/audio")
    if hush.library.stats.track_count == 0:
        paths = []
        for root, _dirs, files in os.walk(fixtures):
            paths += [os.path.join(root, f) for f in files]
        hush.library.import_files(paths)
    tracks = hush.library.tracks_page(LibraryQuery(sort="title", limit=10))
    hush.player.play_tracks(tracks, 0, context="flash-probe")
    hush.player.seek(3000)

    screen = QGuiApplication.primaryScreen()
    samples: list[tuple[str, float]] = []
    frames: list[str] = []
    state = {"i": 0, "opened": False}

    def capture(tag: str) -> None:
        if screen is None:
            return
        pm = screen.grabWindow(0)
        name = f"{len(frames):03d}_{tag}.jpg"
        path = os.path.join(FRAMES, name)
        pm.save(path, "JPG", 70)
        img = pm.toImage()
        step = 16
        total = 0
        count = 0
        for y in range(0, img.height(), step):
            for x in range(0, img.width(), step):
                c = img.pixelColor(x, y)
                total += (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
                count += 1
        samples.append((name, total / max(1, count)))
        frames.append(path)

    def tick() -> None:
        capture("imm" if state["opened"] else "main")
        state["i"] += 1
        if state["i"] == 6 and not state["opened"]:
            state["opened"] = True
            hush.window.open_immersive()
            capture("open")
        if state["i"] >= 40:
            timer.stop()
            finish()

    def finish() -> None:
        print("frames", len(samples))
        for name, lum in samples:
            print(f"{name}\t{lum:6.2f}")
        hush.window.ctx = None  # type: ignore[attr-defined]
        try:
            if hush.window.immersive is not None:
                hush.window.immersive.close_immersive()
        except Exception:
            pass
        hush.shutdown()
        app.quit()

    timer = QTimer()
    timer.setInterval(40)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(20000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
