"""1.3.25 探针：歌曲列表首帧封面 + 播放栏圆钮。

用法（离屏）：
    $env:QT_QPA_PLATFORM="offscreen"
    .venv\\Scripts\\python.exe tools\\probe_r98_covers_button.py save

产物：artifacts/qa/r98/songs_first.png / songs_later.png / play_button.png
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "artifacts" / "qa" / "r98"
DATA = BASE / "data"
os.environ["HUSHPLAYER_DATA_DIR"] = str(DATA)
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from hushplayer.app import HushApp  # noqa: E402


def pump(ms: int = 100) -> None:
    from PySide6.QtCore import QDeadlineTimer, QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents(QEventLoop.AllEvents, 50)


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    audio = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "audio"
    files = sorted(
        p for p in audio.rglob("*")
        if p.suffix.lower() in {".mp3", ".flac", ".ogg", ".wav", ".m4a"}
        and "corrupt" not in p.name.lower()
    )

    shell = HushApp(app)
    shell.start()
    window = shell.window
    window.resize(1280, 820)

    service = shell.library
    result = service.import_files([str(p) for p in files])
    print("imported:", result.added, "updated:", result.updated)

    shell.window.navigate("songs")
    pump(150)
    window.grab().save(str(BASE / "songs_first.png"))
    pump(1500)
    window.grab().save(str(BASE / "songs_later.png"))

    bar = shell.window.playerbar
    origin = bar.play.mapTo(bar, QPoint(0, 0))
    centre = QRect(origin, bar.play.size())
    crop = bar.grab(centre.adjusted(-12, -12, 12, 12))
    crop.scaled(crop.width() * 5, crop.height() * 5).save(str(BASE / "play_button.png"))

    (BASE / "probe.json").write_text(
        json.dumps(
            {
                "tracks": shell.player.queue.count,
                "songs": len(service.tracks.list(kind="local")),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("saved", BASE)
    shell.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
