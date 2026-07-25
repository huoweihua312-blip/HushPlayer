"""Cached UI V2 music-library route pages and their shared action bridge."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.artists_adapter import ArtistsAdapter
from app.ui_v2.adapters.favorites_adapter import FavoritesAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.online_source_adapter import OnlineSourceAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter, PlaylistTrackAdapter
from app.ui_v2.adapters.recent_adapter import RecentAdapter
from app.ui_v2.pages.album_detail_page import AlbumDetailPage
from app.ui_v2.pages.albums_page import AlbumsPage
from app.ui_v2.pages.artist_detail_page import ArtistDetailPage
from app.ui_v2.pages.artists_page import ArtistsPage
from app.ui_v2.pages.favorites_page import FavoritesPage
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.pages.online_search_page import OnlineSearchPage
from app.ui_v2.pages.online_source_page import OnlineSourcePage
from app.ui_v2.pages.playlist_page import PlaylistPage
from app.ui_v2.pages.recent_page import RecentPage
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class ComingSoonPage(QWidget):
    """A formal V2 destination for routes outside the current implementation stage."""

    def __init__(
        self, title: str, icon_name: str, theme: Theme, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self.icon_label = QLabel(self)
        self.title_label = QLabel(title, self)
        self.detail_label = QLabel("该页面将在后续阶段实现。", self)
        self.detail_label.setWordWrap(True)
        for label in (self.icon_label, self.title_label, self.detail_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)
        self._icon_name = icon_name
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(f"background: {theme.colors.content_background};")
        self.icon_label.setPixmap(icon(self._icon_name, theme, "selected").pixmap(32, 32))
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )


class ContentRouter(QStackedWidget):
    """Caches static pages and reuses one detail page per entity kind."""

    track_play_requested = Signal(object, str)
    queue_requested = Signal(object, bool)
    online_play_requested = Signal(object)

    ROUTE_METADATA = {
        "online_search": ("在线搜索", "search"),
        "lyrics": ("歌词", "lyrics"),
        "settings": ("设置", "settings"),
    }

    def __init__(
        self,
        library_page: LibraryPage,
        navigation: NavigationAdapter,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        online: OnlineAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._navigation = navigation
        self._collection = collection
        self._playlists = playlists
        self._online_adapter = online
        self._online_sources = OnlineSourceAdapter(online, self)
        self._pages: dict[str, QWidget] = {"library": library_page}
        self._favorites_adapter = FavoritesAdapter(collection, self)
        self._recent_adapter = RecentAdapter(collection, self)
        self._playlist_tracks = PlaylistTrackAdapter(collection, playlists, self)
        self._artists_adapter = ArtistsAdapter(collection, self)
        self._albums_adapter = AlbumsAdapter(collection, self)
        self.addWidget(library_page)
        library_page.track_table.play_requested.connect(
            lambda track_id: self.track_play_requested.emit(
                library_page.adapter.tracks(), track_id
            )
        )
        navigation.route_changed.connect(self.show_route)
        self.show_route(navigation.route)

    def page_for_route(self, route_id: str) -> QWidget:
        if route_id in {"liked", "favorites"}:
            return self._cached_page("favorites", self._create_favorites_page)
        if route_id == "recent":
            return self._cached_page("recent", self._create_recent_page)
        if route_id == "artists":
            return self._cached_page("artists", self._create_artists_page)
        if route_id == "albums":
            return self._cached_page("albums", self._create_albums_page)
        if route_id == "online_search":
            return self._cached_page("online_search", self._create_online_search_page)
        if route_id == "online_sources":
            return self._cached_page("online_sources", self._create_online_source_page)
        if route_id.startswith("playlist:"):
            page = self._cached_page("playlist", self._create_playlist_page)
            page.set_playlist(route_id.removeprefix("playlist:"))
            return page
        if route_id.startswith("artist_detail:"):
            page = self._cached_page("artist_detail", self._create_artist_detail_page)
            page.set_artist(route_id.removeprefix("artist_detail:"))
            return page
        if route_id.startswith("album_detail:"):
            page = self._cached_page("album_detail", self._create_album_detail_page)
            page.set_album(route_id.removeprefix("album_detail:"))
            return page
        if route_id == "library":
            return self._pages["library"]
        return self._cached_page(route_id, lambda: self._create_coming_soon(route_id))

    def show_route(self, route_id: str) -> None:
        self.setCurrentWidget(self.page_for_route(route_id))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for page in dict.fromkeys(self._pages.values()):
            if hasattr(page, "set_theme"):
                page.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        for page in dict.fromkeys(self._pages.values()):
            if hasattr(page, "set_responsive_reference_width"):
                page.set_responsive_reference_width(width)

    def set_playing_track(self, track_id: str) -> None:
        self._online_adapter.set_playing_track(track_id)

    @property
    def cached_page_count(self) -> int:
        return len(self._pages)

    def _cached_page(self, key: str, factory) -> QWidget:
        if key not in self._pages:
            page = factory()
            self._pages[key] = page
            self.addWidget(page)
        return self._pages[key]

    def _wire_track_page(self, page: TrackListPage) -> TrackListPage:
        page.track_play_requested.connect(self.track_play_requested)
        page.queue_requested.connect(self.queue_requested)
        page.browse_library_requested.connect(lambda: self._navigation.set_route("library"))
        return page

    def _create_favorites_page(self) -> FavoritesPage:
        return self._wire_track_page(FavoritesPage(self._favorites_adapter, self._theme, self))

    def _create_recent_page(self) -> RecentPage:
        return self._wire_track_page(RecentPage(self._recent_adapter, self._theme, self))

    def _create_playlist_page(self) -> PlaylistPage:
        page = PlaylistPage(self._playlist_tracks, self._playlists, self._theme, self)
        page.playlist_deleted.connect(lambda _playlist_id: self._navigation.set_route("library"))
        return self._wire_track_page(page)

    def _create_artists_page(self) -> ArtistsPage:
        page = ArtistsPage(self._artists_adapter, self._theme, self)
        page.entity_requested.connect(
            lambda artist_id: self._navigation.set_route(f"artist_detail:{artist_id}")
        )
        return page

    def _create_albums_page(self) -> AlbumsPage:
        page = AlbumsPage(self._albums_adapter, self._theme, self)
        page.entity_requested.connect(
            lambda album_id: self._navigation.set_route(f"album_detail:{album_id}")
        )
        return page

    def _create_artist_detail_page(self) -> ArtistDetailPage:
        page = ArtistDetailPage(self._collection, self._artists_adapter, self._theme, self)
        page.back_button.clicked.connect(lambda: self._navigation.set_route("artists"))
        return self._wire_track_page(page)

    def _create_album_detail_page(self) -> AlbumDetailPage:
        page = AlbumDetailPage(self._collection, self._albums_adapter, self._theme, self)
        page.back_button.clicked.connect(lambda: self._navigation.set_route("albums"))
        return self._wire_track_page(page)

    def _create_online_search_page(self) -> OnlineSearchPage:
        page = OnlineSearchPage(self._online_adapter, self._playlists, self._theme, self)
        page.source_management_requested.connect(
            lambda: self._navigation.set_route("online_sources")
        )
        self._online_adapter.play_requested.connect(self.online_play_requested)
        return page

    def _create_online_source_page(self) -> OnlineSourcePage:
        page = OnlineSourcePage(self._online_sources, self._theme, self)
        page.back_requested.connect(lambda: self._navigation.set_route("online_search"))
        return page

    def _create_coming_soon(self, route_id: str) -> ComingSoonPage:
        title, icon_name = self.ROUTE_METADATA.get(route_id, ("页面", "library"))
        return ComingSoonPage(title, icon_name, self._theme, self)
