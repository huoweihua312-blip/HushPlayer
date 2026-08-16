"""Responsive column policy shared by every Quiet Orbit track surface."""

from __future__ import annotations

from dataclasses import dataclass

from app.ui_v2.models.track_table_model import TrackColumn


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    """A stable table profile chosen from the shell reference width."""

    name: str
    visible: tuple[TrackColumn, ...]


class ResponsiveColumnPolicy:
    """Keep the song column flexible while preserving the action column."""

    @staticmethod
    def profile_for_width(width: int) -> ColumnProfile:
        value = int(width)
        if value < 950:
            return ColumnProfile(
                "narrow",
                (
                    TrackColumn.STATUS,
                    TrackColumn.TITLE,
                    TrackColumn.ARTIST,
                    TrackColumn.DURATION,
                    TrackColumn.MORE,
                ),
            )
        if value < 1220:
            return ColumnProfile(
                "standard",
                (
                    TrackColumn.STATUS,
                    TrackColumn.TITLE,
                    TrackColumn.ARTIST,
                    TrackColumn.ALBUM,
                    TrackColumn.DURATION,
                    TrackColumn.FAVORITE,
                    TrackColumn.MORE,
                ),
            )
        return ColumnProfile(
            "wide",
            (
                TrackColumn.STATUS,
                TrackColumn.TITLE,
                TrackColumn.ARTIST,
                TrackColumn.ALBUM,
                TrackColumn.DURATION,
                TrackColumn.FAVORITE,
                TrackColumn.SOURCE,
                TrackColumn.MORE,
            ),
        )

    @staticmethod
    def widths(profile: str, viewport_width: int) -> dict[TrackColumn, int]:
        width = max(1, int(viewport_width))
        if profile == "narrow":
            status, duration, more = 40, 68, 42
            remaining = max(320, width - status - duration - more)
            artist = min(150, max(120, int(remaining * 0.29)))
            return {
                TrackColumn.STATUS: status,
                TrackColumn.TITLE: max(150, remaining - artist),
                TrackColumn.ARTIST: artist,
                TrackColumn.ALBUM: 0,
                TrackColumn.DURATION: duration,
                TrackColumn.FAVORITE: 0,
                TrackColumn.SOURCE: 0,
                TrackColumn.MORE: more,
            }
        if profile == "standard":
            status, favorite, duration, artist, album, more = 40, 40, 74, 140, 130, 42
            return {
                TrackColumn.STATUS: status,
                TrackColumn.FAVORITE: favorite,
                TrackColumn.TITLE: max(160, width - status - favorite - duration - artist - album - more),
                TrackColumn.ARTIST: artist,
                TrackColumn.ALBUM: album,
                TrackColumn.DURATION: duration,
                TrackColumn.SOURCE: 0,
                TrackColumn.MORE: more,
            }
        status, favorite, duration, artist, album, source, more = 40, 40, 80, 200, 240, 140, 44
        return {
            TrackColumn.STATUS: status,
            TrackColumn.FAVORITE: favorite,
            TrackColumn.TITLE: max(220, width - status - favorite - duration - artist - album - source - more),
            TrackColumn.ARTIST: artist,
            TrackColumn.ALBUM: album,
            TrackColumn.DURATION: duration,
            TrackColumn.SOURCE: source,
            TrackColumn.MORE: more,
        }
