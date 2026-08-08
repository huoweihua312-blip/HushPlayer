"""Shared detail heroes for Playlist, Favorites and Album content pages."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.ui_v2.models.album import Album
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.playlist_header import PlaylistHeader
from app.ui_v2.widgets.track_collection_hero import TrackCollectionHero


class PlaylistHero(PlaylistHeader):
    """Named shared Playlist hero; CRUD behavior remains in PlaylistHeader."""


class AlbumHero(TrackCollectionHero):
    """Compact album identity band that preserves artist and year semantics."""

    def set_album(self, album: Album | None, tracks: Iterable[Track] = ()) -> None:
        materialized = tuple(tracks)
        if album is None:
            self.set_content("专辑", "专辑不存在", (), "专辑")
            return
        parts = [str(album.artist or "未知艺人")]
        year = self._valid_year(album.year)
        if year is not None:
            parts.append(str(year))
        parts.append(f"{len(album.track_ids)} 首歌曲")
        total_ms = sum(track.duration_ms or 0 for track in materialized)
        if total_ms > 0:
            parts.append(format_duration(total_ms))
        self.set_content(album.title or "未命名专辑", "  ·  ".join(parts), materialized, "专辑")

    @staticmethod
    def _valid_year(value: object) -> int | None:
        try:
            year = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return year if 1900 <= year <= date.today().year + 1 and year != 1970 else None
