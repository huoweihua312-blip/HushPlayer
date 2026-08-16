"""Presentation-only labels for deterministic mock tracks.

This module deliberately leaves ``Track`` and all adapters untouched.  It is
used only by formal UI widgets so mock fixtures never leak into screenshots or
tooltips, while real-library metadata is always shown verbatim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
_UNKNOWN_METADATA = "未知艺人"

_PLAYABLE_STATES = frozenset({"available", "playable", "downloaded"})
_UNRESOLVED_STATES = frozenset({"", "unknown", "not_resolved", "not-resolved"})
_CONFIRMED_ERROR_STATES = frozenset(
    {
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
)
_RESOLVING_STATES = frozenset({"resolving", "buffering"})


@dataclass(frozen=True, slots=True)
class TrackAvailabilityPresentation:
    """Independent playback/source state for a track identity."""

    state: str = "playable"
    label: str = ""
    tooltip: str = ""

    @property
    def is_visible(self) -> bool:
        return bool(self.label)

    @property
    def is_resolving(self) -> bool:
        return self.state in _RESOLVING_STATES

    @property
    def is_confirmed_error(self) -> bool:
        return self.state in _CONFIRMED_ERROR_STATES or self.state == "missing"

    @property
    def is_retryable(self) -> bool:
        """Resolution/media failures may be attempted again by the user."""

        return self.state in {"resolve_failed", "playback_error"}

    @property
    def is_playable(self) -> bool:
        return self.state in _PLAYABLE_STATES


@dataclass(frozen=True, slots=True)
class TrackIdentityPresentation:
    """Canonical user-facing identity text shared by V2 track surfaces."""

    title: str
    artist: str
    album: str
    metadata: str
    availability: TrackAvailabilityPresentation


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


def format_track_metadata(artist: str, album: str) -> str:
    """Combine only artist and album; playback state never belongs here."""

    artist_text = str(artist or "").strip()
    album_text = str(album or "").strip()
    if artist_text and album_text:
        return f"{artist_text} · {album_text}"
    return artist_text or album_text or _UNKNOWN_METADATA


def normalize_availability_state(
    value: str,
    *,
    is_online: bool,
    is_missing: bool = False,
) -> str:
    """Normalize legacy capability values without hiding unresolved state."""

    normalized = str(value or "").strip().casefold().replace("-", "_")
    if not is_online:
        if is_missing or normalized in {"missing", "unavailable", "source_unavailable"}:
            return "missing"
        return "playable"
    if normalized in _PLAYABLE_STATES:
        return "playable"
    if normalized in _UNRESOLVED_STATES:
        return "not_resolved"
    if normalized in _RESOLVING_STATES:
        return "resolving"
    if normalized in _CONFIRMED_ERROR_STATES:
        return normalized
    return "not_resolved"


def _availability_presentation(
    *,
    is_online: bool,
    is_missing: bool,
    availability: str,
    playback_status: str,
    playback_detail: str,
) -> TrackAvailabilityPresentation:
    status = str(playback_status or "").strip().casefold()
    detail = str(playback_detail or "").strip()
    status_labels = {
        "resolving": ("准备播放", "正在准备播放这首歌曲。"),
        "buffering": ("缓冲中", "正在缓冲这首歌曲。"),
        "unavailable": (
            "暂不可播放",
            "当前无法播放这首在线歌曲。" if is_online else "当前无法播放这首歌曲。",
        ),
        "error": ("播放失败", "当前无法播放这首歌曲。"),
    }
    if status in status_labels:
        label, fallback_tooltip = status_labels[status]
        normalized_status = "playback_error" if status == "error" else status
        return TrackAvailabilityPresentation(normalized_status, label, detail or fallback_tooltip)

    normalized_availability = normalize_availability_state(
        availability,
        is_online=is_online,
        is_missing=is_missing,
    )
    if normalized_availability == "resolving":
        return TrackAvailabilityPresentation(
            "resolving",
            "解析中",
            detail or "正在准备这首在线歌曲。",
        )
    if normalized_availability in {"unknown", "not_resolved"}:
        return TrackAvailabilityPresentation("not_resolved")
    if normalized_availability in _CONFIRMED_ERROR_STATES:
        if normalized_availability == "permission_denied":
            label = "暂不可播放"
            fallback = "当前来源拒绝播放这首在线歌曲。"
        elif normalized_availability == "source_unavailable":
            label = "暂不可播放"
            fallback = "当前在线来源不可用。"
        else:
            label = "播放失败"
            fallback = "当前无法播放这首在线歌曲。"
        return TrackAvailabilityPresentation(
            normalized_availability,
            label,
            detail or fallback,
        )
    if not is_online and is_missing:
        return TrackAvailabilityPresentation(
            "missing",
            "文件不可用",
            detail or "找不到这首本地歌曲文件。",
        )
    return TrackAvailabilityPresentation()


def present_track_identity_values(
    title: str,
    artist: str,
    album: str,
    *,
    is_online: bool = False,
    is_missing: bool = False,
    availability: str = "available",
    playback_status: str = "",
    playback_detail: str = "",
) -> TrackIdentityPresentation:
    """Build identity and independent availability text from stable fields."""

    title_text = str(title or "").strip()
    artist_text = str(artist or "").strip()
    album_text = str(album or "").strip()
    return TrackIdentityPresentation(
        title=title_text,
        artist=artist_text,
        album=album_text,
        metadata=format_track_metadata(artist_text, album_text),
        availability=_availability_presentation(
            is_online=is_online,
            is_missing=is_missing,
            availability=availability,
            playback_status=playback_status,
            playback_detail=playback_detail,
        ),
    )


def present_track_identity(
    track: Track,
    *,
    playback_status: str = "",
    playback_detail: str = "",
) -> TrackIdentityPresentation:
    """Present a Track without allowing playback state into its metadata."""

    title, artist, album = display_track_text(track)
    return present_track_identity_values(
        title,
        artist,
        album,
        is_online=track.is_online,
        is_missing=track.is_missing,
        availability=track.availability,
        playback_status=playback_status,
        playback_detail=playback_detail or track.availability_detail,
    )
