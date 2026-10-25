"""Render the replace-source dialog with synthetic candidates."""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(ROOT / "artifacts" / "qa" / "r84" / "data"))
os.environ.setdefault("HUSHPLAYER_NO_CLOSE_PROMPT", "1")
os.environ.setdefault("HUSHPLAYER_MUTEX_SUFFIX", "r84")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.model.track import Track  # noqa: E402
from hushplayer.services.source_replace import SourceCandidate  # noqa: E402
from hushplayer.ui.track_source_dialog import TrackSourceDialog  # noqa: E402


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    hush = HushApp(app)
    hush.start()
    out = ROOT / "artifacts" / "qa" / "r84"
    out.mkdir(parents=True, exist_ok=True)

    track = Track(
        id="online:kw:demo",
        kind="online",
        title="家书",
        artist="加木",
        album="羲和",
        duration_ms=242000,
        source_id="kw",
        source_name="酷我",
        remote_id="demo",
    )
    dialog = TrackSourceDialog(hush.window, track)
    dialog.show()

    candidates = [
        SourceCandidate("wy", "网易音乐", "a1", "家书", "加木", "羲和", 242000, "", 100, {}),
        SourceCandidate("kg", "酷狗", "a2", "家书", "加木", "羲和", 241000, "", 96, {}),
        SourceCandidate("wy", "网易音乐", "a3", "家书 (Live)", "加木", "羲和 Live", 250000, "", 88, {}),
        SourceCandidate("tx", "QQ音乐 · 1a43", "a4", "家书", "加木", "羲和", 240000, "", 84, {}),
    ]
    dialog._on_finished(candidates, ["酷我：Request failed with status code 404"])
    for _ in range(12):
        app.processEvents()
    path = out / "source_dialog.png"
    dialog.grab().save(str(path))
    print("saved", path, dialog.width(), dialog.height(), "rows", dialog.list.count())
    dialog.close()
    hush.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
