"""Shared artwork-first cards for related content surfaces."""

from __future__ import annotations

from app.ui_v2.models.playlist import Playlist
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.media_card import MediaCard


class CompactContentCard(MediaCard):
    """Stable artwork/title/meta geometry for compact content collections."""


class PlaylistCard(CompactContentCard):
    """Playlist identity card sharing the same visual base as Artist/Album."""

    def __init__(
        self,
        playlist: Playlist,
        theme: Theme,
        parent=None,
        representative: Track | None = None,
    ) -> None:
        super().__init__(playlist.id, "playlist", theme, parent)
        self.set_playlist(playlist, representative)

    def set_playlist(self, playlist: Playlist, representative: Track | None = None) -> None:
        self.entity_id = playlist.id
        if representative is not None:
            self.set_artwork(representative)
        self.set_content(
            playlist.name,
            "本地歌单",
            f"{len(playlist.entries)} 首歌曲",
        )


__all__ = ["CompactContentCard", "PlaylistCard"]
