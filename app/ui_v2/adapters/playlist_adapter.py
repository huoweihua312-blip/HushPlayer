"""Mock playlist CRUD and filtered playlist Track views for UI V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Iterable

from PySide6.QtCore import QObject, Qt, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.models.playlist import Playlist, PlaylistEntry
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


class PlaylistAdapter(QObject):
    """Stores mock playlist metadata and member IDs only."""

    playlists_changed = Signal(object)
    playlist_changed = Signal(str)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        parent: QObject | None = None,
        *,
        seed_mock: bool = True,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self._read_only = bool(read_only)
        self._clock = datetime(2026, 2, 1, 9, 0)
        self._next_playlist_number = 1
        self._playlists = self._create_initial_playlists() if seed_mock else []

    @property
    def read_only(self) -> bool:
        return self._read_only

    def playlists(self) -> tuple[Playlist, ...]:
        return tuple(self._playlists)

    def playlist_for_id(self, playlist_id: str) -> Playlist | None:
        return next((item for item in self._playlists if item.id == playlist_id), None)

    def create_playlist(self, name: str = "", description: str = "") -> Playlist | None:
        if self._read_only:
            return None
        title = str(name or "").strip() or f"新建歌单 {self._next_playlist_number}"
        playlist = Playlist(
            id=f"playlist-custom-{self._next_playlist_number}",
            name=title,
            created_at=self._next_timestamp(),
            description=str(description or "").strip(),
        )
        self._next_playlist_number += 1
        self._playlists.append(playlist)
        self.playlists_changed.emit(self.playlists())
        return playlist

    def rename_playlist(self, playlist_id: str, name: str) -> bool:
        if self._read_only:
            return False
        title = str(name or "").strip()
        if not title:
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        self._playlists[index] = replace(self._playlists[index], name=title)
        self.playlists_changed.emit(self.playlists())
        self.playlist_changed.emit(playlist_id)
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        if self._read_only:
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        del self._playlists[index]
        self.playlists_changed.emit(self.playlists())
        self.playlist_changed.emit(playlist_id)
        return True

    def add_tracks(self, playlist_id: str, track_ids: Iterable[str]) -> int:
        if self._read_only:
            return 0
        index = self._playlist_index(playlist_id)
        if index is None:
            return 0
        playlist = self._playlists[index]
        existing_ids = set(playlist.track_ids)
        valid_ids = self.collection.track_ids()
        new_ids: list[str] = []
        for track_id in track_ids:
            if track_id in valid_ids and track_id not in existing_ids:
                existing_ids.add(track_id)
                new_ids.append(track_id)
        if not new_ids:
            return 0
        entries = list(playlist.entries)
        for track_id in new_ids:
            entries.append(PlaylistEntry(track_id, self._next_timestamp()))
        self._playlists[index] = replace(playlist, entries=tuple(entries))
        self.playlist_changed.emit(playlist_id)
        return len(new_ids)

    def remove_track(self, playlist_id: str, track_id: str) -> bool:
        if self._read_only:
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        playlist = self._playlists[index]
        entries = tuple(entry for entry in playlist.entries if entry.track_id != track_id)
        if len(entries) == len(playlist.entries):
            return False
        self._playlists[index] = replace(playlist, entries=entries)
        self.playlist_changed.emit(playlist_id)
        return True

    def tracks_for_playlist(self, playlist_id: str) -> tuple[Track, ...]:
        playlist = self.playlist_for_id(playlist_id)
        if playlist is None:
            return ()
        entries = playlist.entries if self._read_only else reversed(playlist.entries)
        return self.collection.tracks_for_ids(entry.track_id for entry in entries)

    def set_playlists(self, playlists: Iterable[Playlist], *, read_only: bool = True) -> None:
        """Replace presentation data from a read-only external snapshot."""

        self._playlists = list(playlists)
        self._read_only = bool(read_only)
        self.playlists_changed.emit(self.playlists())

    def added_at(self, playlist_id: str, track_id: str) -> datetime | None:
        playlist = self.playlist_for_id(playlist_id)
        if playlist is None:
            return None
        return next(
            (entry.added_at for entry in playlist.entries if entry.track_id == track_id),
            None,
        )

    def _create_initial_playlists(self) -> list[Playlist]:
        names = (
            "专注时刻",
            "深夜电台与缓慢的城市灯光",
            "周末收藏",
            "通勤节奏",
            "雨天窗口",
            "测试中的长歌单名称用于检查导航文本省略",
            "轻声阅读",
            "空白歌单",
        )
        track_ids = [track.id for track in self.collection.tracks() if not track.is_missing]
        playlists: list[Playlist] = []
        for index, name in enumerate(names, start=1):
            entries = ()
            if index != len(names):
                selected = track_ids[index - 1 :: 19][:9]
                entries = tuple(
                    PlaylistEntry(track_id, self._next_timestamp())
                    for track_id in selected
                )
            playlists.append(
                Playlist(
                    id=f"playlist-seed-{index}",
                    name=name,
                    created_at=self._next_timestamp(),
                    description="UI V2 mock 歌单",
                    entries=entries,
                )
            )
        return playlists

    def _playlist_index(self, playlist_id: str) -> int | None:
        return next(
            (index for index, item in enumerate(self._playlists) if item.id == playlist_id),
            None,
        )

    def _next_timestamp(self) -> datetime:
        self._clock += timedelta(minutes=3)
        return self._clock


class PlaylistTrackAdapter(TrackListAdapter):
    """Track view for one PlaylistAdapter playlist, retaining view-local state."""

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        parent: QObject | None = None,
    ) -> None:
        self.playlists = playlists
        self._playlist_id = ""
        self._preserve_source_order = playlists.read_only
        super().__init__(
            collection,
            parent,
            predicate=self._is_member,
            sort_column=TrackColumn.ADDED_AT,
            sort_order=Qt.SortOrder.DescendingOrder,
        )
        playlists.playlist_changed.connect(self._on_playlist_changed)
        playlists.playlists_changed.connect(self._on_playlists_changed)

    @property
    def playlist_id(self) -> str:
        return self._playlist_id

    def set_playlist(self, playlist_id: str) -> None:
        if playlist_id == self._playlist_id:
            return
        self._playlist_id = playlist_id
        self._rebuild_visible_tracks()

    def _is_member(self, track: Track) -> bool:
        playlist = self.playlists.playlist_for_id(self._playlist_id)
        return playlist is not None and track.id in playlist.track_ids

    def _sort_value(self, track: Track, column: TrackColumn):
        if column == TrackColumn.ADDED_AT:
            return self.playlists.added_at(self._playlist_id, track.id) or track.added_at
        return super()._sort_value(track, column)

    def _rebuild_visible_tracks(self, emit: bool = True) -> None:
        if (
            self._preserve_source_order
            and self._sort_column == TrackColumn.ADDED_AT
            and self._sort_order == Qt.SortOrder.DescendingOrder
        ):
            self._visible_tracks = [
                track
                for track in self.playlists.tracks_for_playlist(self._playlist_id)
                if self._matches(track)
            ]
            if emit:
                self.tracks_reset.emit(tuple(self._visible_tracks))
            return
        super()._rebuild_visible_tracks(emit)

    def _on_playlist_changed(self, playlist_id: str) -> None:
        if playlist_id == self._playlist_id:
            self._rebuild_visible_tracks()

    def _on_playlists_changed(self, _playlists) -> None:
        self._rebuild_visible_tracks()
