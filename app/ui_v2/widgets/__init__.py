"""Reusable presentation components for UI V2."""

from app.ui_v2.widgets.track_table import TrackTable
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.navigation_item import NavigationItem
from app.ui_v2.widgets.playback_button import PlaybackButton

__all__ = [
    "ArtworkThumbnail",
    "ElidedLabel",
    "NavigationItem",
    "PlaybackButton",
    "TrackTable",
]
