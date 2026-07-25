"""Aggregated artist data derived from the shared mock track collection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Artist:
    id: str
    name: str
    track_ids: tuple[str, ...]
    album_ids: tuple[str, ...]
    total_duration_ms: int
