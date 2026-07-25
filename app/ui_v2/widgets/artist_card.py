"""Artist-specific presentation over the shared MediaCard surface."""

from __future__ import annotations

from app.ui_v2.models.artist import Artist
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.media_card import MediaCard


class ArtistCard(MediaCard):
    def __init__(self, artist: Artist, theme: Theme, parent=None) -> None:
        super().__init__(artist.id, "artist", theme, parent)
        self.set_artist(artist)

    def set_artist(self, artist: Artist) -> None:
        self.entity_id = artist.id
        self.set_content(
            artist.name,
            f"{len(artist.track_ids)} 首歌曲",
            f"{len(artist.album_ids)} 张专辑",
        )
