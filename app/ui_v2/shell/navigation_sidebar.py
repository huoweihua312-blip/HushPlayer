"""Approved V3 navigation shell with a fixed chrome and one playlist scroller."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QDialog,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.models.navigation_item import NavigationItem as NavigationValue
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.navigation_item import NavigationItem
from app.ui_v2.widgets.playlist_dialogs import PlaylistConfirmDialog, PlaylistNameDialog
from app.ui_v2.widgets.quiet_context_menu import apply_menu_theme


_PLAYLIST_COVER_DIR = Path(__file__).resolve().parent.parent / "assets" / "sidebar_playlist_covers"
_PLAYLIST_COVERS = ("midnight", "daily", "coast")
_QUIET_ORBIT_LOGO = Path(__file__).resolve().parent.parent / "assets" / "quiet-orbit-logo.svg"


class NavigationSidebar(QFrame):
    """Persistent 220px navigation rail with one contained playlist scroller."""

    more_playlists_requested = Signal()
    new_playlist_requested = Signal()
    settings_requested = Signal()

    def __init__(
        self,
        adapter: NavigationAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self._compact = False
        self._items: dict[str, NavigationItem] = {}
        self._playlist_items: dict[str, NavigationItem] = {}
        self._section_labels: list[QLabel] = []
        self.setObjectName("navigationSidebar")
        self.setFixedWidth(theme.metrics.sidebar_width)

        self.brand = QWidget(self)
        self.brand.setObjectName("navigationBrand")
        self.brand.setFixedHeight(84)
        brand_layout = QHBoxLayout(self.brand)
        brand_layout.setContentsMargins(28, 0, 16, 0)
        brand_layout.setSpacing(11)
        self.brand_mark = QLabel(self.brand)
        self.brand_mark.setObjectName("navigationBrandMark")
        self.brand_mark.setFixedSize(40, 28)
        self.brand_label = QLabel("HushPlayer", self.brand)
        self.brand_label.setObjectName("navigationBrandLabel")
        self.brand_label.setToolTip("HushPlayer")
        brand_layout.addWidget(self.brand_mark)
        brand_layout.addWidget(self.brand_label)
        brand_layout.addStretch(1)
        # Keep the historical public brand handles for integrations and tests,
        # but render the visible lockup in the aligned TopBar column.
        self.brand.setVisible(False)

        self.primary_section = QWidget(self)
        self.primary_section.setObjectName("navigationPrimarySection")
        self.library_box = self.primary_section  # Compatibility handle for existing shell tests.
        primary_layout = QVBoxLayout(self.primary_section)
        primary_layout.setContentsMargins(18, 20, 14, 0)
        primary_layout.setSpacing(0)
        self.library_caption = self._caption("资料库", self.primary_section)
        self.library_caption.setFixedHeight(29)
        primary_layout.addWidget(self.library_caption)
        self._add_static_item("library", primary_layout, 42)
        self._add_static_item("browse", primary_layout, 42)
        if any(item.route_id == "online_search" for item in adapter.items()):
            self._add_static_item("online_search", primary_layout, 42)

        self.playlist_section = QWidget(self)
        self.playlist_section.setObjectName("navigationPlaylistSection")
        playlist_outer = QVBoxLayout(self.playlist_section)
        playlist_outer.setContentsMargins(18, 20, 14, 0)
        playlist_outer.setSpacing(5)
        self.playlist_caption_row = QWidget(self.playlist_section)
        self.playlist_caption_row.setObjectName("playlistCaptionRow")
        caption_layout = QHBoxLayout(self.playlist_caption_row)
        caption_layout.setContentsMargins(0, 0, 0, 0)
        caption_layout.setSpacing(4)
        self.playlist_caption = self._caption("歌单", self.playlist_caption_row)
        self.playlist_caption.setFixedHeight(25)
        caption_layout.addWidget(self.playlist_caption)
        caption_layout.addStretch(1)
        self.playlist_add_button = QToolButton(self.playlist_caption_row)
        self.playlist_add_button.setObjectName("playlistAddButton")
        self.playlist_add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.playlist_add_button.setFixedSize(26, 26)
        self.playlist_add_button.setToolTip("新建歌单")
        self.playlist_add_button.setAccessibleName("新建歌单")
        self.playlist_add_button.setVisible(adapter.playlist_adapter.can_mutate)
        self.playlist_add_button.clicked.connect(self.new_playlist_requested)
        self.playlist_add_button.clicked.connect(self._open_create_playlist_dialog)
        caption_layout.addWidget(self.playlist_add_button)
        playlist_outer.addWidget(self.playlist_caption_row)
        self.scroll_area = QScrollArea(self.playlist_section)
        self.scroll_area.setObjectName("navigationScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.viewport().setObjectName("navigationViewport")
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("navigationContent")
        self.playlist_layout = QVBoxLayout(self.content)
        self.playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.playlist_layout.setSpacing(0)
        self.playlist_container = self.content
        self._add_static_item("liked", self.playlist_layout, 42)
        # Compatibility handle for older shell tests. It is not attached to
        # the layout and therefore cannot appear as a dead visible action.
        self.more_playlists_button = NavigationItem(
            NavigationValue("more_playlists", "更多歌单", "playlist_more", "歌单"),
            self._theme,
            self.content,
        )
        self.more_playlists_button.setObjectName("morePlaylistsButton")
        self.more_playlists_button.setFixedHeight(42)
        self.more_playlists_button.setVisible(False)
        self.more_playlists_button.route_requested.connect(
            lambda _route_id: self.more_playlists_requested.emit()
        )
        self.playlist_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        playlist_outer.addWidget(self.scroll_area, 1)

        self.settings_box = QWidget(self)
        self.settings_box.setObjectName("navigationSettingsBox")
        self.settings_box.setFixedHeight(72)
        settings_layout = QVBoxLayout(self.settings_box)
        settings_layout.setContentsMargins(18, 13, 14, 17)
        settings_layout.setSpacing(0)
        self._add_static_item("settings", settings_layout, 42)
        # The top bar owns the one visible Settings entry in Quiet Orbit.  The
        # hidden widget and signal remain for compatibility with V2 callers.
        self.settings_box.setVisible(False)

        # Keep the historical public handle while making the add action real.
        self.new_playlist_button = self.playlist_add_button

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.primary_section)
        layout.addWidget(self.playlist_section, 1)
        layout.addWidget(self.settings_box)

        self.adapter.route_changed.connect(self._update_selected_route)
        self.adapter.playlists_changed.connect(self._refresh_playlists)
        self._refresh_playlists(self.adapter.playlists())
        self.set_theme(theme)
        self._update_selected_route(adapter.route)

    @property
    def compact(self) -> bool:
        return self._compact

    @property
    def item_count(self) -> int:
        return len(self._items) + len(self._playlist_items)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QFrame#navigationSidebar {{ background: {c.sidebar_background}; border-right: 1px solid {c.divider}; }}"
            f"QScrollArea#navigationScrollArea, QAbstractScrollArea#navigationScrollArea::viewport, "
            f"QWidget#navigationViewport, QWidget#navigationContent {{ background: {c.sidebar_background}; border: 0; }}"
            f"QScrollArea#navigationScrollArea QScrollBar:vertical {{ width: 6px; background: transparent; margin: 2px 0; border: 0; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 3px; background: {c.border_strong}; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::handle:vertical:hover {{ background: {c.secondary_text}; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::add-line:vertical, QScrollArea#navigationScrollArea QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::add-page:vertical, QScrollArea#navigationScrollArea QScrollBar::sub-page:vertical {{ background: transparent; }}"
            f"QWidget#navigationSettingsBox {{ border-top: 1px solid {c.divider}; }}"
            f"QLabel#navigationBrandMark {{ background: transparent; }}"
            f"QLabel#navigationBrandLabel {{ color: {c.text_primary}; font-size: 17px; font-weight: 600; }}"
        )
        logo = QPixmap(str(_QUIET_ORBIT_LOGO))
        self.brand_mark.setPixmap(
            logo.scaled(
                self.brand_mark.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        for label in self._section_labels:
            label.setStyleSheet(
                f"padding-left: 12px; color: {c.text_tertiary}; font-size: 12px; font-weight: 400;"
            )
        for item in (*self._items.values(), *self._playlist_items.values()):
            item.set_theme(theme)
        self.more_playlists_button.set_theme(theme)
        self.playlist_add_button.setIcon(icon("add", theme, "normal"))
        self.playlist_add_button.setIconSize(QSize(17, 17))
        self.playlist_add_button.setStyleSheet(
            f"QToolButton#playlistAddButton {{ border: 0; border-radius: {theme.metrics.radius_sm}px; "
            f"background: transparent; color: {c.secondary_text}; }}"
            f"QToolButton#playlistAddButton:hover {{ background: {c.hover_background}; color: {c.primary_text}; }}"
            f"QToolButton#playlistAddButton:pressed {{ background: {c.playing_background}; }}"
        )
        self._apply_surface_backgrounds(c.sidebar_background)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.setFixedWidth(
            self._theme.metrics.compact_sidebar_width if compact else self._theme.metrics.sidebar_width
        )
        self.brand_label.setVisible(not compact)
        self.library_caption.setVisible(not compact)
        self.playlist_caption.setVisible(not compact)
        self.brand.layout().setContentsMargins(18 if compact else 28, 0, 18 if compact else 16, 0)
        self.primary_section.layout().setContentsMargins(12 if compact else 18, 20, 12 if compact else 14, 0)
        self.playlist_section.layout().setContentsMargins(12 if compact else 18, 20, 12 if compact else 14, 0)
        for item in (*self._items.values(), *self._playlist_items.values()):
            item.set_compact(compact)
        self.more_playlists_button.set_compact(compact)
        self.playlist_add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def create_mock_playlist(self, name: str = "") -> str:
        playlist = self.adapter.create_playlist(name)
        return playlist.id if playlist is not None else ""

    def rename_mock_playlist(self, playlist_id: str, name: str) -> bool:
        return self.adapter.rename_playlist(playlist_id, name)

    def delete_mock_playlist(self, playlist_id: str) -> bool:
        return self.adapter.delete_playlist(playlist_id)

    def _open_create_playlist_dialog(self) -> str:
        if not self.adapter.playlist_adapter.can_mutate:
            return ""
        dialog = PlaylistNameDialog(self._theme, "新建歌单", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        playlist = self.adapter.create_playlist(dialog.name)
        return playlist.id if playlist is not None else ""

    def _caption(self, text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("navigationCaption")
        self._section_labels.append(label)
        return label

    def _add_static_item(self, route_id: str, layout: QVBoxLayout, height: int) -> NavigationItem:
        value = next(item for item in self.adapter.items() if item.route_id == route_id)
        item = NavigationItem(value, self._theme, layout.parentWidget())
        item.setFixedHeight(height)
        if route_id == "settings":
            item.route_requested.connect(lambda _route_id: self.settings_requested.emit())
        else:
            item.route_requested.connect(self.adapter.set_route)
        self._items[route_id] = item
        layout.addWidget(item)
        return item

    def _refresh_playlists(self, playlists) -> None:
        for item in self._playlist_items.values():
            self.playlist_layout.removeWidget(item)
            item.deleteLater()
        self._playlist_items.clear()
        for index, playlist in enumerate(tuple(playlists), start=1):
            value = NavigationValue(
                f"playlist:{playlist.id}", playlist.name, "playlist", "歌单", playlist.id
            )
            item = NavigationItem(value, self._theme, self.content)
            item.setFixedHeight(42)
            item.set_custom_icon(self._playlist_cover_icon(playlist.id, playlist.name))
            item.set_compact(self._compact)
            item.route_requested.connect(self.adapter.set_route)
            item.context_requested.connect(self._show_playlist_menu)
            self._playlist_items[playlist.id] = item
            self.playlist_layout.insertWidget(index, item)
        self.playlist_layout.activate()
        for item in self._playlist_items.values():
            item.refresh_elided_text()
        self._update_selected_route(self.adapter.route)

    def _playlist_cover_icon(self, playlist_id: str, playlist_name: str) -> QIcon:
        identity = f"{playlist_id}:{playlist_name}".casefold()
        if "night" in identity or "深夜" in identity:
            cover_name = "midnight"
        elif "daily" in identity or "日常" in identity:
            cover_name = "daily"
        else:
            cover_name = _PLAYLIST_COVERS[sha256(playlist_id.encode("utf-8")).digest()[0] % len(_PLAYLIST_COVERS)]
        return QIcon(str(_PLAYLIST_COVER_DIR / f"{cover_name}.svg"))

    def _update_selected_route(self, route_id: str) -> None:
        for route, item in self._items.items():
            item.set_selected(route == route_id)
        for playlist_id, item in self._playlist_items.items():
            item.set_selected(route_id == f"playlist:{playlist_id}")

    def _apply_surface_backgrounds(self, background: str) -> None:
        for surface in (
            self,
            self.scroll_area,
            self.scroll_area.viewport(),
            self.content,
            self.playlist_container,
        ):
            palette = surface.palette()
            color = QColor(background)
            palette.setColor(QPalette.ColorRole.Window, color)
            palette.setColor(QPalette.ColorRole.Base, color)
            surface.setPalette(palette)
            surface.setAutoFillBackground(True)

    def _show_playlist_menu(self, playlist_id: str, global_position) -> None:
        if not self.adapter.playlist_adapter.can_mutate or playlist_id == "liked":
            return
        menu = apply_menu_theme(QMenu(self), self._theme)
        rename_action = menu.addAction("重命名歌单")
        delete_action = menu.addAction("删除歌单")
        selected = menu.exec(global_position)
        if selected is rename_action:
            playlist = next(
                (item for item in self.adapter.playlists() if item.id == playlist_id), None
            )
            if playlist is not None:
                dialog = PlaylistNameDialog(
                    self._theme,
                    "重命名歌单",
                    initial_name=playlist.name,
                    parent=self,
                )
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.adapter.rename_playlist(playlist_id, dialog.name)
        elif selected is delete_action:
            dialog = PlaylistConfirmDialog(
                self._theme,
                "删除歌单",
                "删除歌单不会删除音乐库中的歌曲。",
                parent=self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.adapter.delete_playlist(playlist_id)
        menu.deleteLater()
