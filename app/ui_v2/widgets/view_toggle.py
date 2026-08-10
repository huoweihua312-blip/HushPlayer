"""Small grid/list preference control for entity collection pages."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from app.ui_v2.theme.tokens import Theme


class ViewToggle(QWidget):
    mode_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._mode = "grid"
        self.grid_button = QToolButton(self)
        self.grid_button.setText("网格")
        self.grid_button.clicked.connect(lambda: self.set_mode("grid"))
        self.list_button = QToolButton(self)
        self.list_button.setText("紧凑")
        self.list_button.clicked.connect(lambda: self.set_mode("list"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.grid_button)
        layout.addWidget(self.list_button)
        self.set_theme(theme)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        normalized = "list" if mode == "list" else "grid"
        if normalized == self._mode:
            return
        self._mode = normalized
        self._refresh()
        self.mode_changed.emit(normalized)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh()

    def _refresh(self) -> None:
        for mode, button in (("grid", self.grid_button), ("list", self.list_button)):
            selected = mode == self._mode
            button.setStyleSheet(
                f"QToolButton {{ min-height: {self._theme.metrics.control_height}px; padding: 0 {self._theme.metrics.spacing_sm}px; "
                f"border: 0; border-radius: {self._theme.metrics.radius_sm}px; "
                f"background: {self._theme.colors.selected_background if selected else 'transparent'}; "
                f"color: {self._theme.colors.primary_text if selected else self._theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ background: {self._theme.colors.hover_background}; }}"
            )
