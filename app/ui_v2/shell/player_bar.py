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
from app.ui_v2.widgets.track_display import present_track_identity


class _PlayerSlider(QSlider):
    """Native-interactive slider with a deterministic, minimal player track."""

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._track_color = QColor("#606166")
        self._fill_color = QColor("#f2f1ee")
        self._handle_color = QColor("#f2f1ee")
        self._disabled_color = QColor("#6a6a70")
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
    track_open_requested = Signal()
    desktop_lyrics_settings_requested = Signal()

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
        self._favorite_available = True
        self._track_availability = None
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
        m = theme.metrics
        self.setFixedHeight(theme.metrics.player_bar_height)
        self.progress_slider.set_visual_colors(theme)
        self.volume_slider.set_visual_colors(theme)
        self.setStyleSheet(
            f"QFrame#playerBar {{ background: {c.playerbar_background}; border-top: 1px solid {c.border}; }}"
            f"QWidget#trackRegionInner, QWidget#utilityRegionInner {{ background: transparent; border: 0; border-radius: 0; }}"
            f"QWidget#trackMetadata, QWidget#volumeGroup, QWidget#transportRow, QWidget#progressRow {{ background: transparent; border: 0; }}"
            f"QLabel#playerTitle {{ color: {c.text_primary}; font-size: {theme.fonts.player_title}px; font-weight: 600; }}"
            f"QLabel#playerArtist {{ color: {c.text_secondary}; font-size: {theme.fonts.player_meta}px; font-weight: 400; }}"
            f"QLabel#playerAvailability {{ padding: 1px 5px; border-radius: {m.radius_sm}px; background: {c.surface_pressed}; color: {c.warning}; font-size: {theme.fonts.caption}px; font-weight: 400; }}"
            f"QLabel#playerTime {{ color: {c.text_secondary}; font-size: {theme.fonts.caption}px; font-weight: 400; }}"
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
        # The approved 900px shell keeps every transport and navigation action
        # reachable. The identity block tightens only to the actual side-region
        # width so long titles do not inherit an arbitrary fixed truncation.
        self.center_region.setFixedWidth(360 if compact else 500)
        self._refresh_metadata_width()
        self._constrain_side_inner_widths()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_metadata_width()

    def _refresh_metadata_width(self) -> None:
        if not all(hasattr(self, name) for name in ("metadata", "artwork")):
            return
        base_width = 160 if self._compact else 196
        region_width = max(0, self.track_region.width() - 32)
        fixed_width = self.artwork.width() + 24
        available = max(base_width, region_width - fixed_width)
        width = min(320, available)
        self.metadata.setFixedWidth(width)
        if hasattr(self, "identity_stack"):
            self.identity_stack.setFixedWidth(width)

    def set_read_only(
        self,
        read_only: bool,
        *,
        allow_playback: bool = False,
        allow_favorite: bool = False,
    ) -> None:
        """Keep writes disabled while allowing a formal local playback backend."""

        self._read_only = bool(read_only)
        self._transport_available = bool(allow_playback)
        self._favorite_available = not self._read_only or bool(allow_favorite)
        self.favorite_button.setVisible(self._favorite_available)
        self.favorite_button.setEnabled(self._favorite_available)
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
        track_inner_layout.setContentsMargins(8, 6, 8, 6)
        track_inner_layout.setSpacing(10)
        self.artwork = ArtworkThumbnail(self._theme, self.track_inner, size=56)
        self.title_label = ElidedLabel(self.track_inner)
        self.title_label.setObjectName("playerTitle")
        self.artist_label = ElidedLabel(self.track_inner, max_lines=2)
        self.artist_label.setObjectName("playerArtist")
        self.identity_stack = QWidget(self.track_inner)
        self.identity_stack.setObjectName("playerIdentityStack")
        self.identity_stack.setFixedWidth(154)
        self.identity_stack.setFixedHeight(76)
        identity_layout = QVBoxLayout(self.identity_stack)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(4)
        self.availability_label = QLabel(self.identity_stack)
        self.availability_label.setObjectName("playerAvailability")
        self.availability_label.setVisible(False)
        self.availability_label.setToolTip("")
        self.metadata = QWidget(self.identity_stack)
        self.metadata.setObjectName("trackMetadata")
        # The approved track copy is one compact two-line group.  Give it a
        # fixed vertical rhythm instead of letting the two labels consume the
        # full-height side region independently.
        self.metadata.setFixedWidth(154)
        self.metadata.setFixedHeight(64)
        self.metadata.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        metadata_layout = QVBoxLayout(self.metadata)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(3)
        metadata_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setFixedHeight(18)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.artist_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.availability_label.setFixedHeight(16)
        self.availability_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        metadata_layout.addWidget(self.title_label)
        metadata_layout.addWidget(self.artist_label)
        identity_layout.addWidget(self.metadata)
        identity_layout.addWidget(self.availability_label)
        track_inner_layout.addWidget(self.artwork)
        track_inner_layout.addWidget(self.identity_stack)
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
        # Keep the favorite action in the transport rail so long track
        # metadata cannot cover it. This is the leftmost control in the rail.
        self.favorite_button = PlayerIconButton(
            "favorite", "收藏", self._theme, self.transport_row, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.favorite_button.clicked.connect(self.adapter.toggle_favorite)
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
        transport_layout.addWidget(self.favorite_button)
        for button in (self.shuffle_button, self.previous_button, self.play_button, self.next_button, self.repeat_button):
            transport_layout.addWidget(button)
        # The new leftmost favorite control adds 44px (button plus gap) to
        # the control group. Match that width on the right so the play button
        # stays on the bar's optical centre.
        transport_layout.addSpacing(44)
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
        utility_layout.setContentsMargins(5, 5, 5, 5)
        utility_layout.setSpacing(9)
        self.queue_button = PlayerIconButton(
            "queue", "播放队列", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.lyrics_button = PlayerIconButton(
            "lyrics", "歌词", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
            asset_family="fluent_player",
        )
        self.desktop_lyrics_button = PlayerIconButton(
            "desktop_lyrics", "桌面歌词", self._theme, self.utility_inner, size=32, icon_canvas_size=18,
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
        # Compatibility handle for older integrations; the placeholder action
        # is intentionally not part of the visible PlayerBar layout.
        self.more_button.setVisible(False)
        self.lyrics_button.clicked.connect(lambda: self.mock_action_requested.emit("lyrics"))
        self.desktop_lyrics_button.clicked.connect(
            lambda: self.mock_action_requested.emit("desktop_lyrics")
        )
        self.desktop_lyrics_button.setContextMenuPolicy(
            Qt.ContextMenuPolicy.NoContextMenu
        )
        self.queue_button.clicked.connect(lambda: self.mock_action_requested.emit("queue"))
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
        utility_layout.addWidget(self.desktop_lyrics_button)
        utility_layout.addWidget(self.volume_group)
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
            self.lyrics_button, self.desktop_lyrics_button, self.queue_button,
            self.volume_button, self.more_button,
        )
        self._configure_accessibility()
        for widget in (
            self.track_inner,
            self.artwork,
            self.identity_stack,
            self.title_label,
            self.artist_label,
            self.metadata,
        ):
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched in (self.track_inner, self.artwork, self.title_label, self.artist_label, self.metadata):
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.track_open_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def _configure_accessibility(self) -> None:
        """Give the fixed player rail stable keyboard and screen-reader labels."""

        labels = (
            (self.favorite_button, "收藏"),
            (self.shuffle_button, "随机播放"),
            (self.previous_button, "上一首"),
            (self.play_button, "播放"),
            (self.next_button, "下一首"),
            (self.repeat_button, "循环模式"),
            (self.queue_button, "播放队列"),
            (self.lyrics_button, "歌词"),
            (self.desktop_lyrics_button, "桌面歌词"),
            (self.volume_button, "音量"),
            (self.more_button, "更多"),
        )
        for button, label in labels:
            button.setAccessibleName(label)
            button.setAccessibleDescription(f"播放器：{label}")
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.progress_slider.setAccessibleName("播放进度")
        self.progress_slider.setAccessibleDescription("调整当前歌曲的播放位置")
        self.volume_slider.setAccessibleName("音量大小")
        self.volume_slider.setAccessibleDescription("调整播放器音量")
        self.track_inner.setAccessibleName("当前播放歌曲")
        self.track_inner.setAccessibleDescription("打开当前歌曲详情")

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
        self.adapter.playback_status_changed.connect(self._on_playback_status_changed)

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
        self._on_playback_status_changed(state.status, state.status_detail)

    def _on_track_changed(self, track: Track | None) -> None:
        self.artwork.set_track(track)
        if track is None:
            title, metadata = "未选择歌曲", "选择一首歌曲开始播放"
            self._track_availability = None
        else:
            identity = present_track_identity(track)
            title, metadata = identity.title, identity.metadata
            self._track_availability = identity.availability
        self.title_label.set_full_text(title)
        self.artist_label.set_full_text(metadata)
        self.availability_label.clear()
        self.availability_label.setToolTip("")
        self.availability_label.setVisible(False)
        self.identity_stack.setFixedHeight(76)
        self.artist_label.setToolTip(metadata)
        self.track_inner.setToolTip(f"{title}\n{metadata}\n点击查看详情")
        self._set_track_controls_enabled(track is not None)

    def _on_playing_changed(self, is_playing: bool) -> None:
        self.play_button.set_icon_name("pause" if is_playing else "play")
        action = "暂停" if is_playing else "播放"
        self.play_button.setToolTip(action)
        self.play_button.setAccessibleName(action)

    def _on_playback_status_changed(self, status: str, detail: str) -> None:
        track = self.adapter.state.current_track
        if track is None:
            return
        identity = present_track_identity(
            track,
            playback_status=status,
            playback_detail=detail,
        )
        self._track_availability = identity.availability
        self.artist_label.set_full_text(identity.metadata)
        if identity.availability.is_visible:
            self.availability_label.setText(identity.availability.label)
            self.availability_label.setToolTip(identity.availability.tooltip)
            self.availability_label.setVisible(True)
            self.identity_stack.setFixedHeight(86)
            self.artist_label.setToolTip(
                f"{identity.metadata}\n状态: {identity.availability.label}\n"
                f"{identity.availability.tooltip}"
            )
        else:
            self.availability_label.clear()
            self.availability_label.setToolTip("")
            self.availability_label.setVisible(False)
            self.identity_stack.setFixedHeight(76)
            self.artist_label.setToolTip(identity.metadata)

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
        is_muted = self.adapter.state.is_muted or self.adapter.state.volume == 0
        self.volume_button.set_icon_name(
            "volume_mute"
            if is_muted
            else "volume"
        )
        action = "取消静音" if is_muted else "静音"
        self.volume_button.setToolTip(action)
        self.volume_button.setAccessibleName(action)

    def _on_favorite_changed(self, is_favorite: bool) -> None:
        self.favorite_button.set_icon_name("favorite_filled" if is_favorite else "favorite")
        self.favorite_button.set_active(is_favorite)
        action = "取消收藏" if is_favorite else "收藏"
        self.favorite_button.setToolTip(action)
        self.favorite_button.setAccessibleName(action)

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
        label = labels[self.adapter.state.repeat_mode]
        self.repeat_button.setToolTip(label)
        self.repeat_button.setAccessibleName(label)

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
        for button in (
            self.lyrics_button,
            self.desktop_lyrics_button,
            self.queue_button,
            self.more_button,
        ):
            button.setEnabled(navigation_enabled)
        self.favorite_button.setEnabled(bool(enabled) and self._favorite_available)
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
        self.adapter.toggle_mute()
