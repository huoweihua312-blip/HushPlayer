from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.media_item import MediaItem


_TRANSIENT_REMOTE_KEYS = {
    "url",
    "playurl",
    "playbackurl",
    "downloadurl",
    "mediaurl",
    "streamurl",
    "audiourl",
    "sourceurl",
}


def _safe_remote_value(value: Any) -> Any:
    """Remove expiring media URLs before a queue item is persisted."""

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").casefold()
            if normalized in _TRANSIENT_REMOTE_KEYS:
                continue
            result[str(key)] = _safe_remote_value(item)
        return result
    if isinstance(value, list):
        return [_safe_remote_value(item) for item in value[:200]]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class PlaybackQueueItem:
    """One stable local or remote entry in a mixed playback queue."""

    media_item: MediaItem

    @classmethod
    def from_value(cls, value: "PlaybackQueueItem | MediaItem | dict | str") -> "PlaybackQueueItem":
        if isinstance(value, cls):
            return value
        if isinstance(value, MediaItem):
            return cls(value)
        if isinstance(value, str):
            return cls(MediaItem.from_local({"path": value}))
        if not isinstance(value, dict):
            raise TypeError("播放队列项必须来自路径、字典或 MediaItem")

        nested = value.get("media_item") or value.get("media") or value.get("track")
        if isinstance(nested, dict):
            return cls(MediaItem.from_mapping(nested))
        if value.get("kind") == "local" and value.get("path"):
            return cls(MediaItem.from_local(value))
        return cls(MediaItem.from_mapping(value))

    @property
    def kind(self) -> str:
        return "remote" if self.media_item.media_type == "online" else "local"

    @property
    def stable_identity(self) -> str:
        return self.media_item.stable_identity

    @property
    def local_path(self) -> str:
        return self.media_item.local_file_path

    @property
    def source_id(self) -> str:
        return self.media_item.source_id if self.kind == "remote" else ""

    @property
    def remote_track_id(self) -> str:
        return self.media_item.track_id if self.kind == "remote" else ""

    @property
    def remote_stable_id(self) -> str:
        if self.kind != "remote":
            return ""
        return str(self.media_item.extra.get("remote_stable_id") or "")

    def to_mapping(self) -> dict:
        return {
            "kind": self.kind,
            "stable_identity": self.stable_identity,
            "media_item": self.media_item.to_dict(),
        }

    def to_storage_value(self) -> str | dict:
        """Keep old local path entries readable while adding safe remote entries."""

        if self.kind == "local":
            return self.local_path
        return {
            "kind": "remote",
            "stable_identity": self.stable_identity,
            "media_item": _safe_remote_value(self.media_item.to_dict()),
        }
