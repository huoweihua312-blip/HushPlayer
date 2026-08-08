"""Public names for the Q3 shared content component contract."""

from app.ui_v2.widgets.content_heroes import AlbumHero, PlaylistHero
from app.ui_v2.widgets.content_cards import CompactContentCard, PlaylistCard
from app.ui_v2.widgets.artist_card import ArtistCard
from app.ui_v2.widgets.album_card import AlbumCard
from app.ui_v2.widgets.content_states import InlineErrorState
from app.ui_v2.widgets.page_header import PageHeader
from app.ui_v2.widgets.quiet_context_menu import QuietContextMenu
from app.ui_v2.widgets.responsive_columns import ResponsiveColumnPolicy
from app.ui_v2.widgets.section_toolbar import SectionToolbar
from app.ui_v2.widgets.track_delegate import TrackDelegate
from app.ui_v2.widgets.track_table import TrackTable


class ContentPageHeader(PageHeader):
    """Q3 name for the shell-compatible content page header."""


class ActionToolbar(SectionToolbar):
    """Q3 name for the shared lightweight action row."""


class QuietTrackTable(TrackTable):
    """Q3 name for the single virtualized track table implementation."""


class QuietTrackDelegate(TrackDelegate):
    """Q3 name for the single row delegate implementation."""


__all__ = [
    "ActionToolbar",
    "AlbumCard",
    "AlbumHero",
    "ContentPageHeader",
    "CompactContentCard",
    "InlineErrorState",
    "ArtistCard",
    "PlaylistHero",
    "PlaylistCard",
    "QuietContextMenu",
    "QuietTrackDelegate",
    "QuietTrackTable",
    "ResponsiveColumnPolicy",
]
