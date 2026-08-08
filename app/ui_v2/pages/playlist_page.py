"""Reusable route page for the active mock playlist."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QVBoxLayout, QWidget

from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter, PlaylistTrackAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.content_heroes import PlaylistHero
from app.ui_v2.widgets.related_playlists_panel import RelatedPlaylistsPanel


class PlaylistPage(TrackListPage):
    playlist_deleted = Signal(str)
    playlist_requested = Signal(str)

    def __init__(
        self,
        adapter: PlaylistTrackAdapter,
        playlists: PlaylistAdapter,
        theme: Theme,
        parent=None,
    ) -> None:
        self.playlists = playlists
        super().__init__("歌单", adapter, theme, parent)
        self.playlist_header = PlaylistHero(theme, self)
        self.playlist_hero = self.playlist_header
        layout = self.layout()
        layout.replaceWidget(self.header, self.playlist_header)
        self.header.hide()
        self.header = self.playlist_header
        self.toolbar.hide()
        self.related_playlists = RelatedPlaylistsPanel(playlists, theme, self)
        content_row = QWidget(self)
        content_layout = QHBoxLayout(content_row)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(theme.metrics.spacing_xl)
        layout.replaceWidget(self.view_host, content_row)
        self.view_host.setParent(content_row)
        content_layout.addWidget(self.view_host, 1)
        content_layout.addWidget(self.related_playlists)
        self.playlist_header.play_requested.connect(lambda: self._request_queue(False))
        self.playlist_header.shuffle_requested.connect(lambda: self._request_queue(True))
        self.playlist_header.rename_requested.connect(self._rename_playlist)
        self.playlist_header.delete_requested.connect(self._delete_playlist)
        self.playlist_header.add_requested.connect(self._add_first_available_track)
        self.playlist_header.set_read_only(playlists.read_only)
        self.playlist_header.set_playback_enabled(not playlists.read_only)
        self.track_table.set_playback_enabled(not playlists.read_only)
        self.playlist_header.favorite_requested.connect(self._on_favorite_requested)
        self.related_playlists.playlist_requested.connect(self._open_related_playlist)
        self.track_table.set_playlist_context(
            None if playlists.read_only else self._remove_track_from_current_playlist
        )
        playlists.playlist_changed.connect(self._on_playlist_changed)
        self.empty_state.set_state("empty", "这个歌单还没有歌曲。")
        self.set_theme(theme)
        self._on_tracks_reset(adapter.tracks())

    @property
    def playlist_id(self) -> str:
        return self.adapter.playlist_id

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if hasattr(self, "related_playlists"):
            self.related_playlists.set_theme(theme)

    def set_playlist(self, playlist_id: str) -> None:
        self.adapter.set_playlist(playlist_id)
        self.playlist_header.set_playlist(
            self.playlists.playlist_for_id(playlist_id), self.adapter.tracks()
        )

    def set_responsive_reference_width(self, width: int) -> None:
        super().set_responsive_reference_width(width)
        self.playlist_header.set_responsive_reference_width(width)
        self.related_playlists.set_responsive_reference_width(width)

    def _on_tracks_reset(self, tracks) -> None:
        if not hasattr(self, "playlist_header"):
            super()._on_tracks_reset(tracks)
            return
        self.playlist_header.set_playlist(
            self.playlists.playlist_for_id(self.playlist_id), tracks
        )
        self.toolbar.setEnabled(bool(tracks))
        if not tracks:
            self.current_view_state = "empty"
            self.view_stack.setCurrentWidget(self.empty_state)
        elif self.current_view_state == "empty":
            self.current_view_state = "content"
            self.view_stack.setCurrentWidget(self.track_table)

    def _on_playlist_changed(self, playlist_id: str) -> None:
        if playlist_id == self.playlist_id:
            self.playlist_header.set_playlist(
                self.playlists.playlist_for_id(playlist_id), self.adapter.tracks()
            )

    def _rename_playlist(self) -> None:
        if self.playlists.read_only:
            return
        playlist = self.playlists.playlist_for_id(self.playlist_id)
        if playlist is None:
            return
        title, accepted = QInputDialog.getText(self, "重命名歌单", "歌单名称", text=playlist.name)
        if accepted:
            self.playlists.rename_playlist(playlist.id, title)

    def _delete_playlist(self) -> None:
        if self.playlists.read_only:
            return
        playlist_id = self.playlist_id
        if playlist_id and self.playlists.delete_playlist(playlist_id):
            self.playlist_deleted.emit(playlist_id)

    def _add_first_available_track(self) -> None:
        if self.playlists.read_only:
            return
        playlist = self.playlists.playlist_for_id(self.playlist_id)
        if playlist is None:
            return
        next_track = next(
            (
                track
                for track in self.adapter.all_tracks()
                if not track.is_missing and track.id not in playlist.track_ids
            ),
            None,
        )
        if next_track is not None:
            self.playlists.add_tracks(playlist.id, (next_track.id,))

    def _remove_track_from_current_playlist(self, track_id: str) -> None:
        if self.playlists.read_only:
            return
        self.playlists.remove_track(self.playlist_id, track_id)

    def _on_favorite_requested(self, value: bool) -> None:
        # Playlist values intentionally have no persistence field yet. Mock
        # keeps the visual toggle local; real mode disables the control.
        self.playlist_header._favorite = bool(value)
        self.playlist_header.set_theme(self._theme)

    def _open_related_playlist(self, playlist_id: str) -> None:
        if playlist_id != self.playlist_id:
            self.playlist_requested.emit(playlist_id)
