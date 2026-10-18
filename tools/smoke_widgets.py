"""Offscreen/real screenshot harness for the custom widgets.

Run with ``HUSH_OFFSCREEN=1`` to render without showing windows; by default the
widgets are placed in a preview window that paints the app background so the
captured PNGs look like the real application.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if os.environ.get("HUSH_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget  # noqa: E402

from hushplayer.core.theme import apply_theme_to_app, qcolor, theme  # noqa: E402
from hushplayer.library.metadata import read_track  # noqa: E402
from hushplayer.ui.widgets.searchfield import SearchField, SegmentedControl  # noqa: E402
from hushplayer.ui.widgets.toast import ToastHost  # noqa: E402
from hushplayer.ui.widgets.tracklist import TrackListWidget  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class PreviewHost(QWidget):
    """Paints the window background the way MainWindow will."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HushPlayer widget preview")
        self.resize(980, 620)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), qcolor(theme().palette.window))
        painter.end()


def collect_tracks():
    tracks = []
    for path in sorted((ROOT / "tests" / "fixtures" / "audio").rglob("*")):
        if path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"} and path.stem != "corrupt":
            track, _cover, _ext = read_track(path, with_cover=False)
            tracks.append(track)
    return tracks


def main() -> int:
    app = QApplication([])
    mode = apply_theme_to_app(app, preference="dark")
    print(f"theme={mode}")
    tracks = collect_tracks()
    print(f"tracks={len(tracks)}")

    host = PreviewHost()
    tool_row = QWidget()
    tool_layout = QHBoxLayout(tool_row)
    tool_layout.setContentsMargins(30, 18, 30, 0)
    tool_layout.setSpacing(12)
    tool_layout.addWidget(SearchField())
    tool_layout.addWidget(SegmentedControl(["歌曲", "专辑", "歌手"]))
    tool_layout.addStretch(1)
    host.body.addWidget(tool_row)

    page = TrackListWidget()
    page.set_tracks(tracks)
    page.set_favorites({tracks[0].id})
    page.set_current(tracks[1].id, True)
    page.sort("title", True)
    host.body.addWidget(page, 1)

    toast_host = ToastHost(host)
    toast_host.set_bottom_offset(60)
    host.show()
    app.processEvents()
    toast_host.show_message("已添加到「我喜欢」", "success")
    app.processEvents()

    out = ROOT / "artifacts" / "smoke"
    out.mkdir(parents=True, exist_ok=True)
    host.grab().save(str(out / "tracklist_dark.png"))
    print("saved dark")

    apply_theme_to_app(app, preference="light")
    page.refresh_theme()
    page.table.header.update()
    app.processEvents()
    host.grab().save(str(out / "tracklist_light.png"))
    print("saved light")

    second = PreviewHost()
    second.resize(560, 420)
    narrow = TrackListWidget()
    narrow.set_tracks(tracks)
    narrow.set_empty_text("还没有歌曲", "导入音乐后会显示在这里")
    second.body.addWidget(narrow)
    second.show()
    app.processEvents()
    second.grab().save(str(out / "tracklist_narrow_light.png"))
    narrow.set_tracks([])
    app.processEvents()
    second.grab().save(str(out / "tracklist_empty_light.png"))
    print("saved narrow + empty")
    print("out", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
