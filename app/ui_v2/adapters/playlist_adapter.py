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
        self._can_mutate = not self._read_only
        self._mutation_backend: object | None = None
        self._clock = datetime(2026, 2, 1, 9, 0)
        self._next_playlist_number = 1
        self._playlists = self._create_initial_playlists() if seed_mock else []

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def can_mutate(self) -> bool:
        """Whether playlist metadata and membership actions may be persisted."""

        return self._can_mutate

    @property
    def mutation_backend(self) -> object | None:
        return self._mutation_backend

    def set_mutation_backend(self, backend: object | None) -> None:
        """Attach the existing runtime bridge used for real playlist writes."""

        self._mutation_backend = backend
        self._can_mutate = backend is not None or not self._read_only

    def playlists(self) -> tuple[Playlist, ...]:
        return tuple(self._playlists)

    def playlist_for_id(self, playlist_id: str) -> Playlist | None:
        return next((item for item in self._playlists if item.id == playlist_id), None)

    def create_playlist(self, name: str = "", description: str = "") -> Playlist | None:
        if not self._can_mutate:
            return None
        title = str(name or "").strip()
        if not title:
            return None
        playlist_id = self._next_playlist_id()
        playlist = Playlist(
            id=playlist_id,
            name=title,
            created_at=self._next_timestamp(),
            description=str(description or "").strip(),
        )
        self._next_playlist_number += 1
        if not self._persist(
            "create_playlist",
            playlist.id,
            playlist.name,
            playlist.description,
            int(playlist.created_at.timestamp() * 1000),
        ):
            return None
        self._playlists.append(playlist)
        self.playlists_changed.emit(self.playlists())
        return playlist

    def rename_playlist(self, playlist_id: str, name: str) -> bool:
        if not self._can_mutate or str(playlist_id or "") == "liked":
            return False
        title = str(name or "").strip()
        if not title:
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        if not self._persist("rename_playlist", playlist_id, title):
            return False
        self._playlists[index] = replace(self._playlists[index], name=title)
        self.playlists_changed.emit(self.playlists())
        self.playlist_changed.emit(playlist_id)
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        if not self._can_mutate or str(playlist_id or "") == "liked":
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        if not self._persist("delete_playlist", playlist_id):
            return False
        del self._playlists[index]
        self.playlists_changed.emit(self.playlists())
        self.playlist_changed.emit(playlist_id)
        return True

    def add_tracks(self, playlist_id: str, track_ids: Iterable[str]) -> int:
        if not self._can_mutate:
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
        if self._mutation_backend is not None:
            members = [
                member
                for track_id in new_ids
                if (member := self._track_member(track_id)) is not None
            ]
            if len(members) != len(new_ids):
                return 0
            if self._persist("add_playlist_members", playlist_id, members) != len(members):
                return 0
        entries = list(playlist.entries)
        for track_id in new_ids:
            entries.append(PlaylistEntry(track_id, self._next_timestamp()))
        self._playlists[index] = replace(playlist, entries=tuple(entries))
        self.playlist_changed.emit(playlist_id)
        return len(new_ids)

    def remove_track(self, playlist_id: str, track_id: str) -> bool:
        if not self._can_mutate:
            return False
        index = self._playlist_index(playlist_id)
        if index is None:
            return False
        playlist = self._playlists[index]
        entries = tuple(entry for entry in playlist.entries if entry.track_id != track_id)
        if len(entries) == len(playlist.entries):
            return False
        if self._mutation_backend is not None:
            member = self._track_member(track_id)
            if member is None or self._persist(
                "remove_playlist_members", playlist_id, (member,)
            ) != 1:
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

    def set_playlists(
        self,
        playlists: Iterable[Playlist],
        *,
        read_only: bool = True,
        can_mutate: bool | None = None,
    ) -> None:
        """Replace presentation data from a read-only external snapshot."""

        self._playlists = list(playlists)
        self._read_only = bool(read_only)
        self._can_mutate = (
            bool(can_mutate)
            if can_mutate is not None
            else self._mutation_backend is not None or not self._read_only
        )
        self._next_playlist_number = self._next_available_playlist_number()
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

    def _next_playlist_id(self) -> str:
        candidate = self._next_available_playlist_number()
        return f"playlist-custom-{candidate}"

    def _next_available_playlist_number(self) -> int:
        used = {item.id for item in self._playlists}
        candidate = max(1, int(self._next_playlist_number))
        while f"playlist-custom-{candidate}" in used:
            candidate += 1
        return candidate

    def _persist(self, method_name: str, *args):
        if self._mutation_backend is None:
            return True
        method = getattr(self._mutation_backend, method_name, None)
        if not callable(method):
            return False
        try:
            return method(*args)
        except Exception:
            return False

    def _track_member(self, track_id: str) -> tuple[str, str] | None:
        track = self.collection.track_for_id(track_id)
        if track is None:
            return None
        if track.is_online:
            identifier = str(
                track.remote_identity
                or track.remote_track_id
                or track.stable_identity
                or track.id
            ).strip()
            return ("remote", identifier) if identifier else None
        identifier = str(track.local_path or track.id).strip()
        return ("local", identifier) if identifier else None

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
            visible_tracks = [
                track
                for track in self.playlists.tracks_for_playlist(self._playlist_id)
                if self._matches(track)
            ]
            self._visible_tracks = visible_tracks
            if emit:
                self.tracks_reset.emit(tuple(self._visible_tracks))
            return
        super()._rebuild_visible_tracks(emit)

    def _on_playlist_changed(self, playlist_id: str) -> None:
        if playlist_id == self._playlist_id:
            self._rebuild_visible_tracks()

    def _on_playlists_changed(self, _playlists) -> None:
        self._rebuild_visible_tracks()
