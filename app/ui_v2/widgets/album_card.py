"""Album-specific presentation over the shared MediaCard surface."""

from __future__ import annotations

from app.ui_v2.models.album import Album
from app.ui_v2.models.track import format_duration
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.media_card import MediaCard


class AlbumCard(MediaCard):
    def __init__(self, album: Album, theme: Theme, parent=None) -> None:
        super().__init__(album.id, "album", theme, parent)
        self.set_album(album)

    def set_album(self, album: Album) -> None:
        self.entity_id = album.id
        self.set_content(
            album.title,
            album.artist,
            f"{len(album.track_ids)} 首歌曲  {format_duration(album.total_duration_ms)}",
        )
