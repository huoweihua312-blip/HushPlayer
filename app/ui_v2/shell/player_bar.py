"""Mock-only PlayerBar that renders state supplied by PlaybackAdapter."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.playback_state import RepeatMode
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.playback_button import PlaybackButton


class PlayerBar(QFrame):
    """A stable-height transport surface driven by the V2 playback adapter."""

    mock_action_requested = Signal(str)

    def __init__(
        self,
        adapter: PlaybackAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self._seeking = False
        self._compact = False
        self._read_only = False
        self.setObjectName("playerBar")
        self.setMinimumHeight(116)
        self.setMaximumHeight(116)
        self._build_layout()
        self._connect_adapter()
        self.set_theme(theme)
        self._apply_state()

    @property
    def compact(self) -> bool:
        return self._compact

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#playerBar {{ background: {colors.player_background}; "
            f"border-top: 1px solid {colors.border}; }}"
            f"QLabel#playerTitle {{ color: {colors.primary_text}; font-size: {theme.fonts.body}px; font-weight: 600; }}"
            f"QLabel#playerArtist, QLabel#playerTime, QLabel#volumeLabel {{ color: {colors.secondary_text}; font-size: {theme.fonts.caption}px; }}"
            f"QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {colors.border_strong}; }}"
            f"QSlider::sub-page:horizontal {{ border-radius: 2px; background: {colors.accent}; }}"
            f"QSlider::handle:horizontal {{ width: 12px; margin: -4px 0; border-radius: 6px; background: {colors.primary_text}; }}"
        )
        self.artwork.set_theme(theme)
        for button in self._buttons:
            button.set_theme(theme)
        self._refresh_repeat_tooltip()

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.shuffle_button.setVisible(not compact)
        self.repeat_button.setVisible(not compact)
        self.lyrics_button.setVisible(not compact)
        self.queue_button.setVisible(not compact)
        self.volume_label.setVisible(not compact)
        self.artist_label.setVisible(not compact)
        self.left_section.setMinimumWidth(188 if compact else 250)
        self.left_section.setMaximumWidth(250 if compact else 320)
        self.right_section.setMinimumWidth(124 if compact else 214)
        self.right_section.setMaximumWidth(160 if compact else 260)

    def set_read_only(self, read_only: bool) -> None:
        """Hide persistence-affecting actions for a read-only library snapshot."""

        self._read_only = bool(read_only)
        self.favorite_button.setVisible(not self._read_only)
        self.favorite_button.setEnabled(not self._read_only)

    def _build_layout(self) -> None:
        self.artwork = ArtworkThumbnail(self._theme, self)
        self.title_label = ElidedLabel(self)
        self.title_label.setObjectName("playerTitle")
        self.artist_label = ElidedLabel(self)
        self.artist_label.setObjectName("playerArtist")
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.artist_label)
        self.favorite_button = PlaybackButton("favorite", "收藏", self._theme, self)
        self.favorite_button.clicked.connect(self.adapter.toggle_favorite)
        self.left_section = QWidget(self)
        left_layout = QHBoxLayout(self.left_section)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(self.artwork)
        left_layout.addLayout(title_layout, 1)
        left_layout.addWidget(self.favorite_button)
        self.left_section.setMinimumWidth(250)
        self.left_section.setMaximumWidth(320)

        self.shuffle_button = PlaybackButton("shuffle", "随机播放", self._theme, self)
        self.previous_button = PlaybackButton("previous", "上一首", self._theme, self)
        self.play_button = PlaybackButton("play", "播放", self._theme, self, primary=True)
        self.next_button = PlaybackButton("next", "下一首", self._theme, self)
        self.repeat_button = PlaybackButton("repeat", "循环模式", self._theme, self)
        self.shuffle_button.clicked.connect(self.adapter.toggle_shuffle)
        self.previous_button.clicked.connect(self.adapter.play_previous)
        self.play_button.clicked.connect(self.adapter.toggle_playback)
        self.next_button.clicked.connect(self.adapter.play_next)
        self.repeat_button.clicked.connect(self.adapter.cycle_repeat_mode)
        transport_layout = QHBoxLayout()
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.setSpacing(4)
        transport_layout.addStretch(1)
        for button in (
            self.shuffle_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.repeat_button,
        ):
            transport_layout.addWidget(button)
        transport_layout.addStretch(1)
        self.current_time_label = QLabel("0:00", self)
        self.current_time_label.setObjectName("playerTime")
        self.total_time_label = QLabel("--:--", self)
        self.total_time_label.setObjectName("playerTime")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self._on_seek_started)
        self.progress_slider.sliderReleased.connect(self._on_seek_finished)
        self.progress_slider.sliderMoved.connect(self._on_seek_preview)
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.total_time_label)
        self.center_section = QWidget(self)
        center_layout = QVBoxLayout(self.center_section)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)
        center_layout.addLayout(transport_layout)
        center_layout.addLayout(progress_layout)
        self.center_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self.lyrics_button = PlaybackButton("lyrics", "歌词", self._theme, self)
        self.queue_button = PlaybackButton("queue", "播放队列", self._theme, self)
        self.volume_button = PlaybackButton("volume", "音量", self._theme, self)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.adapter.state.volume)
        self.volume_slider.valueChanged.connect(self.adapter.set_volume)
        self.volume_label = QLabel(f"{self.adapter.state.volume}%", self)
        self.volume_label.setObjectName("volumeLabel")
        self.lyrics_button.clicked.connect(lambda: self.mock_action_requested.emit("lyrics"))
        self.queue_button.clicked.connect(lambda: self.mock_action_requested.emit("queue"))
        self.volume_button.clicked.connect(self._toggle_mute)
        self.right_section = QWidget(self)
        right_layout = QHBoxLayout(self.right_section)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self.lyrics_button)
        right_layout.addWidget(self.queue_button)
        right_layout.addWidget(self.volume_button)
        right_layout.addWidget(self.volume_slider, 1)
        right_layout.addWidget(self.volume_label)
        self.right_section.setMinimumWidth(214)
        self.right_section.setMaximumWidth(260)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(18)
        layout.addWidget(self.left_section)
        layout.addWidget(self.center_section, 1)
        layout.addWidget(self.right_section)
        self._buttons = (
            self.favorite_button,
            self.shuffle_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.repeat_button,
            self.lyrics_button,
            self.queue_button,
            self.volume_button,
        )

    def _connect_adapter(self) -> None:
        self.adapter.track_changed.connect(self._on_track_changed)
        self.adapter.playing_changed.connect(self._on_playing_changed)
        self.adapter.position_changed.connect(self._on_position_changed)
        self.adapter.duration_changed.connect(self._on_duration_changed)
        self.adapter.volume_changed.connect(self._on_volume_changed)
        self.adapter.favorite_changed.connect(self._on_favorite_changed)
        self.adapter.shuffle_changed.connect(self._on_shuffle_changed)
        self.adapter.repeat_mode_changed.connect(self._on_repeat_mode_changed)

    def _apply_state(self) -> None:
        state = self.adapter.state
        self._on_track_changed(state.current_track)
        self._on_playing_changed(state.is_playing)
        self._on_duration_changed(state.duration_ms)
        self._on_position_changed(state.position_ms)
        self._on_volume_changed(state.volume)
        self._on_favorite_changed(state.is_favorite)
        self._on_shuffle_changed(state.shuffle_enabled)
        self._on_repeat_mode_changed(state.repeat_mode)

    def _on_track_changed(self, track: Track | None) -> None:
        self.artwork.set_track(track)
        self.title_label.set_full_text(track.title if track is not None else "未选择歌曲")
        self.artist_label.set_full_text(track.artist if track is not None else "选择一首歌曲开始播放")
        self._set_track_controls_enabled(track is not None)

    def _on_playing_changed(self, is_playing: bool) -> None:
        self.play_button.set_icon_name("pause" if is_playing else "play")
        self.play_button.setToolTip("暂停" if is_playing else "播放")

    def _on_duration_changed(self, duration_ms: int | None) -> None:
        duration = max(0, int(duration_ms or 0))
        blocker = QSignalBlocker(self.progress_slider)
        self.progress_slider.setRange(0, duration)
        del blocker
        self.progress_slider.setEnabled(
            self.adapter.state.current_track is not None
            and duration_ms is not None
            and duration > 0
        )
        self.total_time_label.setText(format_duration(duration_ms))

    def _on_position_changed(self, position_ms: int) -> None:
        if self._seeking:
            return
        duration = self.adapter.state.duration_ms
        position = min(max(0, int(position_ms)), duration or 0)
        blocker = QSignalBlocker(self.progress_slider)
        self.progress_slider.setValue(position)
        del blocker
        self.current_time_label.setText(format_duration(position))

    def _on_volume_changed(self, volume: int) -> None:
        blocker = QSignalBlocker(self.volume_slider)
        self.volume_slider.setValue(volume)
        del blocker
        self.volume_label.setText(f"{volume}%")
        self.volume_button.set_icon_name("volume_mute" if volume == 0 else "volume")

    def _on_favorite_changed(self, is_favorite: bool) -> None:
        self.favorite_button.set_icon_name(
            "favorite_filled" if is_favorite else "favorite"
        )
        self.favorite_button.set_active(is_favorite)
        self.favorite_button.setToolTip("取消收藏" if is_favorite else "收藏")

    def _on_shuffle_changed(self, enabled: bool) -> None:
        self.shuffle_button.set_active(enabled)

    def _on_repeat_mode_changed(self, mode: RepeatMode) -> None:
        self.repeat_button.set_active(mode != RepeatMode.OFF)
        self._refresh_repeat_tooltip()

    def _refresh_repeat_tooltip(self) -> None:
        labels = {
            RepeatMode.OFF: "循环：关闭",
            RepeatMode.ALL: "循环：全部歌曲",
            RepeatMode.ONE: "循环：单曲",
        }
        self.repeat_button.setToolTip(labels[self.adapter.state.repeat_mode])

    def _set_track_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.favorite_button,
            self.shuffle_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.repeat_button,
            self.lyrics_button,
            self.queue_button,
        ):
            button.setEnabled(enabled and not (
                self._read_only and button is self.favorite_button
            ))
        self.progress_slider.setEnabled(
            enabled and (self.adapter.state.duration_ms or 0) > 0
        )

    def _on_seek_started(self) -> None:
        self._seeking = True

    def _on_seek_preview(self, position_ms: int) -> None:
        self.current_time_label.setText(format_duration(position_ms))

    def _on_seek_finished(self) -> None:
        self._seeking = False
        self.adapter.seek(self.progress_slider.value())

    def _toggle_mute(self) -> None:
        self.adapter.set_volume(0 if self.adapter.state.volume else 70)
