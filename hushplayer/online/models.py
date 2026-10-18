"""Data model bridging the Node online-source runtime and the app's ``Track``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..model.track import ONLINE, Track, online_track_id

# Short labels used in badges.  Sources advertise a ``platform`` field, but the
# registry is user editable, so anything unknown falls back to the source name.
_PLATFORM_LABELS = {
    "wy": "网易云",
    "netease": "网易云",
    "qq": "QQ音乐",
    "kg": "酷狗",
    "kugou": "酷狗",
    "kw": "酷我",
    "kuwo": "酷我",
    "qishui": "汽水",
    "migu": "咪咕",
    "xiami": "虾米",
}


def platform_label(platform: str, fallback: str = "") -> str:
    key = (platform or "").strip().lower()
    return _PLATFORM_LABELS.get(key, fallback or (platform or "在线"))


@dataclass(slots=True)
class SourceInfo:
    """One online source as reported by ``listSources``."""

    id: str
    name: str
    platform: str = ""
    enabled: bool = True
    user_installed: bool = False
    content_policy: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    file_exists: bool = True
    scan_error: str = ""
    loaded: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------- factories
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceInfo":
        caps = data.get("capabilities") or {}
        if not isinstance(caps, Mapping):
            caps = {}
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or data.get("platform") or data.get("id") or ""),
            platform=str(data.get("platform") or ""),
            enabled=bool(data.get("enabled", True)),
            user_installed=bool(data.get("userInstalled", False)),
            content_policy=str(data.get("contentPolicy") or ""),
            version=str(data.get("version") or ""),
            description=str(data.get("description") or ""),
            author=str(data.get("author") or ""),
            file_exists=bool(data.get("fileExists", True)),
            scan_error=str(data.get("scanError") or ""),
            loaded=bool(data.get("loaded", False)),
            capabilities=dict(caps),
            raw=dict(data),
        )

    # ------------------------------------------------------------ properties
    @property
    def label(self) -> str:
        return platform_label(self.platform, self.name)

    @property
    def searchable(self) -> bool:
        return self.enabled and self.file_exists and bool(self.capabilities.get("search", True))

    @property
    def can_play(self) -> bool:
        return self.enabled and self.file_exists and bool(self.capabilities.get("playback"))

    @property
    def can_download(self) -> bool:
        return self.enabled and self.file_exists and bool(self.capabilities.get("download"))

    @property
    def can_lyrics(self) -> bool:
        return self.enabled and self.file_exists and bool(self.capabilities.get("lyrics"))

    @property
    def problem(self) -> str:
        """Human readable reason why the source is unusable, or empty."""
        if not self.file_exists:
            return self.scan_error or "音源文件缺失"
        if not self.enabled:
            return "已停用"
        if not self.can_play:
            return "不支持播放解析"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "label": self.label,
            "enabled": self.enabled,
            "fileExists": self.file_exists,
            "scanError": self.scan_error,
            "capabilities": dict(self.capabilities),
            "problem": self.problem,
        }


def build_sources(raw_sources: Iterable[Mapping[str, Any]]) -> list[SourceInfo]:
    items: list[SourceInfo] = []
    for entry in raw_sources or ():
        if isinstance(entry, Mapping):
            info = SourceInfo.from_dict(entry)
            if info.id:
                items.append(info)
    return items


# ------------------------------------------------------------------ tracks
def _as_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def track_from_item(
    item: Mapping[str, Any],
    *,
    source: SourceInfo | None = None,
) -> Track:
    """Convert one runtime search result into a :class:`Track`."""
    source_id = str(item.get("sourceId") or (source.id if source else "") or "")
    remote_id = str(item.get("id") or item.get("songmid") or "")
    title = str(item.get("title") or "").strip() or "未知歌曲"
    artist = str(item.get("artist") or "").strip() or "未知艺术家"
    album = str(item.get("album") or "").strip()
    duration = _as_int(item.get("duration"))
    if duration and duration < 1000:  # some sources report seconds
        duration *= 1000
    artwork = str(item.get("artwork") or "").strip()
    source_name = str(item.get("sourceName") or (source.name if source else "") or "")
    caps = item.get("capabilities") or {}
    if not isinstance(caps, Mapping):
        caps = {}

    track = Track(
        id=online_track_id(source_id, remote_id or title),
        kind=ONLINE,
        title=title,
        artist=artist,
        album=album,
        album_artist=artist,
        duration_ms=duration,
        source_id=source_id,
        source_name=source_name,
        remote_id=remote_id,
        artwork_url=artwork,
        available=bool(caps.get("playback", True)),
        raw=dict(item),
    )
    if source is not None:
        track.raw.setdefault("sourceName", source.name)
        track.raw.setdefault("sourceId", source.id)
        if not track.source_name:
            track.source_name = source.name
    return track


def tracks_from_items(
    items: Iterable[Mapping[str, Any]],
    *,
    source: SourceInfo | None = None,
) -> list[Track]:
    tracks: list[Track] = []
    seen: set[str] = set()
    for item in items or ():
        if not isinstance(item, Mapping):
            continue
        track = track_from_item(item, source=source)
        if not track.remote_id and not track.title:
            continue
        if track.id in seen:
            continue
        seen.add(track.id)
        tracks.append(track)
    return tracks


def runtime_track(track: Track) -> dict[str, Any]:
    """Build the payload the runtime needs to resolve a stream for ``track``."""
    payload: dict[str, Any] = {}
    raw = track.raw if isinstance(track.raw, dict) else {}
    item = raw.get("raw")
    if isinstance(item, Mapping):
        payload = dict(item)
    else:
        payload = dict(raw)
    payload.pop("capabilities", None)
    if track.remote_id and not payload.get("id"):
        payload["id"] = track.remote_id
    if track.title and not payload.get("title"):
        payload["title"] = track.title
    if track.artist and not payload.get("artist"):
        payload["artist"] = track.artist
    if track.album and not payload.get("album"):
        payload["album"] = track.album
    if track.artwork_url and not payload.get("artwork"):
        payload["artwork"] = track.artwork_url
    if track.duration_ms and not payload.get("duration"):
        payload["duration"] = track.duration_ms
    return payload


def source_of(track: Track, sources: Iterable[SourceInfo]) -> SourceInfo | None:
    if not track.source_id:
        return None
    for source in sources:
        if source.id == track.source_id:
            return source
    return None


__all__ = [
    "SourceInfo",
    "build_sources",
    "platform_label",
    "runtime_track",
    "source_of",
    "track_from_item",
    "tracks_from_items",
]
