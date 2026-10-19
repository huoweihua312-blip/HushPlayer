"""R6 回归：调整歌词偏移时视图不能先跳到第一行再回来。"""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer

from hushplayer.lyrics import parser
from hushplayer.ui.widgets.lyrics_view import LyricsView

LRC = "\n".join(
    [f"[00:{second:02d}.00]第 {second} 行歌词内容用来撑开高度" for second in range(0, 40, 2)]
)


def pump(ms: int = 30) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def make_document(offset_ms: int = 0):
    document = parser.parse(LRC, source="local")
    document.offset_ms = offset_ms
    return document


def test_offset_rebuild_keeps_scroll_position(qapp) -> None:
    view = LyricsView(centered=True)
    view.resize(620, 360)
    view.show()
    view.set_document(make_document())
    view.set_position(20_000)
    pump(80)
    index = view.body.active_index
    assert index > 2
    view._scroll_to_index(index, animate=False)  # noqa: SLF001 - exercise the same path as following
    pump(60)
    bar = view.scroll.verticalScrollBar()
    before = bar.value()
    assert before > 0

    view.set_document(make_document(500), keep_position=True)
    # Immediately after the rebuild the viewport must not snap to the top.
    assert bar.value() == before
    for _ in range(10):
        pump(20)
        assert bar.value() == before, "offset calibration must not move the lyrics"

    view.close()


def test_new_track_still_starts_at_top(qapp) -> None:
    view = LyricsView()
    view.resize(620, 360)
    view.show()
    view.set_document(make_document())
    view.set_position(20_000)
    pump(60)
    view._scroll_to_index(view.body.active_index, animate=False)  # noqa: SLF001
    pump(40)
    assert view.scroll.verticalScrollBar().value() > 0

    view.set_document(make_document())
    pump(40)
    assert view.scroll.verticalScrollBar().value() == 0
    view.close()
