"""可收起音源列表的窗口计算。"""

from __future__ import annotations

from hushplayer.ui.pages.settings import SOURCES_COLLAPSED_VISIBLE, source_window


def test_short_list_is_always_fully_visible() -> None:
    assert source_window(3, expanded=False) == (3, 0)
    assert source_window(SOURCES_COLLAPSED_VISIBLE, expanded=False) == (SOURCES_COLLAPSED_VISIBLE, 0)


def test_long_list_collapses_to_the_limit() -> None:
    visible, hidden = source_window(7, expanded=False)
    assert visible == SOURCES_COLLAPSED_VISIBLE
    assert hidden == 3


def test_expanded_list_shows_everything() -> None:
    assert source_window(7, expanded=True) == (7, 0)
