"""All Songs collection page for UI V2 content stage 2A."""

from __future__ import annotations

from PySide6.QtCore import Signal

from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.collection_action_row import CollectionActionRow


class AllSongsPage(LibraryPage):
    """Keeps the approved Library data flow with a compact action row."""

    play_requested = Signal()
    shuffle_requested = Signal()

    def __init__(self, adapter, theme: Theme | None = None, parent=None) -> None:
        # All Songs uses the shell TitleBar search.  The page-local query and
        # preview controls are not constructed, so the approved header has no
        # hidden widgets or reserved trailing space.
        super().__init__(
            adapter,
            theme,
            parent,
            include_page_search=False,
            include_preview_controls=False,
        )
        self.collection_actions = CollectionActionRow(self._theme, self)
        self.collection_actions.play_requested.connect(self.play_requested)
        self.collection_actions.shuffle_requested.connect(self.shuffle_requested)
        self.layout().insertWidget(1, self.collection_actions)
        self.set_playback_enabled(not adapter.collection.read_only)

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if hasattr(self, "collection_actions"):
            self.collection_actions.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        super().set_responsive_reference_width(width)
        if hasattr(self, "collection_actions"):
            self.collection_actions.set_compact(int(width) < 950)

    def set_playback_enabled(self, enabled: bool) -> None:
        self.track_table.set_playback_enabled(bool(enabled))
        if hasattr(self, "collection_actions"):
            self.collection_actions.play_button.setEnabled(bool(enabled) and bool(self.adapter.tracks()))
            self.collection_actions.shuffle_button.setEnabled(bool(enabled) and bool(self.adapter.tracks()))
            tip = "播放功能尚未接入真实模式" if not enabled else ""
            self.collection_actions.play_button.setToolTip(tip or "播放全部歌曲")
            self.collection_actions.shuffle_button.setToolTip(tip or "随机播放全部歌曲")
