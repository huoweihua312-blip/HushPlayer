"""Mock online-source capabilities and visible health state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OnlineSource:
    id: str
    name: str
    enabled: bool
    status: str
    latency_ms: int
    result_count: int
    last_error: str
    supports_playback: bool
    supports_download: bool
    supports_lyrics: bool
    source_type: str
