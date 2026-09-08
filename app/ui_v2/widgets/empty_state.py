"""Formal empty, loading, and error presentation used by the V2 library page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class EmptyState(QWidget):
    action_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme: Theme | None = None
        self._state = "empty"
        self._detail = ""
        self._search_query = ""
        self._action_text = ""
        self.empty_icon_name = "playlist"
        self.icon_label = QLabel(self)
        self.title_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.action_button = QToolButton(self)
        self.action_button.setVisible(False)
        self.action_button.clicked.connect(self.action_requested)
        for label in (self.icon_label, self.title_label, self.detail_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        self.set_state("empty")

    def set_state(self, state: str, detail: str = "") -> None:
        self._state = state
        self._detail = detail
        self._refresh_content()

    def set_search_query(self, query: str) -> None:
        self._search_query = str(query or "").strip()
        self._refresh_content()

    def _refresh_content(self) -> None:
        content = {
            "empty": ("没有可显示的歌曲", "尝试调整搜索内容或添加音乐文件。", "playlist"),
            "loading": ("正在加载歌曲", "正在准备歌曲列表。", "library"),
            "error": ("无法显示歌曲", "请稍后重试。", "missing"),
        }
        title, default_detail, icon_name = content.get(self._state, content["empty"])
        is_search_empty = self._state == "empty" and bool(self._search_query)
        if is_search_empty:
            title, default_detail, icon_name = (
                "未找到匹配歌曲", "试试其他歌曲名、歌手或专辑，也可以清空搜索查看当前列表。", "search"
            )
        self.empty_icon_name = icon_name
        self.title_label.setText(title)
        self.detail_label.setText(default_detail if is_search_empty else self._detail or default_detail)
        action = "清空搜索" if is_search_empty else self._action_text
        self.action_button.setText(action)
        self.action_button.setToolTip(action)
        self.action_button.setVisible(bool(action))
        if self._theme is not None:
            self.icon_label.setPixmap(icon(icon_name, self._theme, "normal").pixmap(32, 32))

    def set_action(self, text: str = "") -> None:
        self._action_text = text
        self._refresh_content()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.icon_label.setPixmap(icon(self.empty_icon_name, theme, "normal").pixmap(32, 32))
        self.icon_label.setObjectName("emptyStateIcon")
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )
        self.action_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.selected_background}; "
            f"color: {theme.colors.primary_text}; }}"
            f"QToolButton:hover {{ background: {theme.colors.hover_background}; }}"
        )
