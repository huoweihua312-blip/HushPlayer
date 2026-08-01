"""Read-only UI V2 projection of the formal local-library services."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository, LibrarySnapshot
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.artists_adapter import (
    album_identity,
    artist_identity,
    normalize_album,
    normalize_artist,
)
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.album import Album
from app.ui_v2.models.artist import Artist
from app.ui_v2.models.playlist import Playlist, PlaylistEntry
from app.ui_v2.models.track import Track


def ui_v2_data_mode() -> str:
    """Return the explicit V2 data mode; mock remains the safe default."""

    return (
        "real"
        if str(os.environ.get("HUSHPLAYER_UI_V2_DATA_MODE") or "").strip().casefold()
        == "real"
        else "mock"
    )


@dataclass(frozen=True, slots=True)
class RealLibraryData:
    tracks: tuple[Track, ...]
    favorites: tuple[Track, ...]
    recent_tracks: tuple[Track, ...]
    artists: tuple[Artist, ...]
    albums: tuple[Album, ...]
    playlists: tuple[Playlist, ...]
    tracks_by_id: dict[str, Track]
    artist_track_ids: dict[str, tuple[str, ...]]
    album_track_ids: dict[str, tuple[str, ...]]
    playlist_track_ids: dict[str, tuple[str, ...]]


class _SnapshotWorker(QObject):
    completed = Signal(int, object, str)

    def __init__(
        self,
        generation: int,
        repository: LibraryRepository,
        remote_tracks: RemoteTrackStore,
    ) -> None:
        super().__init__()
        self._generation = generation
        self._repository = repository
        self._remote_tracks = remote_tracks

    @Slot()
    def run(self) -> None:
        try:
            snapshot = self._repository.load_snapshot()
            if snapshot.library.status == "error":
                raise RuntimeError(snapshot.library.error or "读取音乐库失败")
            if snapshot.playlists.load_error:
                raise RuntimeError(snapshot.playlists.load_error)
            data = RealLibraryAdapter.map_snapshot(
                snapshot,
                self._remote_tracks.load_tracks(),
            )
        except Exception as error:  # reported to the UI thread without fallback
            self.completed.emit(self._generation, None, str(error))
            return
        self.completed.emit(self._generation, data, "")


class RealLibraryAdapter(QObject):
    """Asynchronously projects read-only service snapshots onto existing V2 data.

    The worker only reads formal services and creates immutable value objects.
    Collection and page-facing adapters are updated only from this object's UI
    thread slots.
    """

    state_changed = Signal(str, str)
    data_loaded = Signal()

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        parent: QObject | None = None,
        *,
        repository: LibraryRepository | None = None,
        remote_tracks: RemoteTrackStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self.playlist_adapter = playlists
        paths = AppPaths.resolve()
        data_dir = paths.data_dir
        self._repository = repository or LibraryRepository(
            data_dir / "library.json",
            data_dir / "playlists.json",
            data_dir / "stats.json",
        )
        self._remote_tracks = remote_tracks or RemoteTrackStore(
            data_dir / "remote_tracks.json"
        )
        self._thread: QThread | None = None
        self._worker: _SnapshotWorker | None = None
        self._generation = 0
        self._pending_generation = 0
        self._state = "idle"
        self._last_error = ""
        self._data = self._empty_data()
        self._closed = False

    @property
    def repository(self) -> LibraryRepository:
        return self._repository

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_loading(self) -> bool:
        return self._state == "loading"

    def load(self) -> bool:
        if self._closed or self._state == "loading":
            return False
        self._generation += 1
        self._start(self._generation)
        return True

    def refresh(self) -> bool:
        if self._closed:
            return False
        self._generation += 1
        generation = self._generation
        if self._thread is not None:
            self._pending_generation = generation
            self._set_state("loading", "正在刷新音乐库。")
            return True
        self._start(generation)
        return True

    def tracks(self) -> tuple[Track, ...]:
        return self._data.tracks

    def favorites(self) -> tuple[Track, ...]:
        return self._data.favorites

    def recent_tracks(self) -> tuple[Track, ...]:
        return self._data.recent_tracks

    def artists(self) -> tuple[Artist, ...]:
        return self._data.artists

    def artist_tracks(self, artist_id: str) -> tuple[Track, ...]:
        return self._tracks_for_ids(self._data.artist_track_ids.get(str(artist_id), ()))

    def albums(self) -> tuple[Album, ...]:
        return self._data.albums

    def album_tracks(self, album_id: str) -> tuple[Track, ...]:
        return self._tracks_for_ids(self._data.album_track_ids.get(str(album_id), ()))

    def playlists(self) -> tuple[Playlist, ...]:
        return self._data.playlists

    def playlist_tracks(self, playlist_id: str) -> tuple[Track, ...]:
        return self._tracks_for_ids(
            self._data.playlist_track_ids.get(str(playlist_id), ())
        )

    def track_by_id(self, track_id: str) -> Track | None:
        return self._data.tracks_by_id.get(str(track_id or ""))

    def last_error(self) -> str:
        return self._last_error

    def shutdown(self) -> None:
        self._closed = True
        self._generation += 1
        self._pending_generation = 0
        if self._state == "loading":
            self._state = "idle"
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            thread.wait(2_000)

    @staticmethod
    def map_snapshot(
        snapshot: LibrarySnapshot,
        remote_tracks: dict[str, dict],
    ) -> RealLibraryData:
        """Pure worker-side mapping with one-time membership and stats indexes."""

        favorite_members = _favorite_members(snapshot)
        stats_by_path = snapshot.song_stats
        tracks: list[Track] = []
        local_ids_by_path: dict[str, list[str]] = defaultdict(list)
        tracks_by_id: dict[str, Track] = {}

        for record in snapshot.library.tracks:
            path = str(record.get("path") or "")
            if not path:
                continue
            track_id = _local_track_id(record, path)
            if track_id in tracks_by_id:
                track_id = _duplicate_id(track_id, len(tracks))
            favorite_at = favorite_members.get(("local", path))
            stats = stats_by_path.get(path, {})
            track = Track(
                id=track_id,
                title=str(record.get("title") or "未知歌曲"),
                artist=str(record.get("artist") or "未知艺术家"),
                album=str(record.get("album") or "未知专辑"),
                duration_ms=_duration_ms(record.get("duration")),
                source_id="local",
                source_name="本地音乐",
                source_type="local",
                added_at=_timestamp(record.get("added_at")),
                is_favorite=favorite_at is not None,
                is_missing=False,
                is_loading=False,
                artwork_path=None,
                stable_identity=track_id,
                favorite_added_at=_timestamp(favorite_at) if favorite_at else None,
                play_count=_nonnegative_int(stats.get("play_count")),
                last_played_at=_timestamp_or_none(stats.get("last_played")),
                artwork_key=str(
                    record.get("artwork_key")
                    or record.get("local_cover_path")
                    or record.get("cover_path")
                    or track_id
                ),
                availability="available",
                local_path=path,
            )
            tracks.append(track)
            tracks_by_id[track.id] = track
            local_ids_by_path[path].append(track.id)

        for stable_id, record in remote_tracks.items():
            if not isinstance(record, dict) or not str(stable_id or ""):
                continue
            track_id = str(stable_id)
            if track_id in tracks_by_id:
                continue
            favorite_at = favorite_members.get(("remote", track_id))
            local_path = str(record.get("local_path") or "")
            source_id = str(record.get("source_id") or "remote")
            track = Track(
                id=track_id,
                title=str(record.get("title") or "未知歌曲"),
                artist=str(record.get("artist") or "未知艺术家"),
                album=str(record.get("album") or "未知专辑"),
                duration_ms=_duration_ms(record.get("duration")),
                source_id=source_id,
                source_name=source_id,
                source_type="online",
                added_at=_timestamp(record.get("added_at")),
                is_favorite=favorite_at is not None,
                is_missing=not bool(local_path),
                is_loading=False,
                artwork_path=None,
                stable_identity=track_id,
                favorite_added_at=_timestamp(favorite_at) if favorite_at else None,
                artwork_key=str(record.get("artwork") or track_id),
                availability="downloaded" if local_path else "source-unavailable",
                local_path=local_path,
                remote_identity=track_id,
            )
            tracks.append(track)
            tracks_by_id[track.id] = track

        playlists, playlist_track_ids = _map_playlists(
            snapshot,
            tracks_by_id,
            local_ids_by_path,
        )
        artists, artist_track_ids, albums, album_track_ids = _map_entities(tracks)
        favorites = tuple(
            sorted(
                (track for track in tracks if track.is_favorite),
                key=lambda track: track.favorite_added_at or datetime.min,
                reverse=True,
            )
        )
        recent_tracks = tuple(
            sorted(
                (track for track in tracks if track.last_played_at is not None),
                key=lambda track: track.last_played_at or datetime.min,
                reverse=True,
            )
        )
        return RealLibraryData(
            tracks=tuple(tracks),
            favorites=favorites,
            recent_tracks=recent_tracks,
            artists=artists,
            albums=albums,
            playlists=playlists,
            tracks_by_id=tracks_by_id,
            artist_track_ids=artist_track_ids,
            album_track_ids=album_track_ids,
            playlist_track_ids=playlist_track_ids,
        )

    def _start(self, generation: int) -> None:
        if self._closed or self._thread is not None:
            return
        self._set_state("loading", "正在加载音乐库。")
        # The worker may still be unwinding a read when the window closes.
        # Keep the QThread independent of the widget tree; it deletes itself
        # once finished rather than being destroyed with a running MainWindow.
        thread = QThread()
        worker = _SnapshotWorker(
            generation,
            self._repository,
            self._remote_tracks,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_worker_completed)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(int, object, str)
    def _on_worker_completed(
        self,
        generation: int,
        data: RealLibraryData | None,
        error: str,
    ) -> None:
        if self._closed or generation != self._generation:
            return
        if error or data is None:
            self._last_error = error or "读取音乐库失败"
            self._set_state("error", self._last_error)
            return
        self._data = data
        self._last_error = ""
        self.collection.set_tracks(data.tracks)
        self.playlist_adapter.set_playlists(data.playlists, read_only=True)
        self._set_state("empty" if not data.tracks else "loaded", "")
        self.data_loaded.emit()

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        if self._closed or not self._pending_generation:
            return
        generation = self._pending_generation
        self._pending_generation = 0
        self._start(generation)

    def _tracks_for_ids(self, track_ids: Iterable[str]) -> tuple[Track, ...]:
        return tuple(
            track
            for track_id in track_ids
            if (track := self._data.tracks_by_id.get(track_id)) is not None
        )

    def _set_state(self, state: str, detail: str) -> None:
        self._state = state
        self.state_changed.emit(state, detail)

    @staticmethod
    def _empty_data() -> RealLibraryData:
        return RealLibraryData((), (), (), (), (), (), {}, {}, {}, {})


def _favorite_members(snapshot: LibrarySnapshot) -> dict[tuple[str, str], int]:
    liked = snapshot.playlists.playlists.get("liked", {})
    members = liked.get("members", ()) if isinstance(liked, dict) else ()
    result: dict[tuple[str, str], int] = {}
    for member in members:
        if not isinstance(member, dict):
            continue
        kind = str(member.get("kind") or "")
        identifier = str(member.get("id") or "")
        if kind in {"local", "remote"} and identifier:
            result[(kind, identifier)] = _nonnegative_int(member.get("added_at"))
    return result


def _map_playlists(
    snapshot: LibrarySnapshot,
    tracks_by_id: dict[str, Track],
    local_ids_by_path: dict[str, list[str]],
) -> tuple[tuple[Playlist, ...], dict[str, tuple[str, ...]]]:
    values: list[Playlist] = []
    track_ids_by_playlist: dict[str, tuple[str, ...]] = {}
    for playlist_id, raw_playlist in snapshot.playlists.playlists.items():
        if playlist_id == "liked" or not isinstance(raw_playlist, dict):
            continue
        entries: list[PlaylistEntry] = []
        members = raw_playlist.get("members", ())
        for member in members if isinstance(members, list) else ():
            if not isinstance(member, dict):
                continue
            kind = str(member.get("kind") or "")
            identifier = str(member.get("id") or "")
            member_ids = (
                local_ids_by_path.get(identifier, ())
                if kind == "local"
                else (identifier,) if kind == "remote" else ()
            )
            for track_id in member_ids:
                if track_id in tracks_by_id:
                    entries.append(
                        PlaylistEntry(
                            track_id,
                            _timestamp(member.get("added_at")),
                        )
                    )
        normalized_id = str(playlist_id)
        values.append(
            Playlist(
                id=normalized_id,
                name=str(raw_playlist.get("name") or "未命名歌单"),
                created_at=_timestamp(
                    raw_playlist.get("created_at") or raw_playlist.get("updated_at")
                ),
                description=str(raw_playlist.get("description") or ""),
                entries=tuple(entries),
            )
        )
        track_ids_by_playlist[normalized_id] = tuple(
            entry.track_id for entry in entries
        )
    return tuple(values), track_ids_by_playlist


def _map_entities(
    tracks: Iterable[Track],
) -> tuple[
    tuple[Artist, ...],
    dict[str, tuple[str, ...]],
    tuple[Album, ...],
    dict[str, tuple[str, ...]],
]:
    artist_ids: dict[str, list[str]] = defaultdict(list)
    artist_albums: dict[str, set[str]] = defaultdict(set)
    artist_durations: dict[str, int] = defaultdict(int)
    artist_names: dict[str, str] = {}
    album_ids: dict[str, list[str]] = defaultdict(list)
    album_durations: dict[str, int] = defaultdict(int)
    album_labels: dict[str, tuple[str, str]] = {}
    for track in tracks:
        artist_name = normalize_artist(track.artist)
        artist_id = artist_identity(artist_name)
        album_title = normalize_album(track.album)
        album_id = album_identity(album_title, artist_name)
        artist_ids[artist_id].append(track.id)
        artist_albums[artist_id].add(album_id)
        artist_durations[artist_id] += track.duration_ms or 0
        artist_names[artist_id] = artist_name
        album_ids[album_id].append(track.id)
        album_durations[album_id] += track.duration_ms or 0
        album_labels[album_id] = (album_title, artist_name)
    artists = tuple(
        sorted(
            (
                Artist(
                    id=artist_id,
                    name=artist_names[artist_id],
                    track_ids=tuple(track_ids),
                    album_ids=tuple(sorted(artist_albums[artist_id])),
                    total_duration_ms=artist_durations[artist_id],
                )
                for artist_id, track_ids in artist_ids.items()
            ),
            key=lambda artist: artist.name.casefold(),
        )
    )
    albums = tuple(
        sorted(
            (
                Album(
                    id=album_id,
                    title=album_labels[album_id][0],
                    artist=album_labels[album_id][1],
                    track_ids=tuple(track_ids),
                    total_duration_ms=album_durations[album_id],
                )
                for album_id, track_ids in album_ids.items()
            ),
            key=lambda album: (album.title.casefold(), album.artist.casefold()),
        )
    )
    return (
        artists,
        {key: tuple(value) for key, value in artist_ids.items()},
        albums,
        {key: tuple(value) for key, value in album_ids.items()},
    )


def _local_track_id(record: dict, path: str) -> str:
    existing = str(
        record.get("stable_id")
        or record.get("stableIdentity")
        or record.get("stable_identity")
        or record.get("track_id")
        or ""
    )
    return existing or f"local:{path.casefold()}"


def _duplicate_id(track_id: str, index: int) -> str:
    return f"{track_id}#{index}"


def _duration_ms(value) -> int | None:
    try:
        duration = float(value or 0)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return int(round(duration if duration > 86_400 else duration * 1_000))


def _nonnegative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _timestamp_or_none(value) -> datetime | None:
    raw = _nonnegative_int(value)
    return _timestamp(raw) if raw else None


def _timestamp(value) -> datetime:
    raw = _nonnegative_int(value)
    if raw > 4_102_444_800:
        raw //= 1_000
    try:
        return datetime.fromtimestamp(raw)
    except (OverflowError, OSError, ValueError):
        return datetime(1970, 1, 1)
