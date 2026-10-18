"""BUG-10 视觉状态矩阵取证：普通 / 悬停 / 选中 / 播放 / 播放+选中 / 播放+悬停。

真实窗口（不能用 offscreen：Qt 不附带字体，中文会变成方块）。
输出 artifacts/qa/rowstates_<mode>.png
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("."))

os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/rowstates/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from hushplayer.app import HushApp
from hushplayer.core.theme import theme
from hushplayer.ui.pages.page import PageHeader
from hushplayer.ui.widgets.common import TextButton
from hushplayer.ui.widgets.searchfield import SearchField
from hushplayer.ui.widgets.tracklist import TrackListWidget


class Host(QWidget):
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme().palette.window))


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # match hushplayer.app.main()
    hush = HushApp(app)
    hush.start()
    library = hush.library

    from pathlib import Path

    from hushplayer.services.library import LibraryQuery

    def load_tracks():
        items = library.tracks_page(LibraryQuery(sort="title", limit=12))
        if len(items) >= 6:
            return items
        paths = [
            str(path)
            for path in sorted(Path("tests/fixtures/audio").rglob("*"))
            if path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"} and "corrupt" not in path.name
        ]
        library.import_files(paths)
        return library.tracks_page(LibraryQuery(sort="title", limit=12))

    tracks = load_tracks()
    print("tracks", len(tracks), flush=True)
    host = Host()
    host.setObjectName("RowStateHost")
    host.resize(1080, 700)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(10)
    header = PageHeader("歌曲", "状态矩阵 · 播放 / 选中 / 悬停 / 焦点")
    header.add_action(TextButton("播放全部", icon_name="play"))
    layout.addWidget(header)
    layout.addWidget(SearchField("搜索歌曲"))
    widget = TrackListWidget()
    layout.addWidget(widget, 1)
    widget.set_tracks(tracks)
    host.show()

    widget.table.setFocus()
    model = widget.table.model()

    QTimer.singleShot(15000, app.quit)

    def step2() -> None:
        # 行 1 = 播放（未选中），行 2 = 播放 + 选中，行 3 = 普通选中，行 0 = 普通
        model.set_current(tracks[1].id, True)
        widget.table.selectRow(2)
        model.set_current(tracks[2].id, True)
        widget.table.setCurrentIndex(model.index(2, 2))
        QTest.mouseMove(widget.table, QPoint(widget.table.columnWidth(0) + 40,
                                              widget.table.rowHeight(0) // 2))
        QTimer.singleShot(350, step3)

    captured = {"done": False}

    def capture(mode: str) -> None:
        host.grab().save(f"artifacts/qa/rowstates_{mode}.png")
        print("saved", mode, flush=True)

    def apply_pref(pref: str) -> None:
        hush.settings.set("appearance.theme", pref)
        hush.apply_theme()

    def step3() -> None:
        try:
            mode = theme().mode
            capture(mode)
            if not captured["done"]:
                captured["done"] = True
                other = "light" if mode == "dark" else "dark"
                apply_pref(other)
                QTimer.singleShot(600, lambda: (capture(other), host.close(), app.quit()))
        except Exception as exc:  # noqa: BLE001
            print("stage failed", exc, flush=True)
            app.quit()

    QTimer.singleShot(900, step2)
    code = app.exec()
    hush.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
