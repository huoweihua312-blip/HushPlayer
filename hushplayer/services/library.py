"""Application-level facade over the library store.

The UI never touches SQLite directly: it asks this service for pages of tracks,
albums, artists, playlists and favourites, and listens to its signals for
changes.  All blocking work (scanning, cover extraction) happens on worker
threads owned by ``Scanner`` / ``CoverProvider``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

from PySide6.QtCore import QObject, Signal

from ..core.logging_setup import get_logger
from ..library.artwork import CoverProvider
from ..library.scanner import ScanResult, Scanner
from ..model.track import Track, album_key
from ..store.db import Database
from ..store.repository import (
    LibraryStats,
    LyricBindingRepository,
    MetaStore,
    PlaylistRepository,
    TrackRepository,
)

log = get_logger("services.library")

FAVORITES_NAME = "我喜欢"


@dataclass(slots=True)
class LibraryQuery:
    kind: str = ""          # "" | "local" | "online"
    search: str = ""
    sort: str = "title"
    descending: bool = False
    favorite: bool | None = None
    limit: int = 0
    offset: int = 0


class LibraryService(QObject):
    library_changed = Signal()
    favorites_changed = Signal()
    playlists_changed = Signal()
    scan_started = Signal()
    scan_stage = Signal(str)
    scan_progress = Signal(int, int, str)
    scan_finished = Signal(object)   # ScanResult
    scan_failed = Signal(str)
    track_updated = Signal(str)      # track id
    covers = None                    # CoverProvider, set in __init__

    def __init__(self, db: Database, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.tracks = TrackRepository(db)
        self.playlists = PlaylistRepository(db)
        self.bindings = LyricBindingRepository(db)
        self.meta = MetaStore(db)
        self.covers = CoverProvider(parent=self)
        self.scanner = Scanner(self.tracks, self.meta, parent=self)
        self.scanner.stage.connect(self.scan_stage)
        self.scanner.progress.connect(self.scan_progress)
        self.scanner.finished.connect(self._on_scan_finished)
        self.scanner.failed.connect(self.scan_failed)
        self._scanning = False

    # ---------------------------------------------------------------- status
    @property
    def scanning(self) -> bool:
        return self._scanning

    @property
    def stats(self) -> LibraryStats:
        return self.tracks.stats()

    def favorites_playlist_id(self) -> int:
        for playlist in self.playlists.list():
            if playlist.system or playlist.name == FAVORITES_NAME:
                return playlist.id
        return 0

    # -------------------------------------------------------------- scanning
    def scan(self, folders: Iterable[str] | None = None, *, force: bool = False) -> bool:
        if self._scanning:
            return False
        target = list(folders or [])
        self._scanning = True
        self.scan_started.emit()
        started = self.scanner.start(target)
        if not started:
            self._scanning = False
        return started

    def cancel_scan(self) -> None:
        self.scanner.cancel()

    def import_files(self, paths: Iterable[str]) -> ScanResult:
        result = self.scanner.import_files(list(paths))
        if result.added or result.updated:
            self.library_changed.emit()
        return result

    def _on_scan_finished(self, result: object) -> None:
        self._scanning = False
        self.library_changed.emit()
        if isinstance(result, ScanResult) and (result.added or result.removed or result.updated):
            self.playlists_changed.emit()

    # ---------------------------------------------------------------- queries
    def tracks_page(self, query: LibraryQuery | None = None) -> list[Track]:
        query = query or LibraryQuery()
        return self.tracks.list(
            kind=query.kind,
            search=query.search,
            sort=query.sort,
            descending=query.descending,
            favorite=query.favorite,
            limit=query.limit,
            offset=query.offset,
        )

    def count(self, kind: str = "", search: str = "", favorite: bool | None = None) -> int:
        return self.tracks.count(kind=kind, search=search, favorite=favorite)

    def search_local(self, term: str, limit: int = 60) -> list[Track]:
        return self.tracks.search_local(term, limit=limit)

    def albums(self, search: str = "", limit: int = 0):
        return self.tracks.albums(search=search, limit=limit)

    def artists(self, search: str = "", limit: int = 0):
        return self.tracks.artists(search=search, limit=limit)

    def album_tracks(self, album_id: str) -> list[Track]:
        return self.tracks.album_tracks(album_id)

    def artist_tracks(self, artist_id: str) -> list[Track]:
        return self.tracks.artist_tracks(artist_id)

    def artist_albums(self, artist_id: str):
        return self.tracks.artist_albums(artist_id)

    def recent(self, limit: int = 60) -> list[Track]:
        return self.tracks.recent(limit)

    def recently_added(self, limit: int = 30) -> list[Track]:
        return self.tracks.recently_added(limit)

    def most_played(self, limit: int = 30) -> list[Track]:
        return self.tracks.most_played(limit)

    def track(self, track_id: str) -> Track | None:
        return self.tracks.get(track_id)

    def tracks_by_ids(self, ids: Iterable[str]) -> list[Track]:
        return self.tracks.get_many(list(ids))

    def replace_online_source(self, track_id: str, candidate) -> Track | None:
        """手动把一首在线歌曲换到另一个来源（右键「替换歌曲来源」）。

        走 :class:`TrackBindingService.manual_choose`：立即写入 DB、锁定为
        ``manual``，之后自动回退/重新导入都不能覆盖它。
        """

        bindings = getattr(self, "source_bindings", None)
        if bindings is not None and getattr(candidate, "remote_id", ""):
            from .binding import BindingChoice

            choice = BindingChoice(
                source_id=str(getattr(candidate, "source_id", "") or ""),
                source_name=str(getattr(candidate, "source_name", "") or ""),
                remote_id=str(getattr(candidate, "remote_id", "") or ""),
                title=str(getattr(candidate, "title", "") or ""),
                artist=str(getattr(candidate, "artist", "") or ""),
                album=str(getattr(candidate, "album", "") or ""),
                duration_ms=int(getattr(candidate, "duration_ms", 0) or 0),
                artwork_url=str(getattr(candidate, "artwork_url", "") or ""),
                album_id=str(getattr(candidate, "album_id", "") or ""),
                raw=dict(getattr(candidate, "raw", {}) or {}),
            )
            if bindings.manual_choose(track_id, choice):
                updated = self.tracks.get(track_id)
                if updated is not None:
                    self.covers.invalidate(updated.id)
                    self.track_updated.emit(updated.id)
                return updated

        self.tracks.update_source(
            track_id,
            source_id=candidate.source_id,
            source_name=candidate.source_name,
            remote_id=candidate.remote_id,
            raw=candidate.raw,
            title=candidate.title,
            artist=candidate.artist,
            album=candidate.album,
            duration_ms=candidate.duration_ms,
            artwork_url=candidate.artwork_url,
            album_id=getattr(candidate, "album_id", "") or (
                album_key(candidate.album, candidate.artist)
                if candidate.album else ""
            ),
            artist_id=getattr(candidate, "artist_id", "") or "",
        )
        updated = self.tracks.get(track_id)
        if updated is not None:
            self.covers.invalidate(updated.id)
            self.track_updated.emit(updated.id)
        return updated

    def is_favorite(self, track: Track | str) -> bool:
        track_id = track.id if isinstance(track, Track) else str(track)
        stored = self.tracks.get(track_id)
        return bool(stored.favorite) if stored is not None else False

    def toggle_favorite(self, track: Track) -> bool:
        """Add/remove ``track`` from 我喜欢, persisting online tracks as needed."""
        if track.kind == "online":
            self._ensure_online_album(track)
            stored = self.tracks.get(track.id)
            if stored is None:
                self.tracks.upsert(track)
        state = not self.is_favorite(track)
        self.tracks.set_favorite(track.id, state)
        track.favorite = state
        playlist_id = self.favorites_playlist_id()
        if playlist_id:
            if state:
                self.playlists.add_tracks(playlist_id, [track.id])
            else:
                self.playlists.remove_tracks(playlist_id, [track.id])
        self.favorites_changed.emit()
        self.track_updated.emit(track.id)
        return state

    def set_favorite(self, track: Track, value: bool) -> None:
        if self.is_favorite(track) != bool(value):
            self.toggle_favorite(track)

    def favorites(self, limit: int = 0, offset: int = 0) -> list[Track]:
        return self.tracks.favorites(limit=limit, offset=offset)

    # -------------------------------------------------------------- playlists
    def playlists_all(self):
        return self.playlists.list()

    def playlist(self, playlist_id: int):
        return self.playlists.get(playlist_id)

    def create_playlist(self, name: str, description: str = "") -> int:
        playlist = self.playlists.create(name, description)
        self.playlists_changed.emit()
        return playlist.id

    def rename_playlist(self, playlist_id: int, name: str) -> bool:
        if not name.strip():
            return False
        self.playlists.rename(playlist_id, name)
        self.playlists_changed.emit()
        return True

    def delete_playlist(self, playlist_id: int) -> bool:
        playlist = self.playlists.get(playlist_id)
        if playlist is None or playlist.system:
            return False
        self.playlists.delete(playlist_id)
        self.playlists_changed.emit()
        return True

    def playlist_tracks(self, playlist_id: int, search: str = "") -> list[Track]:
        return self.playlists.tracks(playlist_id, search=search)

    def add_to_playlist(self, playlist_id: int, tracks: Iterable[Track]) -> int:
        items = [track for track in tracks if track is not None]
        if not items:
            return 0
        for track in items:
            if self.tracks.get(track.id) is None:
                self.tracks.upsert(track)
        added = self.playlists.add_tracks(playlist_id, [track.id for track in items])
        self.playlists_changed.emit()
        return added

    def remove_from_playlist(self, playlist_id: int, track_ids: Iterable[str]) -> int:
        removed = self.playlists.remove_tracks(playlist_id, list(track_ids))
        if removed:
            self.playlists_changed.emit()
        return removed

    def move_playlist_item(self, playlist_id: int, from_row: int, to_row: int) -> None:
        self.playlists.move(playlist_id, from_row, to_row)

    def playlists_containing(self, track_id: str):
        return self.playlists.containing(track_id)

    # ------------------------------------------------------------------ misc

    @staticmethod
    def _ensure_online_album(track: Track) -> None:
        """Online tracks arrive without album ids; derive one so the album and
        artist browsers can group them like local files."""
        if not track.album_id and track.album:
            track.album_id = album_key(track.album, track.album_artist or track.artist)
        if not track.album_artist and track.artist:
            track.album_artist = track.artist

    def record_play(self, track: Track, context: str = "") -> None:
        if track.kind == "online":
            self._ensure_online_album(track)
            if self.tracks.get(track.id) is None:
                self.tracks.upsert(track)
        self.tracks.record_play(track.id, context)
        self.track_updated.emit(track.id)

    # ------------------------------------------------------- 失效文件与重定位
    def missing_tracks(self, limit: int = 0) -> list[Track]:
        """Local tracks whose file is gone (moved, renamed or unplugged drive)."""
        tracks = self.tracks.list(kind="local")
        missing = [track for track in tracks if track.path and not os.path.exists(track.path)]
        return missing[:limit] if limit else missing

    def missing_count(self) -> int:
        return len(self.missing_tracks())

    def relocate_folder(self, old_root: str, new_root: str) -> tuple[int, int]:
        """Rewrite paths of tracks under ``old_root`` to the same relative path
        under ``new_root``. Returns ``(moved, still_missing)``."""
        old_root = old_root.rstrip("\\/")
        new_root = new_root.rstrip("\\/")
        moved = 0
        still = 0
        for track in self.tracks.tracks_under(old_root):
            try:
                relative = os.path.relpath(track.path, old_root)
            except ValueError:
                still += 1
                continue
            candidate = os.path.join(new_root, relative)
            if not os.path.exists(candidate):
                still += 1
                continue
            try:
                stat = os.stat(candidate)
                self.tracks.update_path(track.id, candidate, stat.st_size, stat.st_mtime)
                moved += 1
            except OSError:
                still += 1
        if moved:
            self.library_changed.emit()
        return moved, still

    def relocate_by_name(self, new_root: str, *, limit: int = 4000) -> tuple[int, int]:
        """Fallback for tracks whose old root is unknown: match by file name."""
        missing = self.missing_tracks()
        if not missing:
            return 0, 0
        wanted = {os.path.basename(track.path): track for track in missing}
        found: dict[str, str] = {}
        scanned = 0
        for root, _dirs, files in os.walk(new_root):
            for name in files:
                scanned += 1
                if name in wanted and name not in found:
                    found[name] = os.path.join(root, name)
                if scanned >= limit or len(found) == len(wanted):
                    break
            if scanned >= limit or len(found) == len(wanted):
                break
        moved = 0
        for name, path in found.items():
            track = wanted[name]
            try:
                stat = os.stat(path)
                self.tracks.update_path(track.id, path, stat.st_size, stat.st_mtime)
                moved += 1
            except OSError:
                continue
        if moved:
            self.library_changed.emit()
        return moved, len(missing) - moved

    def scan_errors(self, limit: int = 40):
        return self.meta.scan_errors(limit=limit)

    def remove_tracks(self, track_ids: Iterable[str]) -> int:
        ids = list(track_ids)
        if not ids:
            return 0
        self.tracks.delete(ids)
        self.library_changed.emit()
        self.playlists_changed.emit()
        return len(ids)

    def art_for(self, track: Track, size: int, *, dpr: float = 2.0):
        return self.covers.pixmap(track, size, dpr=dpr)

    def prefetch_cover(self, track: Track) -> None:
        self.covers.prefetch(track)

    def store_cover_bytes(self, data: bytes, ext: str = "") -> str:
        return self.covers.store.store(data, ext)

    def last_scan_text(self) -> str:
        value = self.meta.get("last_scan_at", "")
        if not value:
            return "尚未扫描"
        try:
            stamp = float(value)
        except (TypeError, ValueError):
            return "尚未扫描"
        then = time.localtime(stamp)
        return time.strftime("%Y-%m-%d %H:%M", then)

    def mark_scanned(self) -> None:
        self.meta.set("last_scan_at", str(time.time()))

    def close(self) -> None:
        self.scanner.cancel()
        try:
            self.covers.shutdown()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["LibraryQuery", "LibraryService", "FAVORITES_NAME"]
