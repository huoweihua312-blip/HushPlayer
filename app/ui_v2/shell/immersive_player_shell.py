"""Shared immersive playback shell.

The implementation lives in :class:`ImmersiveLyricsPage` for backwards
compatibility with the approved lyrics route.  This semantic subclass gives
the stage-3 architecture a stable name without allocating another player or
another top-level window.
"""

from __future__ import annotations

from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage


class ImmersivePlayerShell(ImmersiveLyricsPage):
    """One cached shell containing Now Playing and Lyrics modes."""

    pass
