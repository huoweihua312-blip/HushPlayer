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


def _metadata_candidates(value: dict) -> list[dict]:
    """Return provider metadata mappings from most to least specific."""

    if not isinstance(value, dict):
        return []
    candidates: list[dict] = []
    metadata = value.get("metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
        candidates.append(metadata)
    item = value.get("item")
    if isinstance(item, dict):
        candidates.append(item)
    nested = value.get("data")
    if isinstance(nested, dict):
        candidates.append(nested)
    candidates.append(value)
    return candidates


def _metadata_text(
    candidates: list[dict],
    keys: tuple[str, ...],
    current: str,
    placeholders: set[str] | None = None,
) -> str:
    placeholders = placeholders or set()
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, (list, tuple)):
                parts = []
                for item in value:
                    if isinstance(item, dict):
                        item = item.get("name") or item.get("title") or item.get("value")
                    if item is not None and str(item).strip():
                        parts.append(str(item).strip())
                text = " / ".join(parts)
            elif isinstance(value, dict):
                nested = value.get("name") or value.get("title") or value.get("value")
                text = str(nested or "").strip()
            else:
                text = str(value or "").strip()
            if text and text not in placeholders:
                return text
    return current


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
    def stable_identity(self) -> str:
        if self.media_type == "online":
            return f"remote:{self.source_id.casefold()}:{self.track_id}"
        if self.local_file_path:
            return f"local:{self.local_file_path.casefold()}"
        return f"local-id:{self.track_id}"

    @property
    def is_local_available(self) -> bool:
        return bool(self.local_file_path and Path(self.local_file_path).is_file())

    def with_resolution(self, resolution: dict) -> "MediaItem":
        enriched = self.with_metadata(resolution)
        return replace(
            enriched,
            play_url=_first_text(resolution, "url", "play_url", default=enriched.play_url),
            lyrics=_first_text(
                resolution,
                "lyrics",
                "lyric",
                "lrc",
                "rawLrc",
                "syncedLyrics",
                "plainLyrics",
                default=enriched.lyrics,
            ),
            cover_url=_first_text(
                resolution,
                "cover_url",
                "artwork",
                "pic",
                "cover",
                default=enriched.cover_url,
            ),
            quality=_first_text(resolution, "quality", "bitrate", default=enriched.quality),
            format=_first_text(
                resolution,
                "format",
                "mimeType",
                "type",
                "ext",
                default=enriched.format,
            ),
        )

    def with_metadata(self, result: dict) -> "MediaItem":
        """Merge richer provider metadata without changing the stable identity."""

        candidates = _metadata_candidates(result)
        if not candidates:
            return self
        duration = self.duration
        for candidate in candidates:
            candidate_duration = _safe_duration(
                candidate.get("duration")
                or candidate.get("interval")
                or candidate.get("time")
            )
            if candidate_duration:
                duration = candidate_duration
                break
        provider_data = self.extra.get("provider_data")
        merged_provider_data = (
            dict(provider_data) if isinstance(provider_data, dict) else {}
        )
        for candidate in reversed(candidates):
            raw = candidate.get("raw")
            if isinstance(raw, dict):
                merged_provider_data.update(raw)
            merged_provider_data.update(
                {
                    key: value
                    for key, value in candidate.items()
                    if key not in {"item", "metadata", "data", "raw"}
                    and value is not None
                }
            )
        extra = dict(self.extra)
        extra["provider_data"] = merged_provider_data
        return replace(
            self,
            title=_metadata_text(
                candidates,
                ("title", "name"),
                self.title,
                {"未知歌曲"},
            ),
            artist=_metadata_text(
                candidates,
                ("artist", "artists", "singer"),
                self.artist,
                {"未知艺术家"},
            ),
            album=_metadata_text(
                candidates,
                ("album", "albumName"),
                self.album,
                {"未知专辑"},
            ),
            duration=duration,
            cover_url=_metadata_text(
                candidates,
                ("cover_url", "artwork", "coverImg", "picUrl", "pic", "cover"),
                self.cover_url,
            ),
            lyrics=_metadata_text(
                candidates,
                ("lyrics", "lyric", "lrc", "rawLrc", "syncedLyrics", "plainLyrics"),
                self.lyrics,
            ),
            lyrics_url=_metadata_text(
                candidates,
                ("lyrics_url", "lyricUrl"),
                self.lyrics_url,
            ),
            quality=_metadata_text(
                candidates,
                ("quality", "bitrate"),
                self.quality,
            ),
            format=_metadata_text(
                candidates,
                ("format", "type", "ext"),
                self.format,
            ),
            extra=extra,
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
