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
    availability_detail: str = ""

    @property
    def is_online(self) -> bool:
        return True

    def as_track(self) -> Track:
        confirmed_error = {
            "unavailable",
            "source_unavailable",
            "source-unavailable",
            "resolve_failed",
            "resolve-failed",
            "permission_denied",
            "permission-denied",
            "playback_error",
            "playback-error",
        }
        remote_payload = dict(self.raw)
        if self.artwork_url:
            remote_payload.setdefault("artwork", self.artwork_url)
            remote_payload.setdefault("artworkUrl", self.artwork_url)
            remote_payload.setdefault("artwork_url", self.artwork_url)
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
            # Unresolved remote tracks are still valid rows.  Only a confirmed
            # runtime failure should enter the disabled/error presentation.
            is_missing=self.availability in confirmed_error,
            is_loading=False,
            artwork_path=None,
            stable_identity=self.stable_identity,
            availability=self.availability,
            remote_identity=self.stable_identity,
            remote_track_id=self.remote_id,
            remote_payload=remote_payload,
            availability_detail=self.availability_detail,
            artwork_key=self.artwork_key,
            artwork_url=self.artwork_url,
            artwork_data=bytes(self.artwork_data),
        )
