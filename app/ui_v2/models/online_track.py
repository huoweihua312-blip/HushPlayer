"""A deterministic online-result value with no network or playback URL data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.ui_v2.models.track import Track


@dataclass(frozen=True, slots=True)
class OnlineTrack:
    id: str
    source_id: str
    source_name: str
    title: str
    artist: str
    album: str
    duration_ms: int | None
    artwork_key: str
    quality: str
    stable_identity: str
    is_favorite: bool
    is_downloaded: bool
    is_cached: bool
    availability: str
    explicit: bool
    result_rank: int
    artwork_url: str = ""
    remote_id: str = ""
    raw: dict = field(default_factory=dict)
    artwork_data: bytes = b""

    @property
    def is_online(self) -> bool:
        return True

    def as_track(self) -> Track:
        return Track(
            id=self.id,
            title=self.title,
            artist=self.artist,
            album=self.album,
            duration_ms=self.duration_ms,
            source_id=self.source_id,
            source_name=self.source_name,
            source_type="online",
            added_at=datetime(2026, 3, 1, 9, 0),
            is_favorite=self.is_favorite,
            is_missing=self.availability != "available",
            is_loading=False,
            artwork_path=None,
            stable_identity=self.stable_identity,
        )
