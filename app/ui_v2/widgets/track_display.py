"""Presentation-only labels for deterministic mock tracks.

This module deliberately leaves ``Track`` and all adapters untouched.  It is
used only by formal UI widgets so mock fixtures never leak into screenshots or
tooltips, while real-library metadata is always shown verbatim.
"""

from __future__ import annotations

import hashlib

from app.ui_v2.models.track import Track


_ARTISTS = (
    "林岸",
    "岑野",
    "北川",
    "Kite Harbor",
    "Nova Vale",
    "Mira Lane",
    "Common Room",
    "Dawn Study",
)
_ALBUMS = (
    "独立专辑",
    "夜间选集",
    "城市漫游",
    "私人收藏",
    "原声作品",
)
_FALLBACK_TITLES = (
    "夜色回声",
    "远处的灯",
    "静默电台",
    "晨雾之后",
)
_FORBIDDEN_VISIBLE_MARKERS = ("mock", "demo", "preview", "fixture")


def is_mock_track(track: Track) -> bool:
    """Identify only the in-memory fixture tracks used by mock mode."""

    return track.id.startswith("mock-")


def _stable_index(track: Track, modulo: int) -> int:
    digest = hashlib.sha256(track.stable_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % modulo


def _safe_text(value: str, fallback: str, track: Track) -> str:
    value = str(value or "").strip()
    lowered = value.casefold()
    if not value or any(marker in lowered for marker in _FORBIDDEN_VISIBLE_MARKERS):
        return fallback
    return value


def display_track_text(track: Track) -> tuple[str, str, str]:
    """Return title, artist and album suitable for formal user-facing UI."""

    if not is_mock_track(track):
        return (track.title, track.artist, track.album)
    title = _safe_text(
        track.title,
        _FALLBACK_TITLES[_stable_index(track, len(_FALLBACK_TITLES))],
        track,
    )
    artist = _ARTISTS[_stable_index(track, len(_ARTISTS))]
    album = _ALBUMS[_stable_index(track, len(_ALBUMS))]
    return (title, artist, album)
