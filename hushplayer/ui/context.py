"""Shared UI services.

Pages are constructed by the main window; instead of threading a dozen objects
through every widget constructor they read the application context, which the
bootstrap fills in once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..audio.controller import PlayerController
    from ..core.settings import Settings
    from ..library.artwork import CoverProvider
    from ..lyrics.service import LyricsService
    from ..online.client import OnlineSourceClient
    from ..online.proxy import AudioProxy
    from ..services.cache import CacheService
    from ..services.downloads import DownloadService
    from ..services.library import LibraryService
    from ..services.updater import UpdateService
    from ..services.state import PlaybackKeeper


@dataclass
class AppContext:
    library: "LibraryService"
    player: "PlayerController"
    lyrics: "LyricsService"
    cache: "CacheService"
    covers: "CoverProvider"
    client: "OnlineSourceClient"
    proxy: "AudioProxy"
    keeper: "PlaybackKeeper"
    settings: "Settings"
    clock: "PlaybackClock | None" = None
    window: Any = None
    downloads: "DownloadService | None" = None
    updater: "UpdateService | None" = None
    desktop_lyrics: Any = None
    immersive: Any = None


_context: AppContext | None = None


def set_context(context: AppContext) -> AppContext:
    global _context
    _context = context
    return context


def ctx() -> AppContext:
    if _context is None:
        raise RuntimeError("UI context has not been initialised")
    return _context


def has_context() -> bool:
    return _context is not None


__all__ = ["AppContext", "ctx", "has_context", "set_context"]
