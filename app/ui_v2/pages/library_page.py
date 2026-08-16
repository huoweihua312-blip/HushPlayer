"""First-stage V2 library page, isolated from production business code."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QStackedLayout, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.empty_state import EmptyState
from app.ui_v2.widgets.page_header import PageHeader
from app.ui_v2.widgets.search_box import SearchBox
from app.ui_v2.widgets.track_table import TrackTable


class LibraryPage(QWidget):
    """A data-only V2 library surface with explicit preview states."""

    theme_changed = Signal(str)

    def __init__(
        self,
        adapter: LibraryAdapter,
        theme: Theme | None = None,
        parent: QWidget | None = None,
        *,
        include_page_search: bool = True,
        include_preview_controls: bool = True,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme or get_theme("dark")
        self.current_view_state = "content"
        self._content_safe_bottom = 0
        self._developer_mode = os.environ.get("HUSHPLAYER_UI_V2_DEVELOPER", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.setObjectName("libraryPage")
        self.header = PageHeader("全部歌曲", self)
        self.header.set_context("资料库")
        self.header.title_label.setMinimumWidth(76)
        self.header.count_label.setMinimumWidth(64)
        self.search_box = None
        self.theme_toggle = None
        self.state_toggle = None
        self._state_menu = None
        if include_page_search:
            self.search_box = SearchBox(self)
            self.search_box.setMinimumWidth(220)
            self.header.trailing_layout.addWidget(self.search_box)
        if include_preview_controls:
            self.theme_toggle = QToolButton(self)
            self.theme_toggle.setObjectName("themeToggle")
            self.theme_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.theme_toggle.clicked.connect(self._toggle_theme)
            self.header.trailing_layout.addWidget(self.theme_toggle)
            self.state_toggle = QToolButton(self)
            self.state_toggle.setObjectName("stateToggle")
            self.state_toggle.setText("状态")
            self.state_toggle.setToolTip("预览页面状态")
            self.state_toggle.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self._state_menu = self._build_state_menu()
            self.state_toggle.setMenu(self._state_menu)
            if self._developer_mode:
                self.header.trailing_layout.addWidget(self.state_toggle)
        self.track_table = TrackTable(adapter, self._theme, self)
        self.empty_state = EmptyState(self)
        self.view_host = QWidget(self)
        self.view_host.setObjectName("libraryWorkSurface")
        self.view_stack = QStackedLayout(self.view_host)
        self.view_stack.setContentsMargins(8, 8, 8, 8)
        self.view_stack.addWidget(self.track_table)
        self.view_stack.addWidget(self.empty_state)
        layout = QVBoxLayout(self)
        m = self._theme.metrics
        layout.setContentsMargins(m.page_margin, m.spacing_lg, m.page_margin, m.page_margin)
        layout.setSpacing(m.spacing_md)
        layout.addWidget(self.header)
        layout.addWidget(self.view_host, 1)
        if self.search_box is not None:
            self.search_box.text_changed.connect(self.adapter.set_query)
        self.adapter.tracks_reset.connect(self._on_tracks_reset)
        self.set_theme(self._theme)
        self._apply_work_surface_margins()
        self._on_tracks_reset(self.adapter.tracks())

    def set_content_safe_bottom(self, height: int) -> None:
        """Reserve the shared bottom-safe area above the global PlayerBar."""

        self._content_safe_bottom = max(0, int(height))
        self._apply_work_surface_margins()

    def _apply_work_surface_margins(self) -> None:
        inset = self._theme.metrics.spacing_sm
        self.view_stack.setContentsMargins(
            inset,
            inset,
            inset,
            self._content_safe_bottom + inset,
        )

    def set_responsive_reference_width(self, width: int) -> None:
        """Resize the table without replacing its model or adapter."""

        reference = int(width)
        self.track_table.set_responsive_reference_width(reference)
        narrow = reference < 950
        if self.search_box is not None:
            self.search_box.setMinimumWidth(180 if narrow else 220)
            self.search_box.setMaximumWidth(220 if narrow else 320)

    @property
    def theme(self) -> Theme:
        return self._theme

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.header.set_theme(theme)
        if self.search_box is not None:
            self.search_box.set_theme(theme)
        self.empty_state.set_theme(theme)
        self.track_table.set_theme(theme)
        if self.theme_toggle is not None:
            self.theme_toggle.setText("浅色" if theme.mode == "dark" else "深色")
            self.theme_toggle.setToolTip(
                "切换到浅色主题" if theme.mode == "dark" else "切换到深色主题"
            )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_preview_control_layout()

    def set_view_state(self, state: str, detail: str = "") -> None:
        if state not in {"content", "empty", "loading", "error"}:
            state = "empty"
        if state == "content" and not self.adapter.tracks():
            state = "empty"
        self.current_view_state = state
        if state == "content":
            self.view_stack.setCurrentWidget(self.track_table)
            return
        self.empty_state.set_state(state, detail)
        self.view_stack.setCurrentWidget(self.empty_state)

    def _on_tracks_reset(self, tracks) -> None:
        self.header.set_count(len(tracks))
        if self.current_view_state == "content" and not tracks:
            self.set_view_state("empty")
        elif self.current_view_state == "empty" and tracks:
            self.set_view_state("content")

    def _toggle_theme(self) -> None:
        mode = "light" if self._theme.mode == "dark" else "dark"
        self.theme_changed.emit(mode)

    def _build_state_menu(self) -> QMenu:
        menu = QMenu(self)
        theme_action = menu.addAction("切换主题")
        theme_action.triggered.connect(self._toggle_theme)
        menu.addSeparator()
        actions = (
            ("显示歌曲列表", "content"),
            ("显示空状态", "empty"),
            ("显示加载状态", "loading"),
            ("显示错误状态", "error"),
        )
        for text, state in actions:
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, value=state: self.set_view_state(value))
        return menu

    def _apply_preview_control_layout(self) -> None:
        narrow = self.width() < 980
        if self.search_box is not None:
            self.search_box.setMinimumWidth(180 if narrow else 220)
            self.search_box.setMaximumWidth(220 if narrow else 320)
        if self.theme_toggle is not None:
            self.theme_toggle.setVisible(not narrow)
        if self.state_toggle is not None:
            self.state_toggle.setVisible(self._developer_mode)
        if self.state_toggle is not None and self._developer_mode:
            self.state_toggle.setText("开发")
            self.state_toggle.setToolTip("切换主题和预览页面状态")
