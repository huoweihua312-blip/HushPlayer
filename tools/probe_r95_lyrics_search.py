"""Render the lyrics search dialog with synthetic LRCLIB results."""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(ROOT / "artifacts" / "qa" / "r95" / "data"))
os.environ.setdefault("HUSHPLAYER_NO_CLOSE_PROMPT", "1")
os.environ.setdefault("HUSHPLAYER_MUTEX_SUFFIX", "r95")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.lyrics.service import LyricsCandidate  # noqa: E402
from hushplayer.ui.widgets.lyrics_search import LyricsSearchDialog  # noqa: E402

SYNCED = "\n".join(f"[00:{index:02d}.00]第 {index} 行歌词" for index in range(1, 9))


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    hush = HushApp(app)
    hush.start()
    out = ROOT / "artifacts" / "qa" / "r95"
    out.mkdir(parents=True, exist_ok=True)

    dialog = LyricsSearchDialog(
        hush.window,
        initial="",
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
    )
    dialog.field.set_text("晴天 周杰伦")
    dialog.show()
    candidates = [
        LyricsCandidate(1, "晴天", "周杰伦", "叶惠美", 269000, SYNCED, ""),
        LyricsCandidate(2, "晴天 (Live)", "周杰伦", "世界巡回演唱会", 302000, SYNCED, ""),
        LyricsCandidate(3, "晴天", "Various Artists", "翻唱合集", 268000, "", "纯文本歌词"),
    ]
    dialog._on_results(candidates)
    dialog.list.setCurrentRow(1)
    for _ in range(16):
        app.processEvents()
    path = out / "lyrics_search.png"
    dialog.grab().save(str(path))
    print("saved", path, dialog.width(), dialog.height(), "rows", dialog.list.count())
    dialog.close()
    hush.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
