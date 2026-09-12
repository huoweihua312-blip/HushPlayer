"""Primary query control for the mock online-search page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.line_edit import apply_optical_vertical_center
from app.ui_v2.widgets.online_presentation import style_action


class OnlineSearchBar(QWidget):
    search_requested = Signal()
    query_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.line_edit = QLineEdit(self)
        apply_optical_vertical_center(self.line_edit)
        self.line_edit.setPlaceholderText("搜索歌曲、歌手或专辑")
        self.line_edit.setMaxLength(120)
        self.search_glyph = self.line_edit.addAction(icon("search", theme), QLineEdit.ActionPosition.LeadingPosition)
        self.line_edit.textChanged.connect(self.query_changed)
        self.line_edit.returnPressed.connect(self.search_requested)
        self.search_button = QToolButton(self)
        self.search_button.setText("搜索")
        self.search_button.clicked.connect(self.search_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        self.setFixedHeight(55)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.search_button)
        self.set_theme(theme)

    def set_text(self, value: str) -> None:
        self.line_edit.setText(value)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.search_glyph.setIcon(icon("search", theme))
        self.line_edit.setStyleSheet(
            f"QLineEdit {{ min-height: 51px; padding: 0 4px; font-size: 21px; "
            f"border: 0; border-bottom: 1px solid {theme.colors.divider}; border-radius: 0; "
            f"background: transparent; color: {theme.colors.primary_text}; }}"
            f"QLineEdit:focus {{ border-bottom-color: {theme.colors.focus_ring}; }}"
        )
        self.search_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.search_button.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
        style_action(self.search_button, theme, primary=True)
