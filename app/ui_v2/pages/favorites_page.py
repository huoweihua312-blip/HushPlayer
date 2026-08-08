"""The shared-collection favorite view for UI V2 stage three."""

from __future__ import annotations

from app.ui_v2.adapters.favorites_adapter import FavoritesAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.track_collection_hero import TrackCollectionHero


class FavoritesPage(TrackListPage):
    def __init__(self, adapter: FavoritesAdapter, theme: Theme, parent=None) -> None:
        super().__init__("我喜欢", adapter, theme, parent)
        self.collection_hero = TrackCollectionHero(theme, self)
        layout = self.layout()
        layout.replaceWidget(self.header, self.collection_hero)
        self.header.hide()
        self.toolbar.hide()
        self.collection_hero.play_requested.connect(lambda: self._request_queue(False))
        self.collection_hero.shuffle_requested.connect(lambda: self._request_queue(True))
        self.empty_state.set_state("empty", "收藏歌曲会显示在这里。")
        self.empty_state.set_action("浏览音乐库")
        self._on_tracks_reset(adapter.tracks())

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if hasattr(self, "collection_hero"):
            self.collection_hero.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        super().set_responsive_reference_width(width)
        if hasattr(self, "collection_hero"):
            self.collection_hero.set_responsive_reference_width(width)

    def _on_tracks_reset(self, tracks) -> None:
        super()._on_tracks_reset(tracks)
        if hasattr(self, "collection_hero"):
            self.collection_hero.set_content(
                "我喜欢", f"{len(tracks)} 首收藏歌曲", tracks, "收藏"
            )
