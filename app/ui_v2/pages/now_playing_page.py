"""Now Playing content used by the shared immersive player shell.

The page is deliberately a presentation-only view.  Playback, queue and
favorite state continue to live in the existing adapters; this widget only
subscribes to them and exposes the small set of actions that are useful while
the shell is open.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.icons import fluent_icon, icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.track_display import present_track_identity


class NowPlayingPage(QFrame):
    """Large artwork and metadata view for the immersive shell."""

    queue_requested = Signal()
    lyrics_requested = Signal()
    more_requested = Signal()

    def __init__(self, playback: PlaybackAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playback = playback
        self._theme = theme
        self._artwork_extent = 340
        self.setObjectName("nowPlayingPage")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.artwork = ArtworkThumbnail(
            theme,
            self,
            size=self._artwork_extent,
            clip_artwork=True,
        )
        self.artwork.setObjectName("nowPlayingArtwork")
        self.title_label = ElidedLabel(self, max_lines=2)
        self.title_label.setObjectName("nowPlayingTitle")
        self.artist_label = ElidedLabel(self)
        self.artist_label.setObjectName("nowPlayingArtist")
        self.album_label = ElidedLabel(self)
        self.album_label.setObjectName("nowPlayingAlbum")
        self.detail_label = QLabel(self)
        self.detail_label.setObjectName("nowPlayingDetail")
        self.detail_label.setWordWrap(True)
        self.error_label = QLabel(self)
        self.error_label.setObjectName("nowPlayingError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.favorite_button = QToolButton(self)
        self.favorite_button.setObjectName("nowPlayingFavorite")
        self.favorite_button.setFixedSize(38, 38)
        self.favorite_button.setIconSize(QSize(20, 20))
        self.queue_button = QToolButton(self)
        self.queue_button.setObjectName("nowPlayingQueue")
        self.queue_button.setFixedSize(38, 38)
        self.queue_button.setIconSize(QSize(20, 20))
        self.queue_button.clicked.connect(self.queue_requested)
        self.lyrics_button = QToolButton(self)
        self.lyrics_button.setObjectName("nowPlayingLyrics")
        self.lyrics_button.setFixedSize(38, 38)
        self.lyrics_button.setIconSize(QSize(20, 20))
        self.lyrics_button.clicked.connect(self.lyrics_requested)
        self.more_button = QToolButton(self)
        self.more_button.setObjectName("nowPlayingMore")
        self.more_button.setFixedSize(38, 38)
        self.more_button.setIconSize(QSize(20, 20))
        self.more_button.clicked.connect(self.more_requested)

        self._meta_group = QWidget(self)
        self._meta_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        meta_layout = QVBoxLayout(self._meta_group)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(10)
        meta_layout.addWidget(self.title_label)
        meta_layout.addWidget(self.artist_label)
        meta_layout.addWidget(self.album_label)
        meta_layout.addWidget(self.detail_label)
        meta_layout.addWidget(self.error_label)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 10, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.favorite_button)
        actions.addWidget(self.queue_button)
        actions.addWidget(self.lyrics_button)
        actions.addWidget(self.more_button)
        actions.addStretch(1)
        meta_layout.addLayout(actions)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(56)
        layout.addStretch(1)
        layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._meta_group, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self.favorite_button.clicked.connect(self.playback.toggle_favorite)
        self.playback.track_changed.connect(self._on_track_changed)
        self.playback.favorite_changed.connect(self._on_favorite_changed)
        self.playback.playing_changed.connect(self._on_playing_changed)
        self.playback.playback_status_changed.connect(self._on_playback_status_changed)
        self.playback.error_occurred.connect(self._on_playback_error)
        self._on_track_changed(self.playback.state.current_track)
        self._on_favorite_changed(self.playback.state.is_favorite)
        self._on_playing_changed(self.playback.state.is_playing)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#nowPlayingPage {{ background: transparent; }}"
            f"QLabel#nowPlayingTitle {{ color: {colors.text_primary}; font-size: 32px; font-weight: 600; }}"
            f"QLabel#nowPlayingArtist {{ color: {colors.text_secondary}; font-size: 19px; }}"
            f"QLabel#nowPlayingAlbum {{ color: {colors.text_tertiary}; font-size: 15px; }}"
            f"QLabel#nowPlayingDetail {{ color: {colors.text_secondary}; font-size: 13px; }}"
            f"QLabel#nowPlayingError {{ color: {colors.danger}; font-size: 13px; }}"
            f"QToolButton {{ border: 0; border-radius: 19px; background: transparent; }}"
            f"QToolButton:hover {{ background: {colors.surface_hover}; }}"
        )
        self.artwork.set_theme(theme)
        self.favorite_button.setIcon(fluent_icon("favorite_filled" if self.playback.state.is_favorite else "favorite", theme, "selected" if self.playback.state.is_favorite else "normal", size=20))
        self.queue_button.setIcon(fluent_icon("queue", theme, size=20))
        self.lyrics_button.setIcon(fluent_icon("lyrics", theme, size=20))
        self.more_button.setIcon(fluent_icon("more", theme, size=20))
        self.favorite_button.setToolTip("取消收藏" if self.playback.state.is_favorite else "收藏")
        self.queue_button.setToolTip("播放队列")
        self.lyrics_button.setToolTip("歌词")
        self.more_button.setToolTip("歌词快捷设置")

    def set_responsive_reference_width(self, width: int, height: int | None = None) -> None:
        width = max(1, int(width))
        if width < 900:
            extent = 230
            meta_min, meta_max = 250, min(300, max(250, width - 48))
        elif width < 1100:
            extent = 280
            meta_min, meta_max = 280, 340
        elif width < 1400:
            extent = 340
            meta_min, meta_max = 340, 400
        elif width < 1700:
            extent = 390
            meta_min, meta_max = 400, 460
        else:
            extent = 420
            meta_min, meta_max = 420, 500
        self._meta_group.setMinimumWidth(meta_min)
        self._meta_group.setMaximumWidth(max(meta_min, meta_max))
        self._artwork_extent = extent
        self.artwork.set_display_size(extent)
        for label in (self.title_label, self.artist_label, self.album_label):
            label.setMinimumWidth(meta_min)
            label.setMaximumWidth(self._meta_group.maximumWidth())

    def set_read_only(self, read_only: bool) -> None:
        """Hide persistence-affecting actions in the real read-only projection."""

        self.favorite_button.setVisible(not bool(read_only))
        self.favorite_button.setEnabled(not bool(read_only) and self.playback.state.current_track is not None)

    def _on_track_changed(self, track: Track | None) -> None:
        self.error_label.hide()
        self.artwork.set_track(track)
        if track is None:
            self.title_label.set_full_text("未选择歌曲")
            self.artist_label.set_full_text("选择一首歌曲开始播放")
            self.album_label.set_full_text("")
        else:
            identity = present_track_identity(track)
            self.title_label.set_full_text(identity.title)
            self.artist_label.set_full_text(identity.artist)
            self.album_label.set_full_text(identity.album)
            if identity.availability.is_visible:
                self.album_label.setToolTip(
                    f"{identity.metadata}\n状态: {identity.availability.label}\n"
                    f"{identity.availability.tooltip}"
                )
        if track is None:
            self.detail_label.setText("选择一首歌曲开始播放")
        else:
            self._refresh_playback_detail()
        enabled = track is not None
        self.favorite_button.setEnabled(enabled)
        self.queue_button.setEnabled(True)
        self.lyrics_button.setEnabled(True)
        self.more_button.setEnabled(True)

    def _on_favorite_changed(self, favorite: bool) -> None:
        self.favorite_button.setIcon(fluent_icon("favorite_filled" if favorite else "favorite", self._theme, "selected" if favorite else "normal", size=20))
        self.favorite_button.setToolTip("取消收藏" if favorite else "收藏")

    def _on_playing_changed(self, _playing: bool) -> None:
        self._refresh_playback_detail()

    def _on_playback_status_changed(self, _status: str, _detail: str) -> None:
        self._refresh_playback_detail()

    def _refresh_playback_detail(self) -> None:
        track = self.playback.state.current_track
        if track is None:
            return
        state = self.playback.state
        label = {
            "resolving": "准备播放",
            "buffering": "缓冲中",
            "unavailable": "来源不可用",
            "error": "播放失败",
            "playing": "播放中",
            "paused": "已暂停",
        }.get(state.status, "播放中" if state.is_playing else "已暂停")
        self.detail_label.setText(f"{format_duration(track.duration_ms)} · {label}")
        self.detail_label.setToolTip(state.status_detail or label)

    def _on_playback_error(self, message: str) -> None:
        detail = str(message or "播放失败，请检查音频文件或输出设备")
        self.error_label.setText(f"播放遇到问题 · {detail}")
        self.error_label.show()
