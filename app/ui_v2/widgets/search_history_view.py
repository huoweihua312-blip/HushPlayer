"""In-memory search-history list with click-to-search and deletion actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.search_history_item import SearchHistoryItem
from app.ui_v2.theme.tokens import Theme


class SearchHistoryView(QWidget):
    query_requested = Signal(str)
    remove_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title_label = QLabel("搜索历史", self)
        self.clear_button = QToolButton(self)
        self.clear_button.setText("清空")
        self.clear_button.clicked.connect(self.clear_requested)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content = QWidget(self.scroll_area)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.scroll_area.setWidget(self.content)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.scroll_area)
        self.set_history(())
        self.set_theme(theme)

    def set_history(self, items: tuple[SearchHistoryItem, ...]) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not items:
            empty = QLabel("暂无搜索历史", self.content)
            empty.setObjectName("historyEmpty")
            self.content_layout.addWidget(empty)
        for entry in items:
            row = QWidget(self.content)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            query = QToolButton(row)
            query.setText(entry.query)
            query.setToolTip(entry.query)
            query.clicked.connect(lambda checked=False, value=entry.query: self.query_requested.emit(value))
            remove = QToolButton(row)
            remove.setText("删除")
            remove.clicked.connect(lambda checked=False, value=entry.query: self.remove_requested.emit(value))
            row_layout.addWidget(query, 1)
            row_layout.addWidget(remove)
            self.content_layout.addWidget(row)
        self.content_layout.addStretch(1)
        self._refresh_rows()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.clear_button.setStyleSheet(self._button_style())
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for row_index in range(self.content_layout.count()):
            row = self.content_layout.itemAt(row_index).widget()
            if row is None:
                continue
            if isinstance(row, QLabel):
                row.setStyleSheet(f"color: {self._theme.colors.subtle_text};")
                continue
            for button in row.findChildren(QToolButton):
                button.setStyleSheet(self._button_style())

    def _button_style(self) -> str:
        return (
            f"QToolButton {{ min-height: {self._theme.metrics.control_height}px; text-align: left; padding: 0 {self._theme.metrics.spacing_sm}px; "
            f"border: 0; border-radius: {self._theme.metrics.radius_sm}px; color: {self._theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {self._theme.colors.primary_text}; background: {self._theme.colors.hover_background}; }}"
        )
