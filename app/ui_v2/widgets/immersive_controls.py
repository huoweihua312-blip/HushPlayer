"""The compact left-column playback controls used only by immersive lyrics."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import format_duration
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


def _rgba(value: str, alpha: int) -> str:
    color = QColor(value)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, alpha))})"


class ImmersiveControls(QWidget):
    """A restrained control stack that belongs below immersive track identity."""

    interaction_started = Signal()
    interaction_finished = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._adapter: PlaybackAdapter | None = None
        self._dragging_progress = False
        self.back_button = self._button("lyrics", "返回普通歌词")
        self.back_button.setObjectName("immersiveReturnButton")
        self.previous_button = self._button("previous", "上一首")
        self.play_button = self._button("play", "播放")
        self.play_button.setObjectName("immersivePlayButton")
        self.next_button = self._button("next", "下一首")
        self.elapsed_label = QLabel("0:00", self)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.progress_slider.setObjectName("immersiveProgressSlider")
        self.progress_slider.setRange(0, 0)
        self.duration_label = QLabel("--:--", self)
        self.volume_button = self._button("volume", "音量")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setObjectName("immersiveVolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.more_button = self._button("settings", "设置")
        self.time_row = QWidget(self)
        self.transport_row = QWidget(self)
        self.secondary_row = QWidget(self)
        self._time_layout = QHBoxLayout(self.time_row)
        self._time_layout.setContentsMargins(0, 0, 0, 0)
        self._time_layout.setSpacing(8)
        self._time_layout.addWidget(self.elapsed_label)
        self._time_layout.addWidget(self.progress_slider, 1)
        self._time_layout.addWidget(self.duration_label)
        self._transport_layout = QHBoxLayout(self.transport_row)
        self._transport_layout.setContentsMargins(0, 0, 0, 0)
        self._transport_layout.setSpacing(10)
        self._transport_layout.addStretch(1)
        self._transport_layout.addWidget(self.previous_button)
        self._transport_layout.addWidget(self.play_button)
        self._transport_layout.addWidget(self.next_button)
        self._transport_layout.addStretch(1)
        self._secondary_layout = QHBoxLayout(self.secondary_row)
        self._secondary_layout.setContentsMargins(0, 0, 0, 0)
        self._secondary_layout.setSpacing(6)
        self._secondary_layout.addWidget(self.volume_button)
        self._secondary_layout.addWidget(self.volume_slider, 1)
        self._secondary_layout.addStretch(1)
        self._secondary_layout.addWidget(self.back_button)
        self._secondary_layout.addWidget(self.more_button)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._layout.addWidget(self.time_row)
        self._layout.addWidget(self.transport_row)
        self._layout.addWidget(self.secondary_row)
        self.volume_slider.setFixedWidth(76)
        self.setObjectName("immersiveControls")
        self.setMinimumHeight(126)
        self.setAutoFillBackground(False)
        for widget in (self.progress_slider, self.volume_slider):
            widget.installEventFilter(self)
        self.set_theme(theme)

    def _button(self, name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        if name:
            button.setIcon(icon(name, self._theme))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumSize(34, 34)
        return button

    def bind_playback(self, adapter: PlaybackAdapter) -> None:
        if self._adapter is adapter:
            return
        self._adapter = adapter
        self.previous_button.clicked.connect(adapter.play_previous)
        self.play_button.clicked.connect(adapter.toggle_playback)
        self.next_button.clicked.connect(adapter.play_next)
        self.progress_slider.sliderPressed.connect(self._begin_progress)
        self.progress_slider.sliderReleased.connect(self._commit_progress)
        self.volume_slider.valueChanged.connect(adapter.set_volume)
        adapter.track_changed.connect(self._on_track_changed)
        adapter.playing_changed.connect(self._on_playing_changed)
        adapter.position_changed.connect(self._on_position_changed)
        adapter.duration_changed.connect(self._on_duration_changed)
        adapter.volume_changed.connect(self._on_volume_changed)
        self._on_track_changed(adapter.state.current_track)
        self._on_playing_changed(adapter.state.is_playing)
        self._on_position_changed(adapter.state.position_ms)
        self._on_volume_changed(adapter.state.volume)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        subtle = (
            "QToolButton { min-width: 34px; min-height: 34px; border: 0; border-radius: 17px; padding: 0; "
            f"background: transparent; color: {_rgba(colors.primary_text, 228)}; }}"
            f"QToolButton:hover {{ background: {colors.hover_background}; color: {colors.primary_text}; }}"
        )
        for button in (self.back_button, self.previous_button, self.next_button, self.volume_button, self.more_button):
            button.setStyleSheet(subtle)
        self.play_button.setStyleSheet(
            "QToolButton { min-width: 36px; min-height: 36px; border: 0; border-radius: 18px; padding: 0; "
            f"background: {colors.accent}; color: {colors.content_background}; }}"
            f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
        )
        self.back_button.setIcon(icon("lyrics", theme))
        self.previous_button.setIcon(icon("previous", theme))
        self.next_button.setIcon(icon("next", theme))
        self.volume_button.setIcon(icon("volume", theme))
        self.more_button.setIcon(icon("settings", theme))
        self._on_playing_changed(self._adapter.state.is_playing if self._adapter else False)
        for label in (self.elapsed_label, self.duration_label):
            label.setStyleSheet(f"background: transparent; color: {_rgba(colors.primary_text, 224)}; font-size: {theme.fonts.caption}px;")
        for slider in (self.progress_slider, self.volume_slider):
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: 3px; border: 0; border-radius: 1px; "
                f"background: {_rgba(colors.primary_text, 112)}; }}"
                f"QSlider::sub-page:horizontal {{ border-radius: 1px; background: {colors.accent}; }}"
                f"QSlider::handle:horizontal {{ width: 10px; margin: -4px 0; border: 0; border-radius: 5px; background: {_rgba(colors.primary_text, 238)}; }}"
            )

    def set_compact(self, compact: bool) -> None:
        self.volume_slider.setVisible(not compact)
        self._layout.setSpacing(8 if compact else 10)
        self._time_layout.setSpacing(6 if compact else 8)
        self.volume_slider.setFixedWidth(60 if compact else 76)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched in (self.progress_slider, self.volume_slider):
            if event.type() == QEvent.Type.MouseButtonPress:
                self.interaction_started.emit()
            elif event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.Leave):
                self.interaction_finished.emit()
        return super().eventFilter(watched, event)

    def _on_track_changed(self, track) -> None:
        duration = track.duration_ms if track is not None else None
        self.progress_slider.setRange(0, int(duration or 0))
        self.duration_label.setText(format_duration(duration))
        enabled = track is not None
        for control in (self.previous_button, self.play_button, self.next_button, self.progress_slider):
            control.setEnabled(enabled)

    def _on_playing_changed(self, playing: bool) -> None:
        self.play_button.setIcon(icon("pause" if playing else "play", self._theme, "selected"))
        self.play_button.setToolTip("暂停" if playing else "播放")

    def _on_position_changed(self, position: int) -> None:
        if not self._dragging_progress:
            self.progress_slider.setValue(int(position))
        self.elapsed_label.setText(format_duration(int(position)))

    def _on_duration_changed(self, duration: int | None) -> None:
        self.progress_slider.setRange(0, int(duration or 0))
        self.duration_label.setText(format_duration(duration))

    def _on_volume_changed(self, value: int) -> None:
        previous = self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(value))
        self.volume_slider.blockSignals(previous)

    def _begin_progress(self) -> None:
        self._dragging_progress = True
        self.interaction_started.emit()

    def _commit_progress(self) -> None:
        self._dragging_progress = False
        if self._adapter is not None:
            self._adapter.seek(self.progress_slider.value())
        self.interaction_finished.emit()
