"""Aggregated artist data derived from the shared mock track collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.ui_v2.models.album import Album
from app.ui_v2.models.track import Track


@dataclass(frozen=True, slots=True)
class Artist:
    id: str
    name: str
    track_ids: tuple[str, ...]
    album_ids: tuple[str, ...]
    total_duration_ms: int
    metadata: Mapping[str, str] = field(
        default_factory=dict,
        compare=False,
        hash=False,
        repr=False,
    )


@dataclass(frozen=True, slots=True)
class ArtistAggregate:
    """One consistent, view-local snapshot for an Artist detail surface.

    The aggregate deliberately owns the filtered tracks, resolved albums, and
    derived counts used by every child of the page.  This prevents the Hero
    from showing adapter-level statistics after the content has been filtered
    or becomes unavailable.
    """

    artist: Artist | None
    tracks: tuple[Track, ...]
    albums: tuple[Album, ...]
    track_count: int
    album_count: int
    total_duration_ms: int
    metadata: Mapping[str, str] = field(default_factory=dict)
    exists: bool = False
