"""Track context and display controls for the ordinary lyrics page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme


class LyricsHeader(QFrame):
    translation_requested = Signal()
    romanization_requested = Signal()
    font_scale_requested = Signal(float)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.cover_label = QLabel("封面", self)
        self.title_label = QLabel("未选择歌曲", self)
        self.artist_label = QLabel("请选择一首歌曲开始播放", self)
        self.source_label = QLabel("歌词来源: --", self)
        self.translation_button = QToolButton(self)
        self.translation_button.setText("翻译")
        self.romanization_button = QToolButton(self)
        self.romanization_button.setText("罗马音")
        self.smaller_button = QToolButton(self)
        self.smaller_button.setText("A-")
        self.larger_button = QToolButton(self)
        self.larger_button.setText("A+")
        self.translation_button.clicked.connect(self.translation_requested)
        self.romanization_button.clicked.connect(self.romanization_requested)
        self.smaller_button.clicked.connect(lambda: self.font_scale_requested.emit(-0.1))
        self.larger_button.clicked.connect(lambda: self.font_scale_requested.emit(0.1))
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)
        text.addWidget(self.title_label)
        text.addWidget(self.artist_label)
        text.addWidget(self.source_label)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        for button in (self.translation_button, self.romanization_button, self.smaller_button, self.larger_button):
            controls.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self.cover_label)
        layout.addLayout(text)
        layout.addLayout(controls)
        self.set_theme(theme)

    def set_track(self, track: Track | None, document: LyricsDocument | None) -> None:
        self.title_label.setText(track.title if track else "未选择歌曲")
        self.artist_label.setText(track.artist if track else "请选择一首歌曲开始播放")
        source = document.source_type if document is not None else "--"
        self.source_label.setText(f"歌词来源: {source}")

    def set_options(self, options: dict[str, object]) -> None:
        self.translation_button.setChecked(bool(options.get("translation")))
        self.romanization_button.setChecked(bool(options.get("romanization")))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"QFrame {{ background: {theme.colors.elevated_background}; border: 1px solid {theme.colors.border}; "
            f"border-radius: {theme.metrics.radius_sm}px; }}"
        )
        self.cover_label.setFixedHeight(140)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet(f"background: {theme.colors.selected_background}; color: {theme.colors.subtle_text};")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.artist_label.setStyleSheet(f"color: {theme.colors.secondary_text};")
        self.source_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {theme.colors.subtle_text};")
        for button in (self.translation_button, self.romanization_button, self.smaller_button, self.larger_button):
            button.setCheckable(button in (self.translation_button, self.romanization_button))
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; border: 0; "
                f"border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:checked, QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
            )
