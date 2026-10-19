"""自绘控件的无障碍名称：屏幕阅读器与 UI 自动化都依赖它。"""

from __future__ import annotations

from hushplayer.ui.widgets.common import IconButton, PlayButton, TextButton
from hushplayer.ui.widgets.searchfield import SearchField
from hushplayer.ui.widgets.sliders import SeekBar, VolumeSlider
from hushplayer.ui.widgets.tracklist import TrackListWidget


def test_icon_button_uses_tooltip_as_name(qapp) -> None:
    button = IconButton("queue", tooltip="播放队列 (Ctrl+Q)")
    assert button.accessibleName() == "播放队列"


def test_text_button_tracks_its_label(qapp) -> None:
    button = TextButton("播放")
    assert button.accessibleName() == "播放"
    button.set_text("暂停")
    assert button.accessibleName() == "暂停"


def test_play_button_reflects_state(qapp) -> None:
    button = PlayButton()
    button.set_playing(False)
    assert button.accessibleName() == "播放"
    button.set_playing(True)
    assert button.accessibleName() == "暂停"


def test_sliders_and_search_have_names(qapp) -> None:
    assert SeekBar().accessibleName() == "播放进度"
    assert VolumeSlider().accessibleName() == "音量"
    field = SearchField()
    assert field.accessibleName() == "搜索"
    assert field.edit.accessibleName() == "搜索"


def test_track_table_is_named(qapp) -> None:
    assert TrackListWidget().table.accessibleName() == "歌曲列表"
