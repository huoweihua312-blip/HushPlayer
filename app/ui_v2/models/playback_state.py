"""Mock playback state used exclusively by the UI V2 shell."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.ui_v2.models.track import Track


class RepeatMode(str, Enum):
    OFF = "off"
    ALL = "all"
    ONE = "one"


@dataclass(frozen=True, slots=True)
class PlaybackState:
    current_track: Track | None = None
    current_index: int = -1
    is_playing: bool = False
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 70
    is_muted: bool = False
    is_favorite: bool = False
    shuffle_enabled: bool = False
    repeat_mode: RepeatMode = RepeatMode.ALL
    status: str = "idle"
    status_detail: str = ""
