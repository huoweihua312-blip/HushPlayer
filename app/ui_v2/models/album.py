"""Aggregated album data with artist-qualified identity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Album:
    id: str
    title: str
    artist: str
    track_ids: tuple[str, ...]
    total_duration_ms: int
