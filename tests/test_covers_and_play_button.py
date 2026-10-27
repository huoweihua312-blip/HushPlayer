"""列表封面按需刷新 + 播放按钮图标居中。

用户反馈两件事：
1. 歌曲列表第一次渲染只有音符占位，要滚动/悬停一下封面才出现；
2. 播放栏中间圆钮里的三角看起来不在正中。

第 1 条是列表没有监听 ``covers.ready``（封面是后台线程下载的，下载完成
后没有行重绘）；第 2 条改用手绘图标集里按 24 网格设计的 play/pause 字形。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.model.track import Track
from hushplayer.ui.widgets import tracklist
from hushplayer.ui.widgets.common import PlayButton
from hushplayer.ui.widgets.tracklist import TrackListWidget


class _Covers(QObject):
    ready = Signal(str)

    def pixmap(self, track, size):  # noqa: ANN001, ANN201
        return None


class _Ctx:
    def __init__(self, covers: _Covers) -> None:
        self.covers = covers


class _RecordingViewport:
    """接管 ``QWidget.viewport()``，只记录重绘请求。"""

    def __init__(self, width: int = 900) -> None:
        self.updates: list[tuple] = []
        self._width = width

    def update(self, *args) -> None:  # noqa: ANN002
        self.updates.append(args)

    def width(self) -> int:
        return self._width


def _make_tracks(count: int = 3) -> list[Track]:
    return [
        Track(
            id=f"local:t{i}",
            kind="local",
            title=f"歌曲 {i}",
            artist="歌手",
            duration_ms=200_000,
        )
        for i in range(count)
    ]


def _widget(qapp, monkeypatch) -> tuple[TrackListWidget, _Covers]:
    covers = _Covers()
    monkeypatch.setattr(tracklist, "ctx", lambda: _Ctx(covers))
    widget = TrackListWidget()
    widget.resize(900, 400)
    widget.set_tracks(_make_tracks(3))
    return widget, covers


def test_cover_ready_repaints_only_that_row(qapp, monkeypatch) -> None:
    widget, covers = _widget(qapp, monkeypatch)
    table = widget.table
    # 构造时还没有 ctx；第一次绘制才接线（和线上一致）。
    table._connect_covers()
    assert table._covers_connected is True

    viewport = _RecordingViewport()
    table.viewport = lambda: viewport  # type: ignore[method-assign]
    covers.ready.emit("local:t1")
    assert len(viewport.updates) == 1
    args = viewport.updates[0]
    assert len(args) == 1
    rect = args[0]
    assert rect.isValid()
    assert rect.width() > 300  # 整行，而不是只有封面那一格
    assert rect.height() > 20


def test_cover_wiring_is_idempotent_and_ignores_unknown_ids(qapp, monkeypatch) -> None:
    widget, covers = _widget(qapp, monkeypatch)
    table = widget.table
    table._connect_covers()
    table._connect_covers()  # 第二次不应重复连接
    viewport = _RecordingViewport()
    table.viewport = lambda: viewport  # type: ignore[method-assign]
    covers.ready.emit("local:t1")
    assert len(viewport.updates) == 1
    covers.ready.emit("missing:track")
    assert len(viewport.updates) == 1


def test_track_table_connects_covers_on_first_paint(qapp, monkeypatch) -> None:
    widget, _covers = _widget(qapp, monkeypatch)
    table = widget.table
    assert table._covers_connected is False
    widget.show()
    qapp.processEvents()
    assert table._covers_connected is True
    widget.hide()


def test_play_button_triangle_is_optically_centred(qapp) -> None:
    button = PlayButton(40)
    button.resize(40, 40)
    pixmap = button.grab()
    image = pixmap.toImage()
    total = 0
    weight = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.red() > 200 and color.green() > 200 and color.blue() > 200:
                total += x
                weight += 1
    assert weight > 30  # 三角确实画出来了
    centre = (image.width() - 1) / 2
    assert abs(total / weight - centre) <= 1.5
