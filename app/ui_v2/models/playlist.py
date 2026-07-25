"""Mock playlist values that retain member IDs rather than duplicating tracks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PlaylistEntry:
    track_id: str
    added_at: datetime


@dataclass(frozen=True, slots=True)
class Playlist:
    id: str
    name: str
    created_at: datetime
    description: str = ""
    entries: tuple[PlaylistEntry, ...] = ()

    @property
    def track_ids(self) -> tuple[str, ...]:
        return tuple(entry.track_id for entry in self.entries)
