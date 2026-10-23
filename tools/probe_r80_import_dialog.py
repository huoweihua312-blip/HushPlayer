"""Capture the playlist import wizard in its three stages (light + dark)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HUSHPLAYER_DATA_DIR"] = str(ROOT / "artifacts" / "qa" / "r80" / "data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = os.environ.get("HUSHPLAYER_TYPE_SCALE", "1.2")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.services.playlist_import import PlaylistEntry  # noqa: E402
from hushplayer.ui.context import ctx  # noqa: E402

OUT = ROOT / "artifacts" / "qa" / "r80"
OUT.mkdir(parents=True, exist_ok=True)

ENTRIES = [
    PlaylistEntry(title="夜航信号", artist="Aurora Field", album="夜航信号", duration_ms=242000),
    PlaylistEntry(title="Long Way Home", artist="The Paper Lanterns", album="Long Way Home", duration_ms=60000),
    PlaylistEntry(title="凌晨四点的海", artist="Aurora Field", album="夜航信号", duration_ms=9000),
    PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=269000),
    PlaylistEntry(title="家书", artist="加木", album="羲和", duration_ms=242000),
    PlaylistEntry(title="一首根本不存在的歌", artist="查无此人", duration_ms=180000),
]


def pump(app, dialog, timeout: float = 10.0) -> None:
    import time


    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        matcher = dialog._matcher
        if matcher and matcher.total and all(r.status != "pending" for r in matcher.rows):
            app.processEvents()
            return
        time.sleep(0.01)


def main() -> None:
    app = QApplication(sys.argv)
    hush = HushApp(app)
    hush.start()
    ctx().library.import_files(
        [str(p) for p in (ROOT / "tests" / "fixtures" / "audio").rglob("*") if p.is_file()]
    )

    from hushplayer.ui.playlist_import_dialog import PlaylistImportDialog

    mode = sys.argv[1] if len(sys.argv) > 1 else "light"
    ctx().settings.set("appearance.theme", mode)

    dialog = PlaylistImportDialog()
    stamp = time.strftime("%H%M%S")
    dialog.resize(980, 700)
    dialog.show()
    app.processEvents()

    # stage 1: source with a file already chosen
    dialog.link_input.setText("https://music.163.com/playlist?id=3778678")
    dialog._accept_entries("夜间通勤 " + stamp, ENTRIES, "来自 网易云音乐 链接")
    app.processEvents()
    dialog.grab().save(str(OUT / f"dialog_source_{mode}.png"))

    dialog._go_next()
    pump(app, dialog)
    dialog._refresh_counts()
    app.processEvents()
    dialog.grab().save(str(OUT / f"dialog_match_{mode}.png"))

    dialog._go_next()
    app.processEvents()
    dialog.grab().save(str(OUT / f"dialog_done_{mode}.png"))

    counts = dialog._matcher.counts()
    print("COUNTS", counts, "STAGE", dialog.stage, flush=True)
    hush.shutdown()


main()
