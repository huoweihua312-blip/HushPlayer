"""UI-facing track value object, independent from legacy library rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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

    @property
    def stable_id(self) -> str:
        """The repository-backed stable identity exposed to V2 consumers."""

        return self.stable_identity or self.id

    @property
    def is_online(self) -> bool:
        return self.source_type == "online"


def format_duration(duration_ms: int | None) -> str:
    """Render a known duration as H:MM:SS or M:SS without a locale dependency."""
    if duration_ms is None or duration_ms < 0:
        return "--:--"
    total_seconds = duration_ms // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
