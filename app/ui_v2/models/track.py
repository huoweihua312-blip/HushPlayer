"""UI-facing track value object, independent from legacy library rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


_ARTWORK_URL_KEYS = (
    "artwork_url",
    "artworkUrl",
    "cover_url",
    "coverUrl",
    "artwork",
    "cover",
    "picUrl",
    "pic_url",
    "pic",
    "imageUrl",
    "image_url",
    "image",
)

_RECOVERABLE_AVAILABILITY_STATES = frozenset(
    {
        "unavailable",
        "source_unavailable",
        "resolve_failed",
        "permission_denied",
        "playback_error",
    }
)


def artwork_url_from_payload(payload: dict | None) -> str:
    """Extract a real artwork URL without treating provider keys as images."""

    if not isinstance(payload, dict):
        return ""
    candidates: list[dict] = [payload]
    for key in ("metadata", "data", "item", "raw", "provider_data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
            if isinstance(nested.get("data"), dict):
                candidates.append(nested["data"])
    for candidate in candidates:
        for key in _ARTWORK_URL_KEYS:
            value = candidate.get(key)
            if isinstance(value, dict):
                value = value.get("url") or value.get("src") or value.get("href")
            text = str(value or "").strip()
            if text.startswith(("http://", "https://", "file://", "data:image/")):
                return text
    return ""


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    title: str
    artist: str
    album: str
    duration_ms: int | None
    source_id: str
    source_name: str
    source_type: str
    added_at: datetime
    is_favorite: bool
    is_missing: bool
    is_loading: bool
    artwork_path: str | None
    stable_identity: str
    favorite_added_at: datetime | None = None
    play_count: int = 0
    last_played_at: datetime | None = None
    artwork_key: str = ""
    availability: str = "available"
    local_path: str = ""
    remote_identity: str = ""
    remote_track_id: str = ""
    remote_payload: dict = field(default_factory=dict)
    availability_detail: str = ""
    artwork_url: str = ""
    artwork_data: bytes = b""

    @property
    def stable_id(self) -> str:
        """The repository-backed stable identity exposed to V2 consumers."""

        return self.stable_identity or self.id

    @property
    def is_online(self) -> bool:
        return self.source_type == "online"

    @property
    def needs_online_recovery(self) -> bool:
        """Whether a failed track can be rematched against enabled sources."""

        if self.is_missing:
            return True
        state = str(self.availability or "").strip().casefold().replace("-", "_")
        return state in _RECOVERABLE_AVAILABILITY_STATES


def format_duration(duration_ms: int | None) -> str:
    """Render a known duration as H:MM:SS or M:SS without a locale dependency."""
    if duration_ms is None or duration_ms < 0:
        return "--:--"
    total_seconds = duration_ms // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
