"""The shared-collection favorite view for UI V2 stage three."""

from __future__ import annotations

from app.ui_v2.adapters.favorites_adapter import FavoritesAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme


class FavoritesPage(TrackListPage):
    def __init__(self, adapter: FavoritesAdapter, theme: Theme, parent=None) -> None:
        super().__init__("我喜欢", adapter, theme, parent)
        self.empty_state.set_state("empty", "收藏歌曲会显示在这里。")
        self.empty_state.set_action("浏览音乐库")
