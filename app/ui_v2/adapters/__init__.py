"""State adapters between V2 pages and data providers."""

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter

__all__ = ["LibraryAdapter", "NavigationAdapter", "PlaybackAdapter"]
