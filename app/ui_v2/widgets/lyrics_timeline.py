"""Compact time display and seek control shared by the lyrics page."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui_v2.models.track import format_duration
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import FlatSlider


class LyricsTimeline(QWidget):
    seek_requested = Signal(int)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.current_label = QLabel("0:00", self)
        self.total_label = QLabel("--:--", self)
        self.slider = FlatSlider(Qt.Orientation.Horizontal, self)
        self.slider.sliderReleased.connect(lambda: self.seek_requested.emit(self.slider.value()))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.current_label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.total_label)
        self.set_theme(theme)

    def set_duration(self, duration_ms: int | None) -> None:
        duration = max(0, int(duration_ms or 0))
        self.slider.setRange(0, duration)
        self.slider.setEnabled(duration > 0)
        self.total_label.setText(format_duration(duration_ms))

    def set_position(self, position_ms: int) -> None:
        blocker = QSignalBlocker(self.slider)
        self.slider.setValue(max(0, int(position_ms)))
        del blocker
        self.current_label.setText(format_duration(position_ms))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.slider.set_handle_radius(5.0)
        self.slider.set_visual_colors(
            theme.colors.border_strong,
            theme.colors.accent,
            theme.colors.primary_text,
            disabled_color=theme.colors.disabled_text,
            focus_color=theme.colors.focus_ring,
        )
        self.setStyleSheet(
            f"QLabel {{ color: {theme.colors.secondary_text}; font-size: {theme.fonts.caption}px; }}"
            "QSlider { background: transparent; border: 0; padding: 0; }"
            "QSlider::groove:horizontal { height: 4px; border: 0; border-radius: 2px; background: transparent; }"
            f"QSlider::sub-page:horizontal {{ background: {theme.colors.accent}; border-radius: 2px; }}"
            "QSlider::add-page:horizontal { background: transparent; border: 0; }"
            f"QSlider::handle:horizontal {{ width: 10px; margin: -3px 0; border-radius: 5px; background: {theme.colors.primary_text}; }}"
        )
