"""BUG-06 dynamic check: the lyric sweep advances continuously (not per glyph)."""

from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, ".")
_ROOT = os.path.abspath("artifacts/qa/sweep")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.join(_ROOT, "data"))
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.services.library import LibraryQuery
from hushplayer.ui.context import ctx
from hushplayer.ui.desktop_lyrics import ensure_desktop_lyrics

LRC = (
    "[00:00.00]夜航信号\n"
    "[00:02.40]<00:02.40>穿过<00:02.80>无人<00:03.10>的<00:03.45>跑道\n"
    "[00:05.00]<00:05.00>城市<00:05.60>在身后<00:06.40>退潮\n"
    "[00:08.00]我把频率调到最高\n"
    "[00:10.00]听见海的心跳\n"
)
ACCENT = (201, 87, 112)


def accent_edge(pixmap) -> float:
    image = pixmap.toImage()
    best = 0.0
    for y in range(0, image.height(), 3):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if (
                abs(colour.red() - ACCENT[0]) < 40
                and abs(colour.green() - ACCENT[1]) < 45
                and abs(colour.blue() - ACCENT[2]) < 45
            ):
                best = max(best, float(x))
    return best


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme_to_app(app, preference="dark")
    hush = HushApp(app)
    hush.start()

    music = os.path.join(_ROOT, "music")
    if not os.path.isdir(music):
        shutil.copytree(os.path.abspath("tests/fixtures/audio"), music)
    lrc_path = os.path.join(music, "夜航信号", "01 - 夜航信号.lrc")
    if not os.path.exists(lrc_path):
        with open(lrc_path, "w", encoding="utf-8") as handle:
            handle.write(LRC)
    if hush.library.stats.track_count == 0:
        files = []
        for root, _dirs, names in os.walk(music):
            files += [os.path.join(root, name) for name in names]
        hush.library.import_files(files)
    tracks = hush.library.tracks_page(LibraryQuery(sort="title", limit=10))
    target = next((track for track in tracks if "夜航" in track.title), tracks[0])
    hush.player.play_tracks([target], 0, context="sweep-probe")

    window = ensure_desktop_lyrics()
    assert window is not None
    window.apply_settings()
    window.show_lyrics()

    clock = ctx().clock
    assert clock is not None
    ticks = {"count": 0}
    clock.tick.connect(lambda _position: ticks.__setitem__("count", ticks["count"] + 1))

    edges: list[tuple[int, float]] = []
    # sample inside one line's word-timed span (line changes are legitimate jumps)
    positions = list(range(2450, 3460, 50))

    def step(index: int = 0) -> None:
        if index >= len(positions):
            finish()
            return
        position = positions[index]
        window._position = position
        window.update()
        app.processEvents()
        edges.append((position, accent_edge(window.grab())))
        QTimer.singleShot(20, lambda: step(index + 1))

    def finish() -> None:
        print(f"ticks observed: {ticks['count']}", flush=True)
        previous = None
        jumps: list[float] = []
        for position, edge in edges:
            if previous is None:
                detail = ""
            else:
                jumps.append(edge - previous)
                detail = f" d={edge - previous:+5.1f}"
            print(f"{position:5d}ms edge={edge:7.1f}{detail}", flush=True)
            previous = edge
        moves = [jump for jump in jumps if abs(jump) > 0.01]
        negative = [jump for jump in moves if jump < -1.0]
        big = [jump for jump in moves if jump > 20.0]
        print(f"steps={len(moves)} negative={len(negative)} jumps>20px={len(big)}", flush=True)
        print("RESULT", "PASS" if not negative and not big and len(moves) >= 15 else "FAIL", flush=True)
        window.hide_lyrics()
        hush.shutdown()
        app.quit()

    QTimer.singleShot(1500, step)
    QTimer.singleShot(60000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
