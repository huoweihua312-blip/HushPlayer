"""Reusable route page for the active mock playlist."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QInputDialog

from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter, PlaylistTrackAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.playlist_header import PlaylistHeader


class PlaylistPage(TrackListPage):
    playlist_deleted = Signal(str)

    def __init__(
        self,
        adapter: PlaylistTrackAdapter,
        playlists: PlaylistAdapter,
        theme: Theme,
        parent=None,
    ) -> None:
        self.playlists = playlists
        super().__init__("歌单", adapter, theme, parent)
        self.playlist_header = PlaylistHeader(theme, self)
        layout = self.layout()
        layout.replaceWidget(self.header, self.playlist_header)
        self.header.hide()
        self.header = self.playlist_header
        self.toolbar.hide()
        self.playlist_header.play_requested.connect(lambda: self._request_queue(False))
        self.playlist_header.shuffle_requested.connect(lambda: self._request_queue(True))
        self.playlist_header.rename_requested.connect(self._rename_playlist)
        self.playlist_header.delete_requested.connect(self._delete_playlist)
        self.playlist_header.add_requested.connect(self._add_first_available_track)
        self.track_table.set_playlist_context(self._remove_track_from_current_playlist)
        playlists.playlist_changed.connect(self._on_playlist_changed)
        self.empty_state.set_state("empty", "这个 mock 歌单还没有歌曲。")
        self.set_theme(theme)
        self._on_tracks_reset(adapter.tracks())

    @property
    def playlist_id(self) -> str:
        return self.adapter.playlist_id

    def set_playlist(self, playlist_id: str) -> None:
        self.adapter.set_playlist(playlist_id)
        self.playlist_header.set_playlist(
            self.playlists.playlist_for_id(playlist_id), self.adapter.tracks()
        )

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
        playlist = self.playlists.playlist_for_id(self.playlist_id)
        if playlist is None:
            return
        title, accepted = QInputDialog.getText(self, "重命名 mock 歌单", "歌单名称", text=playlist.name)
        if accepted:
            self.playlists.rename_playlist(playlist.id, title)

    def _delete_playlist(self) -> None:
        playlist_id = self.playlist_id
        if playlist_id and self.playlists.delete_playlist(playlist_id):
            self.playlist_deleted.emit(playlist_id)

    def _add_first_available_track(self) -> None:
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
        self.playlists.remove_track(self.playlist_id, track_id)
