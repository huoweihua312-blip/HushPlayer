"""BUG-01 dynamic check: grab the immersive window itself right after show()."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
_ROOT = os.path.abspath("artifacts/qa/immflash")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.join(_ROOT, "data"))
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.services.library import LibraryQuery
from hushplayer.ui.context import ctx


class PaintSpy(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.paints = 0

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Paint:
            self.paints += 1
        return False


def luma(pixmap) -> float:
    img = pixmap.toImage()
    total = 0
    count = 0
    step = 16
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            c = img.pixelColor(x, y)
            total += (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
            count += 1
    return total / max(1, count)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme_to_app(app, preference="dark")
    hush = HushApp(app)
    hush.start()
    out = os.path.join(_ROOT, "window")
    os.makedirs(out, exist_ok=True)

    if hush.library.stats.track_count == 0:
        paths = []
        for root, _dirs, files in os.walk(os.path.abspath("tests/fixtures/audio")):
            paths += [os.path.join(root, f) for f in files]
        hush.library.import_files(paths)
    tracks = hush.library.tracks_page(LibraryQuery(sort="title", limit=10))
    hush.player.play_tracks(tracks, 0, context="flash-probe")
    hush.player.seek(4000)
    hush.window.show()

    results = []
    spy = {"obj": None}
    index = {"n": 0}

    def snap(tag: str) -> None:
        win = ctx().immersive
        if win is None:
            print("no immersive window", flush=True)
            return
        path = os.path.join(out, f"{index['n']:03d}_{tag}.png")
        index["n"] += 1
        pix = win.grab()
        pix.save(path)
        results.append((tag, luma(pix), spy["obj"].paints if spy["obj"] else -1))

    def start() -> None:
        print("start: opening immersive", flush=True)
        hush.window.open_immersive()
        win = ctx().immersive
        assert win is not None
        spy["obj"] = PaintSpy()
        win.installEventFilter(spy["obj"])
        snap("immediately")
        for delay, tag in ((40, "040ms"), (80, "080ms"), (200, "200ms"), (400, "400ms"), (800, "800ms")):
            QTimer.singleShot(delay, lambda t=tag: snap(t))
        QTimer.singleShot(1400, finish)

    def finish() -> None:
        snap("1400ms")
        base = results[-1][1]
        print(f"steady luma = {base:.2f}", flush=True)
        worst = 0.0
        for tag, lum, paints in results:
            delta = abs(lum - base)
            worst = max(worst, delta)
            print(f"{tag:14s} luma={lum:6.2f} delta={delta:5.2f} paints={paints}", flush=True)
        print(f"worst delta = {worst:.2f} (threshold 25)", flush=True)
        print("RESULT", "PASS" if worst < 25.0 else "FAIL", flush=True)
        win = ctx().immersive
        if win is not None:
            win.close_immersive()
        hush.shutdown()
        app.quit()

    QTimer.singleShot(1200, start)
    QTimer.singleShot(20000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
