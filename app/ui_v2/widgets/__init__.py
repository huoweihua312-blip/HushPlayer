"""Reusable presentation components for UI V2."""

from app.ui_v2.widgets.track_table import TrackTable
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.navigation_item import NavigationItem
from app.ui_v2.widgets.playback_button import PlaybackButton
from app.ui_v2.widgets.cover_card import CoverCard
from app.ui_v2.widgets.custom_title_bar import CustomTitleBar

__all__ = [
    "ArtworkThumbnail",
    "CoverCard",
    "CustomTitleBar",
    "ElidedLabel",
    "NavigationItem",
    "PlaybackButton",
    "TrackTable",
]
