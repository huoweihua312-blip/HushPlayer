"""统一的曲目模型（本地与在线共用）。

在线曲目与本地曲目在数据结构上完全一致，通过 ``kind`` / ``source_id`` 区分，
这样播放队列、收藏、歌单、搜索都可以用同一条代码路径处理。
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

LOCAL = "local"
ONLINE = "online"


def _hash(*parts: str) -> str:
    digest = hashlib.sha1()
    for part in parts:
        digest.update(str(part).encode("utf-8", errors="replace"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def normalize_path(path: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(path))
    except (OSError, ValueError):
        return path.casefold()


def local_track_id(path: str) -> str:
    return "local:" + _hash(normalize_path(path))[:20]


def online_track_id(source_id: str, remote_id: str) -> str:
    return f"online:{source_id}:{_hash(source_id, remote_id)[:20]}"


def album_key(name: str, album_artist: str) -> str:
    return "album:" + _hash((name or "").strip().casefold(), (album_artist or "").strip().casefold())[:20]


def artist_key(name: str) -> str:
    return "artist:" + _hash((name or "").strip().casefold())[:20]


_ARTIST_SPLIT = re.compile(r"\s*(?:/|;|、|,|&| feat\.? | ft\.? )\s*", re.IGNORECASE)


def split_artists(value: str) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in _ARTIST_SPLIT.split(value) if part and part.strip()]
    return parts or [value.strip()]


@dataclass
class Track:
    id: str
    kind: str = LOCAL
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    duration_ms: int = 0
    path: str = ""
    source_id: str = ""
    source_name: str = ""
    remote_id: str = ""
    artwork_url: str = ""
    artwork_path: str = ""
    track_no: int = 0
    disc_no: int = 0
    year: int = 0
    genre: str = ""
    bitrate: int = 0
    sample_rate: int = 0
    codec: str = ""
    size: int = 0
    added_at: float = 0.0
    modified_at: float = 0.0
    play_count: int = 0
    last_played: float = 0.0
    favorite: bool = False
    favorited_at: float = 0.0
    lyrics_offset_ms: int = 0
    album_id: str = ""
    artist_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    # 运行时字段（不持久化）
    available: bool = True

    # ------------------------------------------------------------------ 便捷属性
    @property
    def is_online(self) -> bool:
        return self.kind == ONLINE

    @property
    def is_local(self) -> bool:
        return self.kind == LOCAL

    @property
    def display_title(self) -> str:
        return self.title or (os.path.basename(self.path) if self.path else "未知歌曲")

    @property
    def display_artist(self) -> str:
        return self.artist or "未知歌手"

    @property
    def display_album(self) -> str:
        return self.album or "未知专辑"

    @property
    def duration_text(self) -> str:
        return format_duration(self.duration_ms)

    @property
    def badge(self) -> str:
        return self.source_name if self.is_online else "本地"

    @property
    def stable_key(self) -> tuple[str, str]:
        return (self.kind, self.remote_id or self.path or self.id)

    def duration_seconds(self) -> float:
        return max(0.0, self.duration_ms / 1000.0)

    # ------------------------------------------------------------------ 序列化
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Track":
        """从快照恢复曲目（与 ``to_dict`` 对称，忽略未知字段）。"""
        if not isinstance(data, dict):
            raise TypeError("Track.from_dict 需要一个字典")
        allowed = {field for field in cls.__dataclass_fields__}
        payload = {key: value for key, value in data.items() if key in allowed}
        payload.setdefault("id", "")
        payload.setdefault("title", "")
        return cls(**payload)

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "duration_ms": self.duration_ms,
            "path": self.path,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "remote_id": self.remote_id,
            "artwork_url": self.artwork_url,
            "artwork_path": self.artwork_path,
            "track_no": self.track_no,
            "disc_no": self.disc_no,
            "year": self.year,
            "genre": self.genre,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "codec": self.codec,
            "size": self.size,
            "added_at": self.added_at,
            "modified_at": self.modified_at,
            "play_count": self.play_count,
            "last_played": self.last_played,
            "favorite": self.favorite,
            "favorited_at": self.favorited_at,
            "lyrics_offset_ms": self.lyrics_offset_ms,
            "album_id": self.album_id,
            "artist_id": self.artist_id,
        }
        if include_raw:
            data["raw"] = self.raw
        return data

    @classmethod
    def from_row(cls, row: Any) -> "Track":
        keys = row.keys() if hasattr(row, "keys") else []
        def value(name: str, default: Any = None) -> Any:
            try:
                item = row[name]
            except (IndexError, KeyError):
                return default
            return default if item is None else item

        raw_text = value("raw", "{}")
        raw: dict[str, Any] = {}
        if raw_text:
            try:
                import json

                raw = json.loads(raw_text) if isinstance(raw_text, str) else dict(raw_text)
            except (ValueError, TypeError):
                raw = {}
        return cls(
            id=str(value("id", "")),
            kind=str(value("kind", LOCAL)),
            title=str(value("title", "") or ""),
            artist=str(value("artist", "") or ""),
            album=str(value("album", "") or ""),
            album_artist=str(value("album_artist", "") or ""),
            duration_ms=int(value("duration_ms", 0) or 0),
            path=str(value("path", "") or ""),
            source_id=str(value("source_id", "") or ""),
            source_name=str(value("source_name", "") or ""),
            remote_id=str(value("remote_id", "") or ""),
            artwork_url=str(value("artwork_url", "") or ""),
            artwork_path=str(value("artwork_path", "") or ""),
            track_no=int(value("track_no", 0) or 0),
            disc_no=int(value("disc_no", 0) or 0),
            year=int(value("year", 0) or 0),
            genre=str(value("genre", "") or ""),
            bitrate=int(value("bitrate", 0) or 0),
            sample_rate=int(value("sample_rate", 0) or 0),
            codec=str(value("codec", "") or ""),
            size=int(value("size", 0) or 0),
            added_at=float(value("added_at", 0) or 0),
            modified_at=float(value("modified_at", 0) or 0),
            play_count=int(value("play_count", 0) or 0),
            last_played=float(value("last_played", 0) or 0),
            favorite=bool(value("favorite", 0)),
            favorited_at=float(value("favorited_at", 0) or 0),
            lyrics_offset_ms=int(value("lyrics_offset_ms", 0) or 0),
            album_id=str(value("album_id", "") or ""),
            artist_id=str(value("artist_id", "") or ""),
            raw=raw,
        )


@dataclass
class Album:
    id: str
    name: str
    artist: str
    year: int = 0
    track_count: int = 1
    duration_ms: int = 0
    cover_track_id: str = ""
    artwork_path: str = ""
    genre: str = ""

    @property
    def display_name(self) -> str:
        return self.name or "未知专辑"


@dataclass
class Artist:
    id: str
    name: str
    track_count: int = 0
    album_count: int = 0
    cover_track_id: str = ""
    artwork_path: str = ""


@dataclass
class Playlist:
    id: int
    name: str
    description: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    track_count: int = 0
    duration_ms: int = 0
    cover_track_id: str = ""
    system: bool = False
    artwork_path: str = ""

    @property
    def is_favorites(self) -> bool:
        return self.system and self.name == "我喜欢"


def format_duration(ms: int | float) -> str:
    total = max(0, int(round(ms / 1000.0)))
    minutes, seconds = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_duration_long(ms: int | float) -> str:
    total = max(0, int(round(ms / 1000.0)))
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{max(1, minutes)} 分钟"


def dedupe_tracks(tracks: Iterable[Track]) -> list[Track]:
    seen: set[str] = set()
    result: list[Track] = []
    for track in tracks:
        key = track.id
        if key in seen:
            continue
        seen.add(key)
        result.append(track)
    return result
