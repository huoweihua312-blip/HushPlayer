from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any


def _first_text(mapping: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _safe_duration(value: Any) -> int:
    try:
        duration = float(value or 0)
    except (TypeError, ValueError):
        return 0
    # Most source plug-ins use seconds. Values above one day are normally ms.
    if duration > 86400:
        duration /= 1000
    return max(0, int(round(duration)))


@dataclass(slots=True)
class MediaItem:
    """Canonical track data used by new library, search and detail UI.

    Provider-specific fields are kept only in ``extra['provider_data']`` so UI
    widgets never need to know names such as ``songmid`` or ``rid``.
    """

    track_id: str
    source_id: str = "local"
    source_name: str = "本地音乐"
    media_type: str = "local"
    title: str = "未知歌曲"
    artist: str = "未知艺术家"
    album: str = "未知专辑"
    duration: int = 0
    cover_url: str = ""
    local_cover_path: str = ""
    play_url: str = ""
    local_file_path: str = ""
    lyrics: str = ""
    lyrics_url: str = ""
    quality: str = ""
    format: str = ""
    can_play: bool = False
    can_download: bool = False
    availability: str = "available"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_local(cls, song: dict) -> "MediaItem":
        path_text = _first_text(song, "local_file_path", "path")
        resolved_path = ""
        if path_text:
            try:
                resolved_path = str(Path(path_text).resolve())
            except (OSError, RuntimeError):
                resolved_path = path_text
        identity = resolved_path.casefold() or "\0".join(
            _first_text(song, key).casefold()
            for key in ("title", "artist", "album")
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        suffix = Path(resolved_path).suffix.lstrip(".").lower() if resolved_path else ""
        extra = {
            key: value
            for key, value in song.items()
            if key not in {
                "track_id", "source_id", "source_name", "media_type", "title",
                "artist", "album", "duration", "cover_url", "local_cover_path",
                "play_url", "local_file_path", "path", "lyrics", "lyrics_url",
                "quality", "format", "can_play", "can_download", "availability",
                "extra",
            }
        }
        inherited_extra = song.get("extra")
        if isinstance(inherited_extra, dict):
            extra.update(inherited_extra)
        return cls(
            track_id=_first_text(song, "track_id", default=f"local_{digest}"),
            title=_first_text(song, "title", default="未知歌曲"),
            artist=_first_text(song, "artist", default="未知艺术家"),
            album=_first_text(song, "album", default="未知专辑"),
            duration=_safe_duration(song.get("duration")),
            local_cover_path=_first_text(song, "local_cover_path", "cover_path"),
            local_file_path=resolved_path,
            lyrics=_first_text(song, "lyrics"),
            format=_first_text(song, "format", default=suffix),
            can_play=bool(resolved_path),
            availability="available" if resolved_path else "missing",
            extra=extra,
        )

    @classmethod
    def from_online(cls, track: dict) -> "MediaItem":
        source_id = _first_text(track, "source_id", "sourceId")
        source_name = _first_text(
            track, "source_name", "sourceName", default=source_id or "未知来源"
        )
        remote_id = _first_text(
            track,
            "track_id",
            "remote_id",
            "id",
            "songmid",
            "rid",
        )
        if not remote_id:
            identity = "\0".join(
                [
                    source_id,
                    _first_text(track, "title").casefold(),
                    _first_text(track, "artist").casefold(),
                    _first_text(track, "album").casefold(),
                    str(_safe_duration(track.get("duration"))),
                ]
            )
            remote_id = "meta_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        capabilities = track.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        local_path = _first_text(track, "local_file_path", "localPath")
        inherited_extra = track.get("extra")
        inherited_extra = inherited_extra if isinstance(inherited_extra, dict) else {}
        provider_data = track.get("provider_data") or inherited_extra.get("provider_data")
        if not isinstance(provider_data, dict):
            raw = track.get("raw")
            provider_data = dict(raw) if isinstance(raw, dict) else dict(track)
        extra = dict(inherited_extra)
        extra["provider_data"] = provider_data
        stable_id = _first_text(track, "remoteStableId")
        if stable_id:
            extra["remote_stable_id"] = stable_id
        raw_mapping = track.get("raw")
        raw_mapping = raw_mapping if isinstance(raw_mapping, dict) else {}
        lyrics_text = _first_text(
            track, "lyrics", "lyric", "lrc", "rawLrc", "syncedLyrics", "plainLyrics"
        ) or _first_text(
            raw_mapping,
            "lyrics",
            "lyric",
            "lrc",
            "rawLrc",
            "syncedLyrics",
            "plainLyrics",
        )
        cover_url = _first_text(track, "cover_url", "artwork", "pic", "cover") or _first_text(
            raw_mapping, "cover_url", "artwork", "pic", "cover"
        )
        return cls(
            track_id=remote_id,
            source_id=source_id,
            source_name=source_name,
            media_type="online",
            title=_first_text(track, "title", "name", default="未知歌曲"),
            artist=_first_text(track, "artist", "singer", default="未知艺术家"),
            album=_first_text(track, "album", "albumName", default="未知专辑"),
            duration=_safe_duration(track.get("duration")),
            cover_url=cover_url,
            local_cover_path=_first_text(track, "local_cover_path"),
            play_url=_first_text(track, "play_url"),
            local_file_path=local_path,
            lyrics=lyrics_text,
            lyrics_url=_first_text(track, "lyrics_url", "lyricUrl"),
            quality=_first_text(track, "quality", "bitrate"),
            format=_first_text(track, "format", "type", "ext"),
            can_play=bool(local_path or capabilities.get("playback") or track.get("can_play")),
            can_download=bool(capabilities.get("download") or track.get("can_download")),
            availability=_first_text(track, "availability", default="available"),
            extra=extra,
        )

    @classmethod
    def from_mapping(cls, value: "MediaItem | dict") -> "MediaItem":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("MediaItem 只能由字典或 MediaItem 创建")
        media_type = _first_text(value, "media_type", "resultKind", default="local")
        source_id = _first_text(value, "sourceId", "source_id")
        if media_type in {"online", "remote"} or (source_id and source_id != "local"):
            return cls.from_online(value)
        return cls.from_local(value)

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.track_id}" if self.media_type == "online" else self.track_id

    @property
    def is_local_available(self) -> bool:
        return bool(self.local_file_path and Path(self.local_file_path).is_file())

    def with_resolution(self, resolution: dict) -> "MediaItem":
        return replace(
            self,
            play_url=_first_text(resolution, "url", "play_url", default=self.play_url),
            lyrics=_first_text(
                resolution,
                "lyrics",
                "lyric",
                "lrc",
                "rawLrc",
                "syncedLyrics",
                "plainLyrics",
                default=self.lyrics,
            ),
            cover_url=_first_text(
                resolution, "cover_url", "artwork", "pic", "cover", default=self.cover_url
            ),
            quality=_first_text(resolution, "quality", "bitrate", default=self.quality),
            format=_first_text(
                resolution, "format", "mimeType", "type", "ext", default=self.format
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def to_provider_payload(self) -> dict:
        provider_data = self.extra.get("provider_data")
        payload = dict(provider_data) if isinstance(provider_data, dict) else {}
        payload.setdefault("id", self.track_id)
        payload.setdefault("title", self.title)
        payload.setdefault("artist", self.artist)
        payload.setdefault("album", self.album)
        payload.setdefault("duration", self.duration)
        return payload

    def to_legacy_local(self) -> dict:
        result = dict(self.extra)
        result.update(
            {
                "title": self.title,
                "artist": self.artist,
                "album": self.album,
                "duration": self.duration,
                "path": self.local_file_path,
                "demo": False,
            }
        )
        return result

    def to_legacy_online(self) -> dict:
        payload = self.to_provider_payload()
        provider_data = self.extra.get("provider_data")
        if isinstance(provider_data, dict):
            payload["raw"] = dict(provider_data)
        payload.update(
            {
                "sourceId": self.source_id,
                "sourceName": self.source_name,
                "title": self.title,
                "artist": self.artist,
                "album": self.album,
                "duration": self.duration,
                "artwork": self.cover_url,
                "availability": self.availability,
                "capabilities": {
                    "playback": self.can_play,
                    "download": self.can_download,
                },
            }
        )
        stable_id = str(self.extra.get("remote_stable_id") or "")
        if stable_id:
            payload["remoteStableId"] = stable_id
        return payload
