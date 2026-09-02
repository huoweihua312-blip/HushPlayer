"""The intentionally small, lyrics-only ordinary page toolbar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

from app.ui_v2.theme.tokens import Theme


class CompactLyricsToolbar(QWidget):
    """No track identity and no playback controls: PlayerBar owns those."""

    translation_requested = Signal()
    immersive_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title_label = QLabel("歌词", self)
        self.translation_button = self._button("翻译", "显示或隐藏翻译", checkable=True)
        self.more_button = self._button("更多", "更多歌词选项")
        self.immersive_button = self._button("沉浸", "进入沉浸歌词")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        for button in (self.translation_button, self.more_button, self.immersive_button):
            layout.addWidget(button)
        self.translation_button.clicked.connect(self.translation_requested)
        self.immersive_button.clicked.connect(self.immersive_requested)
        self.more_menu = QMenu(self)
        self.more_menu.addAction("回到当前歌词")
        self.more_button.setMenu(self.more_menu)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setObjectName("compactLyricsToolbar")
        self.setFixedHeight(58)
        self.set_theme(theme)

    def _button(self, text: str, tooltip: str, *, checkable: bool = False) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumSize(32, 32)
        return button

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        style = (
            "QToolButton { border: 0; border-radius: 6px; padding: 5px 8px; background: transparent; "
            f"color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ background: {theme.colors.hover_background}; color: {theme.colors.primary_text}; }}"
            f"QToolButton:checked {{ color: {theme.colors.accent}; background: transparent; }}"
        )
        for button in (self.translation_button, self.more_button, self.immersive_button):
            button.setStyleSheet(style)

    def set_options(self, options: dict[str, object]) -> None:
        self.translation_button.setChecked(bool(options.get("translation", True)))

    def set_compact(self, compact: bool) -> None:
        self.setFixedHeight(52 if compact else 58)
        self.translation_button.setText("译" if compact else "翻译")
        self.immersive_button.setText("沉浸" if not compact else "沉浸")
