"""Approved three-region PlayerBar driven by the existing PlaybackAdapter."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSignalBlocker, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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
from app.ui_v2.widgets.playback_button import PlayerIconButton
from app.ui_v2.widgets.track_display import display_track_text


class _PlayerSlider(QSlider):
    """Native-interactive slider with a deterministic, minimal player track."""

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._track_color = QColor("#43464a")
        self._fill_color = QColor("#f4f3f2")
        self._handle_color = QColor("#f4f3f2")
        self._disabled_color = QColor("#606166")
        self.setMouseTracking(True)

    def set_visual_colors(self, theme: Theme) -> None:
        colors = theme.colors
        self._track_color = QColor(colors.progress_track)
        self._fill_color = QColor(colors.progress_fill)
        self._handle_color = QColor(colors.text_primary)
        self._disabled_color = QColor(colors.text_disabled)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self.orientation() != Qt.Orientation.Horizontal:
            return super().paintEvent(_event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(4, 0, -4, 0)
        center_y = bounds.center().y()
        track = QRectF(float(bounds.left()), center_y - 1.5, float(bounds.width()), 3.0)
        track_color = self._track_color if self.isEnabled() else self._disabled_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 1.5, 1.5)

        minimum, maximum = self.minimum(), self.maximum()
        ratio = 0.0 if maximum <= minimum else (self.value() - minimum) / (maximum - minimum)
        ratio = max(0.0, min(1.0, ratio))
        handle_radius = 5.0 if self.isEnabled() and self.underMouse() else 4.0
        handle_x = track.left() + track.width() * ratio
        if ratio > 0:
            fill = QRectF(track.left(), track.top(), max(0.0, handle_x - track.left()), track.height())
            painter.setBrush(self._fill_color if self.isEnabled() else self._disabled_color)
            painter.drawRoundedRect(fill, 1.5, 1.5)
        painter.setBrush(self._handle_color if self.isEnabled() else self._disabled_color)
        painter.drawEllipse(QRectF(handle_x - handle_radius, center_y - handle_radius, handle_radius * 2, handle_radius * 2))
        painter.end()


class PlayerBar(QFrame):
    """One stable 102px player with full-height side regions and a two-row centre."""

    mock_action_requested = Signal(str)
    queue_requested = Signal()
    lyrics_requested = Signal()
    track_open_requested = Signal()

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
        self._transport_available = False
        self.setObjectName("playerBar")
        self.setFixedHeight(theme.metrics.player_bar_height)
        self._build_layout()
        self._connect_adapter()
        self.set_theme(theme)
        self._apply_state()

    @property
    def compact(self) -> bool:
        return self._compact

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setFixedHeight(theme.metrics.player_bar_height)
        self.progress_slider.set_visual_colors(theme)
        self.volume_slider.set_visual_colors(theme)
        self.setStyleSheet(
            f"QFrame#playerBar {{ background: {c.playerbar_background}; border-top: 1px solid {c.divider}; }}"
            f"QLabel#playerTitle {{ color: {c.text_primary}; font-size: {theme.fonts.player_title}px; font-weight: 600; }}"
            f"QLabel#playerArtist {{ color: {c.text_secondary}; font-size: {theme.fonts.player_meta}px; }}"
            f"QLabel#playerTime {{ color: {c.text_secondary}; font-size: 11px; }}"
            f"QSlider#playerProgress, QSlider#playerVolume {{ background: transparent; border: 0; }}"
            f"QSlider#playerProgress::groove:horizontal {{ height: 3px; border-radius: 2px; background: {c.progress_track}; }}"
            f"QSlider#playerVolume::groove:horizontal {{ height: 3px; border-radius: 2px; background: {c.progress_track}; }}"
            f"QSlider#playerProgress::add-page:horizontal, QSlider#playerVolume::add-page:horizontal {{ background: transparent; }}"
            f"QSlider#playerProgress::sub-page:horizontal, QSlider#playerVolume::sub-page:horizontal {{ border-radius: 2px; background: {c.progress_fill}; }}"
            f"QSlider#playerProgress::handle:horizontal, QSlider#playerVolume::handle:horizontal {{ width: 8px; margin: -3px 0; border-radius: 4px; background: {c.text_primary}; }}"
            f"QSlider#playerProgress:hover::handle:horizontal, QSlider#playerVolume:hover::handle:horizontal {{ width: 10px; margin: -4px 0; border-radius: 5px; background: {c.icon_hover}; }}"
            f"QSlider#playerProgress:disabled::groove:horizontal, QSlider#playerVolume:disabled::groove:horizontal {{ background: {c.surface_pressed}; }}"
            f"QSlider#playerProgress:disabled::sub-page:horizontal, QSlider#playerVolume:disabled::sub-page:horizontal {{ background: {c.text_disabled}; }}"
            f"QSlider#playerProgress:disabled::handle:horizontal, QSlider#playerVolume:disabled::handle:horizontal {{ background: {c.text_disabled}; }}"
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
        self.more_button.setVisible(not compact)
        self.lyrics_button.setVisible(not compact)
        self.queue_button.setVisible(not compact)
        self.shuffle_button.setVisible(not compact)
        self.repeat_button.setVisible(not compact)
        self.center_region.setFixedWidth(360 if compact else 500)
        self.metadata.setFixedWidth(118 if compact else 154)
        self._constrain_side_inner_widths()

    def set_read_only(self, read_only: bool, *, allow_playback: bool = False) -> None:
        """Keep writes disabled while allowing a formal local playback backend."""

        self._read_only = bool(read_only)
        self._transport_available = bool(allow_playback)
        self.favorite_button.setVisible(not self._read_only)
        self.favorite_button.setEnabled(not self._read_only)
        self._set_track_controls_enabled(self.adapter.state.current_track is not None)

    def _build_layout(self) -> None:
        # TrackRegion spans the entire bar and owns its own visual centre.
        self.track_region = QWidget(self)
        self.track_region.setObjectName("trackRegion")
        self.left_section = self.track_region  # compatibility alias
        # Grid columns own the side-region width.  Ignore text-derived outer
        # size hints so a long current track cannot pull the centre off-window.
        self.track_region.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        track_region_layout = QHBoxLayout(self.track_region)
        self.track_region_layout = track_region_layout
        track_region_layout.setContentsMargins(16, 0, 16, 0)
        track_region_layout.setSpacing(0)
        track_region_layout.addStretch(1)
        self.track_inner = QWidget(self.track_region)
        self.track_inner.setObjectName("trackRegionInner")
        self.track_inner.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        track_inner_layout = QHBoxLayout(self.track_inner)
        track_inner_layout.setContentsMargins(0, 0, 0, 0)
        track_inner_layout.setSpacing(12)
        self.artwork = ArtworkThumbnail(self._theme, self.track_inner, size=56)
        self.title_label = ElidedLabel(self.track_inner)
        self.title_label.setObjectName("playerTitle")
        self.artist_label = ElidedLabel(self.track_inner)
        self.artist_label.setObjectName("playerArtist")
        self.metadata = QWidget(self.track_inner)
        self.metadata.setObjectName("trackMetadata")
        # The approved track copy is one compact two-line group.  Give it a
        # fixed vertical rhythm instead of letting the two labels consume the
        # full-height side region independently.
        self.metadata.setFixedWidth(174)
        self.metadata.setFixedHeight(36)
        self.metadata.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        metadata_layout = QVBoxLayout(self.metadata)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(3)
        metadata_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setFixedHeight(15)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.artist_label.setFixedHeight(14)
        self.artist_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.artist_label)
        self.favorite_button = PlayerIconButton(
            "favorite", "收藏", self._theme, self.track_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.favorite_button.clicked.connect(self.adapter.toggle_favorite)
        track_inner_layout.addWidget(self.artwork)
        track_inner_layout.addWidget(self.metadata)
        track_inner_layout.addWidget(self.favorite_button)
        # The outer region owns the complete left grid column.  Its two equal
        # stretches center this natural-width group without anchoring artwork
        # or favourite controls to either column edge.
        track_region_layout.addWidget(
            self.track_inner, 0, Qt.AlignmentFlag.AlignCenter
        )
        track_region_layout.addStretch(1)

        # CenterRegion alone owns the transport and progress rows.
        self.center_region = QWidget(self)
        self.center_region.setObjectName("centerRegion")
        self.center_section = self.center_region  # compatibility alias
        self.center_region.setFixedWidth(500)
        center_layout = QVBoxLayout(self.center_region)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addStretch(1)

        self.transport_row = QWidget(self.center_region)
        self.transport_row.setObjectName("transportRow")
        self.transport_row.setFixedHeight(60)
        transport_layout = QHBoxLayout(self.transport_row)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.setSpacing(12)
        transport_layout.addStretch(1)
        self.shuffle_button = PlayerIconButton(
            "shuffle", "随机播放", self._theme, self.transport_row, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.previous_button = PlayerIconButton(
            "previous", "上一首", self._theme, self.transport_row, size=34, icon_canvas_size=20,
            asset_family="fluent_player",
        )
        self.play_button = PlayerIconButton(
            "play", "播放", self._theme, self.transport_row, primary=True, size=52, icon_canvas_size=22,
            asset_family="fluent_player",
        )
        self.next_button = PlayerIconButton(
            "next", "下一首", self._theme, self.transport_row, size=34, icon_canvas_size=20,
            asset_family="fluent_player",
        )
        self.repeat_button = PlayerIconButton(
            "repeat", "循环模式", self._theme, self.transport_row, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.shuffle_button.clicked.connect(self.adapter.toggle_shuffle)
        self.previous_button.clicked.connect(self.adapter.play_previous)
        self.play_button.clicked.connect(self.adapter.toggle_playback)
        self.next_button.clicked.connect(self.adapter.play_next)
        self.repeat_button.clicked.connect(self.adapter.cycle_repeat_mode)
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button, self.repeat_button):
            transport_layout.addWidget(button)
        transport_layout.addStretch(1)

        self.progress_row = QWidget(self.center_region)
        self.progress_row.setObjectName("progressRow")
        self.progress_row.setFixedHeight(30)
        progress_layout = QHBoxLayout(self.progress_row)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        self.current_time_label = QLabel("0:00", self.progress_row)
        self.current_time_label.setObjectName("playerTime")
        self.current_time_label.setFixedWidth(38)
        self.current_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_time_label = QLabel("--:--", self.progress_row)
        self.total_time_label.setObjectName("playerTime")
        self.total_time_label.setFixedWidth(38)
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.progress_slider = _PlayerSlider(Qt.Orientation.Horizontal, self.progress_row)
        self.progress_slider.setObjectName("playerProgress")
        # Keep a real paintable canvas inside the fixed progress row.  Without
        # an explicit vertical size Qt can collapse a horizontal slider to
        # zero height on the native Windows style, leaving the approved track
        # invisible while the surrounding labels still render.
        self.progress_slider.setFixedHeight(18)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self._on_seek_started)
        self.progress_slider.sliderReleased.connect(self._on_seek_finished)
        self.progress_slider.sliderMoved.connect(self._on_seek_preview)
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.total_time_label)
        center_layout.addWidget(self.transport_row)
        center_layout.addWidget(self.progress_row)
        center_layout.addStretch(1)

        # UtilityRegion also spans the whole bar and remains visually centred.
        self.utility_region = QWidget(self)
        self.utility_region.setObjectName("utilityRegion")
        self.right_section = self.utility_region  # compatibility alias
        self.utility_region.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        utility_region_layout = QHBoxLayout(self.utility_region)
        self.utility_region_layout = utility_region_layout
        utility_region_layout.setContentsMargins(16, 0, 16, 0)
        utility_region_layout.setSpacing(0)
        utility_region_layout.addStretch(1)
        self.utility_inner = QWidget(self.utility_region)
        self.utility_inner.setObjectName("utilityRegionInner")
        self.utility_inner.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        utility_layout = QHBoxLayout(self.utility_inner)
        utility_layout.setContentsMargins(0, 0, 0, 0)
        utility_layout.setSpacing(9)
        self.queue_button = PlayerIconButton(
            "queue", "播放队列", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.lyrics_button = PlayerIconButton(
            "lyrics", "歌词", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.volume_button = PlayerIconButton(
            "volume", "音量", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.volume_slider = _PlayerSlider(Qt.Orientation.Horizontal, self.utility_inner)
        self.volume_slider.setObjectName("playerVolume")
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setFixedHeight(18)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.adapter.state.volume)
        self.volume_slider.valueChanged.connect(self.adapter.set_volume)
        self.volume_label = QLabel(self.utility_inner)
        self.volume_label.setVisible(False)
        self.more_button = PlayerIconButton(
            "more", "更多", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.lyrics_button.clicked.connect(self.lyrics_requested)
        self.queue_button.clicked.connect(self.queue_requested)
        self.more_button.clicked.connect(lambda: self.mock_action_requested.emit("more"))
        self.volume_button.clicked.connect(self._toggle_mute)
        self.volume_group = QWidget(self.utility_inner)
        self.volume_group.setObjectName("volumeGroup")
        volume_layout = QHBoxLayout(self.volume_group)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(6)
        volume_layout.addWidget(self.volume_button)
        volume_layout.addWidget(self.volume_slider)
        utility_layout.addWidget(self.queue_button)
        utility_layout.addWidget(self.lyrics_button)
        utility_layout.addWidget(self.volume_group)
        utility_layout.addWidget(self.more_button)
        # Like TrackRegion, tools retain their intrinsic width and sit at the
        # visual centre of the complete right grid column rather than its edge.
        utility_region_layout.addWidget(
            self.utility_inner, 0, Qt.AlignmentFlag.AlignCenter
        )
        utility_region_layout.addStretch(1)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)
        layout.addWidget(self.track_region, 0, 0)
        layout.addWidget(self.center_region, 0, 1)
        layout.addWidget(self.utility_region, 0, 2)
        layout.setColumnMinimumWidth(0, 260)
        layout.setColumnMinimumWidth(2, 260)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        self._constrain_side_inner_widths()
        self._buttons = (
            self.favorite_button, self.shuffle_button, self.previous_button,
            self.play_button, self.next_button, self.repeat_button,
            self.lyrics_button, self.queue_button, self.volume_button, self.more_button,
        )
        for widget in (self.track_inner, self.artwork, self.title_label, self.artist_label, self.metadata):
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched in (self.track_inner, self.artwork, self.title_label, self.artist_label, self.metadata):
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.track_open_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def _constrain_side_inner_widths(self) -> None:
        """Keep side content at its intrinsic width inside its grid column."""

        for inner in (self.track_inner, self.utility_inner):
            layout = inner.layout()
            if layout is not None:
                layout.activate()
            inner.setMaximumWidth(inner.sizeHint().width())

    def _connect_adapter(self) -> None:
        self.adapter.track_changed.connect(self._on_track_changed)
        self.adapter.playing_changed.connect(self._on_playing_changed)
        self.adapter.position_changed.connect(self._on_position_changed)
        self.adapter.duration_changed.connect(self._on_duration_changed)
        self.adapter.volume_changed.connect(self._on_volume_changed)
        self.adapter.muted_changed.connect(self._on_muted_changed)
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
        self._on_muted_changed(state.is_muted)
        self._on_favorite_changed(state.is_favorite)
        self._on_shuffle_changed(state.shuffle_enabled)
        self._on_repeat_mode_changed(state.repeat_mode)

    def _on_track_changed(self, track: Track | None) -> None:
        self.artwork.set_track(track)
        if track is None:
            title, artist = "未选择歌曲", "选择一首歌曲开始播放"
        else:
            title, artist, _album = display_track_text(track)
        self.title_label.set_full_text(title)
        self.artist_label.set_full_text(artist)
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
            self.adapter.state.current_track is not None and duration_ms is not None and duration > 0
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
        self._refresh_volume_icon()

    def _on_muted_changed(self, _muted: bool) -> None:
        self._refresh_volume_icon()

    def _refresh_volume_icon(self) -> None:
        self.volume_button.set_icon_name(
            "volume_mute"
            if self.adapter.state.is_muted or self.adapter.state.volume == 0
            else "volume"
        )

    def _on_favorite_changed(self, is_favorite: bool) -> None:
        self.favorite_button.set_icon_name("favorite_filled" if is_favorite else "favorite")
        self.favorite_button.set_active(is_favorite)
        self.favorite_button.setToolTip("取消收藏" if is_favorite else "收藏")

    def _on_shuffle_changed(self, enabled: bool) -> None:
        self.shuffle_button.set_active(enabled)

    def _on_repeat_mode_changed(self, mode: RepeatMode) -> None:
        self.repeat_button.set_icon_name(
            "repeat_one" if mode == RepeatMode.ONE else "repeat"
        )
        self.repeat_button.set_active(mode != RepeatMode.OFF)
        self._refresh_repeat_tooltip()

    def _refresh_repeat_tooltip(self) -> None:
        labels = {
            RepeatMode.OFF: "关闭循环",
            RepeatMode.ALL: "列表循环",
            RepeatMode.ONE: "单曲循环",
        }
        self.repeat_button.setToolTip(labels[self.adapter.state.repeat_mode])

    def _set_track_controls_enabled(self, enabled: bool) -> None:
        transport_enabled = bool(enabled) and (
            not self._read_only or self._transport_available
        )
        for button in (
            self.shuffle_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.repeat_button,
        ):
            button.setEnabled(transport_enabled)
        # Real read-only mode still needs to expose page entry points while no
        # playback capability has been connected yet.
        navigation_enabled = bool(enabled) or self._read_only
        for button in (self.lyrics_button, self.queue_button, self.more_button):
            button.setEnabled(navigation_enabled)
        self.favorite_button.setEnabled(bool(enabled) and not self._read_only)
        self.progress_slider.setEnabled(
            transport_enabled and (self.adapter.state.duration_ms or 0) > 0
        )

    def _on_seek_started(self) -> None:
        self._seeking = True

    def _on_seek_preview(self, position_ms: int) -> None:
        self.current_time_label.setText(format_duration(position_ms))

    def _on_seek_finished(self) -> None:
        self._seeking = False
        self.adapter.seek(self.progress_slider.value())

    def _toggle_mute(self) -> None:
        self.adapter.set_muted(not self.adapter.state.is_muted)
