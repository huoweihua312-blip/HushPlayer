"""Responsive, mock-data navigation for the second-phase UI V2 shell."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QInputDialog,
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


class NavigationSidebar(QFrame):
    """Keeps nav widgets stable while width changes between compact and full."""

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
        self.brand_label = QLabel("HushPlayer", self)
        self.brand_label.setToolTip("HushPlayer")
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("navigationScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setObjectName("navigationViewport")
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("navigationContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 4, 10, 12)
        self.content_layout.setSpacing(4)
        self.scroll_area.setWidget(self.content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.brand_label)
        layout.addWidget(self.scroll_area, 1)
        self._build_static_items()
        self._build_playlist_section()
        self.adapter.route_changed.connect(self._update_selected_route)
        self.adapter.playlists_changed.connect(self._refresh_playlists)
        self.set_theme(theme)
        self._update_selected_route(adapter.route)
        self.setFixedWidth(224)

    @property
    def compact(self) -> bool:
        return self._compact

    @property
    def item_count(self) -> int:
        return len(self._items) + len(self._playlist_items)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        background = theme.colors.navigation_background
        self.setStyleSheet(
            f"QFrame#navigationSidebar {{ background: {background}; "
            f"border-right: 1px solid {theme.colors.border}; }}"
            f"QScrollArea#navigationScrollArea {{ border: 0; background: {background}; }}"
            f"QAbstractScrollArea#navigationScrollArea::viewport {{ background: {background}; }}"
            f"QWidget#navigationViewport, QWidget#navigationContent, "
            f"QWidget#playlistContainer {{ background: {background}; }}"
            f"QScrollArea#navigationScrollArea QScrollBar:vertical {{ width: 10px; "
            f"border: 0; background: {background}; margin: 4px 2px; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::handle:vertical {{ "
            f"min-height: 32px; border-radius: 4px; background: {theme.colors.border_strong}; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::handle:vertical:hover {{ "
            f"background: {theme.colors.secondary_text}; }}"
            f"QScrollArea#navigationScrollArea QScrollBar::add-line:vertical, "
            f"QScrollArea#navigationScrollArea QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        self.brand_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; "
            f"padding: 0 8px; color: {theme.colors.primary_text};"
        )
        for label in self._section_labels:
            label.setStyleSheet(
                f"font-size: {theme.fonts.caption}px; padding: 10px 8px 2px; "
                f"color: {theme.colors.subtle_text};"
            )
        for item in (*self._items.values(), *self._playlist_items.values()):
            item.set_theme(theme)
        self._refresh_add_button()
        for surface in (
            self,
            self.scroll_area,
            self.scroll_area.viewport(),
            self.content,
            self.playlist_container,
        ):
            self._apply_surface_background(surface, background)
            self._repolish(surface)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if self._compact == compact:
            return
        self._compact = compact
        self.setFixedWidth(64 if compact else 224)
        self.brand_label.setText("HP" if compact else "HushPlayer")
        self.brand_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter if compact else Qt.AlignmentFlag.AlignLeft
        )
        for label in self._section_labels:
            label.setVisible(not compact)
        for item in (*self._items.values(), *self._playlist_items.values()):
            item.set_compact(compact)
        self.new_playlist_button.setText("" if compact else "新建歌单")
        self.new_playlist_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._refresh_add_button()

    def create_mock_playlist(self, name: str = "") -> str:
        playlist = self.adapter.create_playlist(name)
        return playlist.id if playlist is not None else ""

    def rename_mock_playlist(self, playlist_id: str, name: str) -> bool:
        return self.adapter.rename_playlist(playlist_id, name)

    def delete_mock_playlist(self, playlist_id: str) -> bool:
        return self.adapter.delete_playlist(playlist_id)

    def _build_static_items(self) -> None:
        last_group = ""
        for item in self.adapter.items():
            if item.group != last_group:
                self._add_section_label(item.group)
                last_group = item.group
            self._add_navigation_item(item)

    def _build_playlist_section(self) -> None:
        self._add_section_label("歌单")
        self.playlist_container = QWidget(self.content)
        self.playlist_container.setObjectName("playlistContainer")
        self.playlist_layout = QVBoxLayout(self.playlist_container)
        self.playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.playlist_layout.setSpacing(4)
        self.content_layout.addWidget(self.playlist_container)
        self.new_playlist_button = QToolButton(self.content)
        self.new_playlist_button.setToolTip("新建歌单")
        self.new_playlist_button.clicked.connect(self._create_playlist_from_ui)
        self.content_layout.addWidget(self.new_playlist_button)
        self.content_layout.addStretch(1)
        self._refresh_playlists(self.adapter.playlists())

    def _add_section_label(self, text: str) -> None:
        label = QLabel(text, self.content)
        self._section_labels.append(label)
        self.content_layout.addWidget(label)

    def _add_navigation_item(self, item: NavigationValue) -> NavigationItem:
        widget = NavigationItem(item, self._theme, self.content)
        widget.route_requested.connect(self.adapter.set_route)
        widget.context_requested.connect(self._show_playlist_menu)
        self._items[item.route_id] = widget
        self.content_layout.addWidget(widget)
        return widget

    def _refresh_playlists(self, playlists) -> None:
        for item in self._playlist_items.values():
            self.playlist_layout.removeWidget(item)
            item.deleteLater()
        self._playlist_items.clear()
        for playlist in playlists:
            value = NavigationValue(
                f"playlist:{playlist.id}",
                playlist.name,
                "playlist",
                "歌单",
                playlist.id,
            )
            widget = NavigationItem(value, self._theme, self.playlist_container)
            widget.set_compact(self._compact)
            widget.route_requested.connect(self.adapter.set_route)
            widget.context_requested.connect(self._show_playlist_menu)
            self._playlist_items[playlist.id] = widget
            self.playlist_layout.addWidget(widget)
        self._update_selected_route(self.adapter.route)

    def _update_selected_route(self, route_id: str) -> None:
        for route, item in self._items.items():
            item.set_selected(route == route_id)
        for playlist_id, item in self._playlist_items.items():
            item.set_selected(route_id == f"playlist:{playlist_id}")

    def _refresh_add_button(self) -> None:
        read_only = self.adapter.playlist_adapter.read_only
        self.new_playlist_button.setVisible(not read_only)
        self.new_playlist_button.setEnabled(not read_only)
        self.new_playlist_button.setIcon(icon("add", self._theme))
        self.new_playlist_button.setIconSize(QSize(self._theme.metrics.icon_md, self._theme.metrics.icon_md))
        self.new_playlist_button.setStyleSheet(
            f"QToolButton {{ min-height: 34px; text-align: left; padding: 0 10px; "
            f"border: 0; border-radius: {self._theme.metrics.radius_sm}px; "
            f"color: {self._theme.colors.secondary_text}; background: transparent; }}"
            f"QToolButton:hover {{ color: {self._theme.colors.primary_text}; "
            f"background: {self._theme.colors.hover_background}; }}"
        )

    @staticmethod
    def _apply_surface_background(widget: QWidget, background: str) -> None:
        palette = widget.palette()
        color = QColor(background)
        palette.setColor(QPalette.ColorRole.Window, color)
        palette.setColor(QPalette.ColorRole.Base, color)
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _create_playlist_from_ui(self) -> None:
        if self.adapter.playlist_adapter.read_only:
            return
        self.adapter.create_playlist()

    def _show_playlist_menu(self, playlist_id: str, global_position) -> None:
        if self.adapter.playlist_adapter.read_only:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("重命名歌单")
        delete_action = menu.addAction("删除歌单")
        selected = menu.exec(global_position)
        if selected is rename_action:
            playlist = next(
                (item for item in self.adapter.playlists() if item.id == playlist_id),
                None,
            )
            if playlist is not None:
                title, accepted = QInputDialog.getText(
                    self, "重命名歌单", "歌单名称", text=playlist.name
                )
                if accepted:
                    self.adapter.rename_playlist(playlist_id, title)
        elif selected is delete_action:
            self.adapter.delete_playlist(playlist_id)
        menu.deleteLater()
