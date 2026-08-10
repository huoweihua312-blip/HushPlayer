"""Artist-specific presentation over the shared MediaCard surface."""

from __future__ import annotations

from app.ui_v2.models.artist import Artist
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.media_card import MediaCard


class ArtistCard(MediaCard):
    def __init__(self, artist: Artist, theme: Theme, parent=None, representative: Track | None = None) -> None:
        super().__init__(artist.id, "artist", theme, parent)
        self.set_artist(artist, representative)

    def set_artist(self, artist: Artist, representative: Track | None = None) -> None:
        self.entity_id = artist.id
        if representative is not None:
            self.set_artwork(representative, circular=True)
        self.set_content(
            artist.name,
            f"{len(artist.track_ids)} 首歌曲",
            f"{len(artist.album_ids)} 张专辑",
        )
