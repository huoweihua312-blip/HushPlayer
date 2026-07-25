"""In-memory metadata for one recently played mock track."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecentPlay:
    track_id: str
    last_played_at: datetime
    play_count: int
    last_position_ms: int
