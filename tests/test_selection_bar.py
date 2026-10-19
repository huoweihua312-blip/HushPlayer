"""批量操作条：选择数量驱动显隐，页面动作真的落到队列/收藏。"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel

from hushplayer.model.track import Track
from hushplayer.ui.widgets.selectionbar import SelectionBar
from hushplayer.ui.widgets.tracklist import TrackListWidget


def make_tracks(count: int = 4) -> list[Track]:
    return [
        Track(id=f"local:t{i}", kind="local", title=f"歌曲 {i}", artist="歌手", duration_ms=200_000)
        for i in range(count)
    ]


def test_bar_only_shows_for_multi_selection(qapp) -> None:
    bar = SelectionBar()
    bar.set_selection(0)
    assert not bar.isVisibleTo(None)
    bar.set_selection(1)
    assert not bar.isVisibleTo(None)
    bar.set_selection(3)
    assert bar.isVisibleTo(None)
    assert bar.count() == 3
    assert "3" in bar.count_label.text()


def test_remove_button_follows_context(qapp) -> None:
    bar = SelectionBar()
    bar.set_selection(2, can_remove=False)
    assert not bar.remove_button.isVisibleTo(bar)
    bar.set_selection(2, can_remove=True)
    assert bar.remove_button.isVisibleTo(bar)


def test_list_shows_bar_when_rows_selected(qapp) -> None:
    widget = TrackListWidget()
    widget.resize(900, 400)
    widget.set_tracks(make_tracks(4))
    table = widget.table
    table.selectionModel().clearSelection()
    for row in range(2):
        index = table.model().index(row, 1)
        table.selectionModel().select(
            index,
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
    assert widget.selection_bar.isVisibleTo(widget)
    assert widget.selection_bar.count() == 2

    widget.clear_selection()
    assert not widget.selection_bar.isVisibleTo(widget)
