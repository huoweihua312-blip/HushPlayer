"""The compact left-column playback controls used only by immersive lyrics."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.playback_state import RepeatMode
from app.ui_v2.models.track import format_duration
from app.ui_v2.theme.icons import fluent_icon, icon
from app.ui_v2.theme.tokens import Theme


def _rgba(value: str, alpha: int) -> str:
    color = QColor(value)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, alpha))})"


class ImmersiveControls(QWidget):
    """A restrained control stack that belongs below immersive track identity."""

    interaction_started = Signal()
    interaction_finished = Signal()
    queue_requested = Signal()
    lyrics_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._adapter: PlaybackAdapter | None = None
        self._dragging_progress = False
        self.shuffle_button = self._button("shuffle", "随机播放")
        self.previous_button = self._button("previous", "上一首")
        self.play_button = self._button("play", "播放")
        self.play_button.setObjectName("immersivePlayButton")
        self.play_button.setFixedSize(58, 58)
        self.play_button.setIconSize(QSize(24, 24))
        self.next_button = self._button("next", "下一首")
        self.repeat_button = self._button("repeat", "循环模式")
        self.elapsed_label = QLabel("0:00", self)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.progress_slider.setObjectName("immersiveProgressSlider")
        self.progress_slider.setRange(0, 0)
        self.duration_label = QLabel("--:--", self)
        self.volume_button = self._button("volume", "音量")
        self.queue_button = self._button("queue", "播放队列")
        self.lyrics_button = self._button("lyrics", "歌词")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setObjectName("immersiveVolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.more_button = self._button("more", "更多设置")
        self.time_row = QWidget(self)
        self.transport_row = QWidget(self)
        self.secondary_row = QWidget(self)
        self.utility_group = QWidget(self.secondary_row)
        self.utility_group.setObjectName("immersiveUtilityGroup")
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
        self._transport_layout.addWidget(self.shuffle_button)
        self._transport_layout.addWidget(self.previous_button)
        self._transport_layout.addWidget(self.play_button)
        self._transport_layout.addWidget(self.next_button)
        self._transport_layout.addWidget(self.repeat_button)
        self._transport_layout.addStretch(1)
        self._secondary_layout = QHBoxLayout(self.secondary_row)
        self._secondary_layout.setContentsMargins(0, 0, 0, 0)
        self._secondary_layout.setSpacing(0)
        self._secondary_layout.addStretch(1)
        self._secondary_layout.addWidget(self.utility_group)
        self._secondary_layout.addStretch(1)
        utility_layout = QHBoxLayout(self.utility_group)
        utility_layout.setContentsMargins(0, 0, 0, 0)
        utility_layout.setSpacing(6)
        utility_layout.addWidget(self.queue_button)
        utility_layout.addWidget(self.lyrics_button)
        utility_layout.addWidget(self.volume_button)
        utility_layout.addWidget(self.volume_slider)
        utility_layout.addWidget(self.more_button)
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
        self.shuffle_button.clicked.connect(adapter.toggle_shuffle)
        self.repeat_button.clicked.connect(adapter.cycle_repeat_mode)
        self.queue_button.clicked.connect(self.queue_requested)
        self.lyrics_button.clicked.connect(self.lyrics_requested)
        self.progress_slider.sliderPressed.connect(self._begin_progress)
        self.progress_slider.sliderReleased.connect(self._commit_progress)
        self.volume_slider.valueChanged.connect(adapter.set_volume)
        self.volume_button.clicked.connect(self._toggle_mute)
        adapter.track_changed.connect(self._on_track_changed)
        adapter.playing_changed.connect(self._on_playing_changed)
        adapter.position_changed.connect(self._on_position_changed)
        adapter.duration_changed.connect(self._on_duration_changed)
        adapter.volume_changed.connect(self._on_volume_changed)
        adapter.muted_changed.connect(self._on_muted_changed)
        adapter.shuffle_changed.connect(self._on_shuffle_changed)
        adapter.repeat_mode_changed.connect(self._on_repeat_changed)
        self._on_track_changed(adapter.state.current_track)
        self._on_playing_changed(adapter.state.is_playing)
        self._on_position_changed(adapter.state.position_ms)
        self._on_volume_changed(adapter.state.volume)
        self._on_muted_changed(adapter.state.is_muted)
        self._on_shuffle_changed(adapter.state.shuffle_enabled)
        self._on_repeat_changed(adapter.state.repeat_mode)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        subtle = (
            "QToolButton { min-width: 34px; min-height: 34px; border: 0; border-radius: 17px; padding: 0; "
            f"background: transparent; color: {_rgba(colors.primary_text, 228)}; }}"
            f"QToolButton:hover {{ background: {colors.hover_background}; color: {colors.primary_text}; }}"
        )
        for button in (self.shuffle_button, self.previous_button, self.next_button, self.repeat_button, self.queue_button, self.lyrics_button, self.volume_button, self.more_button):
            button.setStyleSheet(subtle)
        self.play_button.setStyleSheet(
            "QToolButton#immersivePlayButton { min-width: 58px; min-height: 58px; "
            "max-width: 58px; max-height: 58px; border: 0; border-radius: 29px; padding: 0; "
            "background: #F4F4F6; }"
            "QToolButton#immersivePlayButton:hover { background: #FFFFFF; }"
            "QToolButton#immersivePlayButton:pressed { background: #E7E7EB; }"
            f"QToolButton#immersivePlayButton:disabled {{ background: {colors.surface_pressed}; }}"
        )
        self.previous_button.setIcon(icon("previous", theme))
        self.next_button.setIcon(icon("next", theme))
        self._on_muted_changed(self._adapter.state.is_muted if self._adapter else False)
        self.more_button.setIcon(fluent_icon("more", theme, size=18))
        self.shuffle_button.setIcon(fluent_icon("shuffle", theme, "selected" if self._adapter and self._adapter.state.shuffle_enabled else "normal", size=18))
        self.repeat_button.setIcon(fluent_icon("repeat", theme, "selected" if self._adapter and self._adapter.state.repeat_mode != RepeatMode.OFF else "normal", size=18))
        self.queue_button.setIcon(fluent_icon("queue", theme, size=18))
        self.lyrics_button.setIcon(fluent_icon("lyrics", theme, size=18))
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
        self.shuffle_button.setEnabled(enabled)
        self.repeat_button.setEnabled(enabled)
        self.queue_button.setEnabled(True)
        self._set_play_icon(self._adapter.state.is_playing if self._adapter else False)

    def _on_playing_changed(self, playing: bool) -> None:
        self._set_play_icon(playing)
        self.play_button.setToolTip("暂停" if playing else "播放")

    def _set_play_icon(self, playing: bool) -> None:
        """Keep the sole primary control high-contrast in every state."""

        if not self.play_button.isEnabled():
            state = "disabled"
        elif self._theme.mode == "dark":
            state = "inverse"
        else:
            state = "normal"
        self.play_button.setIcon(
            fluent_icon("pause" if playing else "play", self._theme, state, size=24)
        )

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
        self._refresh_volume_icon()

    def _on_muted_changed(self, muted: bool) -> None:
        self._refresh_volume_icon(bool(muted))

    def _refresh_volume_icon(self, muted: bool | None = None) -> None:
        if muted is None:
            muted = self._adapter.state.is_muted if self._adapter is not None else False
        is_muted = bool(muted) or self.volume_slider.value() == 0
        self.volume_button.setIcon(icon("volume_mute" if is_muted else "volume", self._theme))
        action = "取消静音" if is_muted else "静音"
        self.volume_button.setToolTip(action)
        self.volume_button.setAccessibleName(action)

    def _toggle_mute(self) -> None:
        if self._adapter is None:
            return
        self._adapter.set_muted(not self._adapter.state.is_muted)

    def _on_shuffle_changed(self, enabled: bool) -> None:
        if self._adapter is not None:
            self.shuffle_button.setIcon(fluent_icon("shuffle", self._theme, "selected" if enabled else "normal", size=18))

    def _on_repeat_changed(self, mode: RepeatMode) -> None:
        if self._adapter is not None:
            name = "repeat_one" if mode == RepeatMode.ONE else "repeat"
            self.repeat_button.setIcon(fluent_icon(name, self._theme, "selected" if mode != RepeatMode.OFF else "normal", size=18))

    def _begin_progress(self) -> None:
        self._dragging_progress = True
        self.interaction_started.emit()

    def _commit_progress(self) -> None:
        self._dragging_progress = False
        if self._adapter is not None:
            self._adapter.seek(self.progress_slider.value())
        self.interaction_finished.emit()
