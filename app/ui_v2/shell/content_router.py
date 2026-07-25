"""Page cache and route switching for the UI V2 main shell."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class ComingSoonPage(QWidget):
    """A formal V2 destination for routes outside this implementation stage."""

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
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; "
            f"color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )


class ContentRouter(QStackedWidget):
    """Caches pages so route changes preserve search, selection, and scroll state."""

    ROUTE_METADATA = {
        "liked": ("我喜欢", "favorite"),
        "recent": ("最近播放", "recent"),
        "artists": ("歌手", "artist"),
        "albums": ("专辑", "album"),
        "online_search": ("在线搜索", "search"),
        "lyrics": ("歌词", "lyrics"),
        "settings": ("设置", "settings"),
    }

    def __init__(
        self,
        library_page: LibraryPage,
        navigation: NavigationAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._navigation = navigation
        self._pages: dict[str, QWidget] = {"library": library_page}
        self.addWidget(library_page)
        navigation.route_changed.connect(self.show_route)
        self.show_route(navigation.route)

    def page_for_route(self, route_id: str) -> QWidget:
        if route_id not in self._pages:
            self._pages[route_id] = self._create_page(route_id)
            self.addWidget(self._pages[route_id])
        return self._pages[route_id]

    def show_route(self, route_id: str) -> None:
        self.setCurrentWidget(self.page_for_route(route_id))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for page in self._pages.values():
            if isinstance(page, (LibraryPage, ComingSoonPage)):
                page.set_theme(theme)

    @property
    def cached_page_count(self) -> int:
        return len(self._pages)

    def _create_page(self, route_id: str) -> ComingSoonPage:
        if route_id.startswith("playlist:"):
            playlist_id = route_id.removeprefix("playlist:")
            playlist = next(
                (item for item in self._navigation.playlists() if item.id == playlist_id),
                None,
            )
            title = playlist.name if playlist is not None else "歌单"
            return ComingSoonPage(title, "playlist", self._theme, self)
        title, icon_name = self.ROUTE_METADATA.get(route_id, ("页面", "library"))
        return ComingSoonPage(title, icon_name, self._theme, self)
