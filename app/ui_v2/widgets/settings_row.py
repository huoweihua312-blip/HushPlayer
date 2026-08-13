"""Consistently aligned setting label, description, and control row."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QBoxLayout, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import Theme


class SettingsRow(QFrame):
    """One setting without turning every preference into a heavy card."""

    def __init__(self, path: str, title: str, description: str, control: QWidget, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self._theme = theme
        self._highlighted = False
        self._compact = False
        self.setProperty("settingPath", path)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("settingsRowTitle")
        self.description_label = QLabel(description, self)
        self.description_label.setObjectName("settingsRowDescription")
        self.description_label.setWordWrap(True)
        self.control = control
        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(2)
        labels.addWidget(self.title_label)
        labels.addWidget(self.description_label)
        self._labels_layout = labels
        self._row_layout = QHBoxLayout(self)
        self._row_layout.setContentsMargins(0, 10, 0, 10)
        self._row_layout.setSpacing(18)
        self._row_layout.addLayout(labels, 1)
        self._row_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight)
        if not control.accessibleName():
            control.setAccessibleName(title)
        if not control.accessibleDescription():
            control.setAccessibleDescription(description)
        self.set_theme(theme)

    def flash_highlight(self) -> None:
        self._highlighted = True
        self.set_theme(self._theme)
        QTimer.singleShot(1100, self._clear_highlight)

    def _clear_highlight(self) -> None:
        self._highlighted = False
        self.set_theme(self._theme)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self._row_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        self._row_layout.setSpacing(8 if compact else 18)
        self._row_layout.setContentsMargins(0, 8 if compact else 10, 0, 8 if compact else 10)
        self._row_layout.setAlignment(self.control, Qt.AlignmentFlag.AlignLeft if compact else Qt.AlignmentFlag.AlignRight)
        self.updateGeometry()

    def set_status(self, text: str) -> None:
        self.description_label.setToolTip(str(text or ""))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        background = theme.colors.selected_background if self._highlighted else "transparent"
        self.setStyleSheet(f"SettingsRow {{ background: {background}; border-bottom: 1px solid {theme.colors.border}; }}")
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.body}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.description_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; font-weight: 500; color: {theme.colors.secondary_text};")


SettingRow = SettingsRow
