"""Playlist-specific actions layered onto the shared collection Hero."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from app.ui_v2.models.playlist import Playlist
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.track_collection_hero import TrackCollectionHero


class PlaylistHeader(TrackCollectionHero):
    """Keeps playlist management in an overflow menu beside Hero playback."""

    rename_requested = Signal()
    delete_requested = Signal()
    add_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(theme, parent)
        # Preserve the small public action handles used by the existing page,
        # while the actual page surface keeps them inside one overflow menu.
        self.add_button = QToolButton(self)
        self.rename_button = QToolButton(self)
        self.delete_button = QToolButton(self)
        self.add_button.clicked.connect(self.add_requested)
        self.rename_button.clicked.connect(self.rename_requested)
        self.delete_button.clicked.connect(self.delete_requested)
        self._more_menu = QMenu(self)
        add_action = self._more_menu.addAction("添加歌曲")
        rename_action = self._more_menu.addAction("重命名")
        self._more_menu.addSeparator()
        delete_action = self._more_menu.addAction("删除歌单")
        add_action.triggered.connect(self.add_requested)
        rename_action.triggered.connect(self.rename_requested)
        delete_action.triggered.connect(self.delete_requested)
        self.more_requested.connect(self._show_more_menu)

    def set_read_only(self, value: bool) -> None:
        self.more_button.setVisible(not bool(value))
        self.more_button.setEnabled(not bool(value))

    def set_playlist(
        self, playlist: Playlist | None, tracks: Iterable[Track] = ()
    ) -> None:
        materialized = tuple(tracks)
        if playlist is None:
            self.set_content("歌单", "歌单不存在", materialized, "歌单")
            return
        metadata = f"{len(playlist.entries)} 首歌曲  ·  更新于 {playlist.created_at:%Y-%m-%d}"
        self.set_content(playlist.name, metadata, materialized, "歌单")
        self.meta_label.setToolTip(playlist.description or metadata)

    def _show_more_menu(self) -> None:
        self._more_menu.popup(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))
