from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.services.playlist_membership import PlaylistMembership


@dataclass(frozen=True, slots=True)
class LibraryRecords:
    """The local-library portion of a read-only repository refresh."""

    tracks: tuple[dict[str, Any], ...]
    status: str
    error: str
    song_list_is_local_only: bool


@dataclass(frozen=True, slots=True)
class PlaylistRecords:
    """The playlist portion of a read-only repository refresh."""

    playlists: dict[str, dict[str, Any]]
    load_error: str
    migration_pending: bool


@dataclass(frozen=True, slots=True)
class LibrarySnapshot:
    """One coherent, in-memory view of HushPlayer's persisted library data.

    The contained dictionaries are freshly parsed for each read.  Consumers own
    those in-memory values and may keep using the existing write flows; this
    repository itself never creates, changes, or saves a user data file.
    """

    library: LibraryRecords
    playlists: PlaylistRecords
    song_stats: dict[str, dict[str, int]]


class LibraryRepository:
    """Read the existing local-library documents without modifying storage.

    This is the shared business-layer source for the legacy window and a future
    UI V2 adapter.  It intentionally contains no Qt widgets, no scanning, and
    no write operation.
    """

    def __init__(
        self,
        library_file: Path,
        playlists_file: Path,
        stats_file: Path,
    ) -> None:
        self.library_file = Path(library_file)
        self.playlists_file = Path(playlists_file)
        self.stats_file = Path(stats_file)

    def load_snapshot(self) -> LibrarySnapshot:
        """Read all persisted library documents once into an isolated snapshot."""

        normalize_path = self._cached_normalizer()
        local_path_state = self._cached_local_path_state(normalize_path)

        return LibrarySnapshot(
            library=self.load_library_records(normalize_path, local_path_state),
            playlists=self.load_playlist_records(normalize_path),
            song_stats=self.load_song_stats(normalize_path),
        )

    def load_library_records(
        self,
        normalize_path: Callable[[str | None], str] | None = None,
        local_path_state: Callable[[str], tuple[bool, str]] | None = None,
    ) -> LibraryRecords:
        """Apply the legacy library read and local-file availability rules."""

        normalize_path = normalize_path or self.normalize_song_path
        if local_path_state is None:
            def local_path_state(path: str) -> tuple[bool, str]:
                exists = Path(path).exists()
                return exists, normalize_path(path) if exists else ""

        if not self.library_file.exists():
            return LibraryRecords((), "missing", "", True)

        try:
            with self.library_file.open("r", encoding="utf-8") as file:
                songs = json.load(file)
        except Exception as error:
            return LibraryRecords((), "error", str(error), True)

        if not songs:
            return LibraryRecords((), "empty", "", True)

        tracks: list[dict[str, Any]] = []
        song_list_is_local_only = True
        try:
            iterator = iter(songs)
        except TypeError as error:
            return LibraryRecords((), "error", str(error), True)

        try:
            for song in iterator:
                if not isinstance(song, dict):
                    raise TypeError("音乐库条目不是对象")

                path = song.get("path", "")
                if not path:
                    continue
                path_exists, normalized_path = local_path_state(path)
                if not path_exists:
                    continue

                song_data = dict(song)
                song_data.update(
                    {
                        "title": song.get("title", "未知歌曲"),
                        "artist": song.get("artist", "未知艺术家"),
                        "album": song.get("album", "未知专辑"),
                        "path": normalized_path,
                        "added_at": int(song.get("added_at", 0) or 0),
                        "demo": False,
                    }
                )
                if song_data.get("recordKind") == "remote":
                    song_list_is_local_only = False
                tracks.append(song_data)
        except Exception as error:
            return LibraryRecords((), "error", str(error), True)

        return LibraryRecords(
            tuple(tracks),
            "loaded",
            "",
            song_list_is_local_only,
        )

    def load_playlist_records(
        self,
        normalize_path: Callable[[str | None], str] | None = None,
    ) -> PlaylistRecords:
        """Read and normalize playlist membership only in the returned copy."""

        normalize_path = normalize_path or self.normalize_song_path

        default_playlists = self.default_playlists()
        if not self.playlists_file.exists():
            return PlaylistRecords(default_playlists, "", False)

        try:
            with self.playlists_file.open("r", encoding="utf-8") as file:
                playlists = json.load(file)
            if not isinstance(playlists, dict):
                raise ValueError("歌单文件根节点不是对象")

            if "liked" not in playlists or not isinstance(playlists["liked"], dict):
                playlists["liked"] = self.default_playlists()["liked"]

            liked = playlists["liked"]
            liked.setdefault("name", "我喜欢")
            liked.setdefault("songs", [])
            liked.setdefault("remoteSongs", [])
            liked["fixed"] = True
            if not isinstance(liked["songs"], list):
                liked["songs"] = []

            for playlist in playlists.values():
                if not isinstance(playlist, dict):
                    continue
                playlist.setdefault("remoteSongs", [])
                if not isinstance(playlist["remoteSongs"], list):
                    playlist["remoteSongs"] = []

            try:
                anchor_ms = int(self.playlists_file.stat().st_mtime * 1000)
            except OSError:
                anchor_ms = int(time.time() * 1000)
            migration_pending = PlaylistMembership.normalize_document(
                playlists,
                normalize_path,
                anchor_ms=anchor_ms,
            )
            return PlaylistRecords(playlists, "", migration_pending)
        except Exception as error:
            return PlaylistRecords(
                default_playlists,
                f"读取歌单失败，已禁止覆盖原文件：{error}",
                False,
            )

    def load_song_stats(
        self,
        normalize_path: Callable[[str | None], str] | None = None,
    ) -> dict[str, dict[str, int]]:
        """Return legacy statistics in their existing normalized in-memory form."""

        normalize_path = normalize_path or self.normalize_song_path

        if not self.stats_file.exists():
            return {}

        try:
            with self.stats_file.open("r", encoding="utf-8") as file:
                raw_stats = json.load(file)
            if not isinstance(raw_stats, dict):
                return {}

            cleaned_stats: dict[str, dict[str, int]] = {}
            for path, stats in raw_stats.items():
                if not isinstance(stats, dict):
                    continue
                normalized_path = normalize_path(path)
                if not normalized_path:
                    continue
                cleaned_stats[normalized_path] = {
                    "play_count": max(0, int(stats.get("play_count", 0))),
                    "total_listen_time": max(
                        0,
                        int(stats.get("total_listen_time", 0)),
                    ),
                    "last_played": max(0, int(stats.get("last_played", 0))),
                }
            return cleaned_stats
        except Exception:
            return {}

    @staticmethod
    def default_playlists() -> dict[str, dict[str, Any]]:
        return {
            "liked": {
                "name": "我喜欢",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": True,
            }
        }

    @staticmethod
    def normalize_song_path(path: str | None) -> str:
        if not path:
            return ""
        try:
            return str(Path(path).resolve())
        except Exception:
            return str(path)

    def _cached_normalizer(self) -> Callable[[str | None], str]:
        cache: dict[str, str] = {}

        def normalize_once(path: str | None) -> str:
            cache_key = str(path or "")
            if cache_key not in cache:
                cache[cache_key] = self.normalize_song_path(path)
            return cache[cache_key]

        return normalize_once

    @staticmethod
    def _cached_local_path_state(
        normalize_path: Callable[[str | None], str],
    ) -> Callable[[str], tuple[bool, str]]:
        cache: dict[str, tuple[bool, str]] = {}

        def resolve_once(path: str) -> tuple[bool, str]:
            cache_key = str(path or "")
            if cache_key not in cache:
                exists = Path(path).exists()
                cache[cache_key] = (
                    exists,
                    normalize_path(path) if exists else "",
                )
            return cache[cache_key]

        return resolve_once
