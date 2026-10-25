"""Bottom player bar: artwork, transport controls, seek bar and utilities."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ...audio.engine import STATE_LOADING, STATE_PLAYING
from ...core.theme import Metrics, mix, qcolor, rgba, theme
from ...model.track import Track, format_duration
from ..context import ctx
from .hover_tip import display_source
from .common import HoverAnimation, IconButton, PlayButton
from .cover import CoverWidget
from .sliders import SeekBar, VolumeSlider


class TrackInfo(QWidget):
    """Two-line, elided title/artist block that doubles as a button."""

    clicked = Signal()
    favorite_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = ""
        self._artist = ""
        self._badge = ""
        self._active_source = ""
        self._status = ""
        self._hover = HoverAnimation(self, 120)
        self.setMinimumWidth(240)
        self.setMaximumWidth(theme().scaled(200, factor=0.6))
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._fit_height()

    def _fit_height(self) -> None:
        title = QFontMetrics(theme().font(10.2, 600))
        artist = QFontMetrics(theme().font(8.8, 500))
        self.setFixedHeight(title.height() + artist.height() + 10)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_height()

    def set_active_source(self, name: str) -> None:
        """Show the source that actually resolved the stream."""
        self._active_source = name or ""
        self.update()

    def set_track(self, track: Track | None, *, subtitle: str = "") -> None:
        if track is None:
            self._title = "未在播放"
            self._artist = subtitle or "选择一首歌曲开始收听"
            self._badge = ""
        else:
            self._title = track.display_title
            self._artist = track.display_artist
            self._badge = display_source(track) if track.is_online else ""
            self._active_source = ""
        self.setToolTip(f"{self._title}\n{self._artist}" if self._title else "")
        self.update()

    def set_subtitle(self, text: str) -> None:
        self._artist = text
        self.update()

    def set_status(self, text: str) -> None:
        """Transient hint (e.g. buffering) shown instead of the source badge."""
        self._status = text
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())

        title_font = theme().font(10.2, 600)
        title_metrics = QFontMetrics(title_font)
        artist_font = theme().font(8.8, 500)
        artist_metrics = QFontMetrics(artist_font)
        # Only transient status (e.g. buffering) stays a pill; the source
        # name reads better as a quiet suffix on the artist line.
        badge_text = self._status
        badge_width = 0.0
        if badge_text:
            font = theme().font(7.2, 600)
            badge_width = QFontMetrics(font).horizontalAdvance(badge_text) + 14

        # Two metric-driven rows, vertically centred: fixed offsets used to make
        # the title and subtitle collide once the type scale grew.
        row_gap = 2
        total = title_metrics.height() + row_gap + artist_metrics.height()
        top = max(0, int((rect.height() - total) / 2))
        painter.setFont(title_font)
        painter.setPen(QPen(rgba(palette.text, 0.96)))
        painter.drawText(
            QRectF(0, top, max(10.0, rect.width() - 4), title_metrics.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            title_metrics.elidedText(
                self._title or "未在播放", Qt.ElideRight, int(max(10, rect.width() - 4))
            ),
        )

        y = top + title_metrics.height() + row_gap
        painter.setFont(artist_font)
        painter.setPen(QPen(rgba(palette.text, 0.32 + 0.28 * self._hover.value)))
        artist_width = rect.width() - badge_width - (8 if badge_width else 0)
        artist_text = artist_metrics.elidedText(
            self._artist, Qt.ElideRight, int(max(10, artist_width))
        )
        painter.drawText(
            QRectF(0, y, max(10, artist_width), artist_metrics.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            artist_text,
        )
        if badge_text and badge_width:
            from .common import paint_badge

            badge_x = min(
                rect.width() - badge_width,
                artist_metrics.horizontalAdvance(artist_text) + 8,
            )
            paint_badge(
                painter,
                QRectF(badge_x, y + 1, badge_width, max(14, artist_metrics.height())),
                badge_text,
                tone="accent",
            )
        elif self._active_source or self._badge:
            room = rect.width() - artist_metrics.horizontalAdvance(artist_text) - 10
            if room > 40:
                painter.setPen(QPen(rgba(palette.text, 0.28)))
                painter.drawText(
                    QRectF(artist_metrics.horizontalAdvance(artist_text) + 8, y, room,
                           artist_metrics.height()),
                    int(Qt.AlignLeft | Qt.AlignVCenter),
                    artist_metrics.elidedText(
                        "· " + (self._active_source or self._badge), Qt.ElideRight, int(room)
                    ),
                )
        painter.end()


class PlayerBar(QWidget):
    lyrics_clicked = Signal()
    queue_clicked = Signal()
    immersive_clicked = Signal()
    track_info_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._track: Track | None = None
        self._duration = 0
        self._seeking = False
        self._loading = False
        self.setMinimumHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, False)

        # Three-column grid: equal stretch on the outer columns keeps the
        # transport block exactly in the middle of the bar, while the left
        # cluster may grow to show long titles without pushing it off centre.
        grid = QGridLayout(self)
        grid.setContentsMargins(20, 12, 20, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)

        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        # ---------------------------------------------------------- left
        self.cover = CoverWidget(54, radius=8)
        self.cover.setCursor(Qt.PointingHandCursor)
        self.cover.clicked.connect(self.track_info_clicked)
        left.addWidget(self.cover, 0, Qt.AlignVCenter)

        self.info = TrackInfo()
        self.info.clicked.connect(self.track_info_clicked)
        left.addWidget(self.info, 1, Qt.AlignVCenter)
        self.favorite = IconButton("heart", size=28, icon_size=16, tooltip="添加到「我喜欢」")
        self.favorite.clicked.connect(self._toggle_favorite)
        left.addWidget(self.favorite, 0, Qt.AlignVCenter)
        grid.addLayout(left, 0, 0, Qt.AlignLeft)

        # ---------------------------------------------------------- centre
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(2)
        centre_layout.addStretch(1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(theme().scaled(14, factor=0.6))
        controls.addStretch(1)
        self.shuffle = IconButton("shuffle", size=30, icon_size=20, tooltip="随机播放", checkable=True)
        self.previous = IconButton("prev", size=32, icon_size=20, tooltip="上一首 (Ctrl+Left)")
        self.play = PlayButton(40)
        self.next = IconButton("next", size=32, icon_size=20, tooltip="下一首 (Ctrl+Right)")
        self.repeat = IconButton("repeat", size=30, icon_size=20, tooltip="循环播放", checkable=True)
        for widget in (self.shuffle, self.previous, self.play, self.next, self.repeat):
            controls.addWidget(widget, 0, Qt.AlignVCenter)
        controls.addStretch(1)
        centre_layout.addLayout(controls)

        progress = QHBoxLayout()
        progress.setContentsMargins(0, 0, 0, 0)
        progress.setSpacing(8)
        self.elapsed = TimeLabel(align_right=True)
        self.seek = SeekBar()
        self.total = TimeLabel(align_right=False)
        progress.addWidget(self.elapsed, 0)
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.total, 0)
        centre_layout.addLayout(progress)
        centre_layout.addStretch(1)
        self._centre = centre
        grid.addWidget(centre, 0, 1, Qt.AlignCenter)

        # ---------------------------------------------------------- right
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        self.lyrics_button = IconButton("lyrics", size=32, icon_size=17, tooltip="歌词 (Ctrl+L)")
        self.queue_button = IconButton("queue", size=32, icon_size=17, tooltip="播放队列 (Ctrl+Q)")
        self.mute = IconButton("volume", size=30, icon_size=16, tooltip="静音 (M)")
        self.volume = VolumeSlider()
        self.immersive = IconButton("immersive", size=32, icon_size=17, tooltip="沉浸式播放 (Ctrl+M)")
        for widget in (self.lyrics_button, self.queue_button, self.mute, self.volume, self.immersive):
            right.addWidget(widget, 0, Qt.AlignVCenter)
        grid.addLayout(right, 0, 2, Qt.AlignRight)
        self._grid = grid
        # Only the centre column absorbs slack, so the two side clusters keep
        # their natural widths instead of drifting towards the window edges.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)

        self._wire()

    # ------------------------------------------------------------------ wiring
    def _wire(self) -> None:
        try:
            player = ctx().player
        except Exception:
            return
        player.track_changed.connect(self._on_track)
        player.state_changed.connect(self._on_state)
        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(self._on_duration)
        player.volume_changed.connect(self._on_volume)
        player.muted_changed.connect(self._on_muted)
        player.queue_changed.connect(self._refresh_queue_badge)
        player.active_source_changed.connect(self.set_active_source)
        player.shuffle_changed.connect(self._on_shuffle)
        player.repeat_changed.connect(self._on_repeat)
        player.loading_changed.connect(self._on_loading)

        self.play.clicked.connect(player.toggle)
        self.previous.clicked.connect(lambda: player.previous())
        self.next.clicked.connect(lambda: player.next())
        self.shuffle.clicked.connect(player.toggle_shuffle)
        self.repeat.clicked.connect(player.cycle_repeat)
        self.seek.seek_requested.connect(self._seek)
        self.seek.drag_started.connect(self._seek_start)
        self.seek.drag_finished.connect(self._seek_end)
        self.mute.clicked.connect(player.toggle_mute)
        self.volume.value_changed.connect(player.set_volume)
        self.lyrics_button.clicked.connect(self.lyrics_clicked)
        self.queue_button.clicked.connect(self.queue_clicked)
        self.immersive.clicked.connect(self.immersive_clicked)

        self._on_track(player.current_track)
        self._on_volume(player.volume)
        self._on_muted(player.muted)
        self._refresh_queue_badge()
        self._on_state(player.engine.state)
        self._on_shuffle(player.shuffle)
        self._on_repeat(player.repeat)

    # ------------------------------------------------------------------ slots
    def _on_track(self, track: Track | None) -> None:
        self._track = track
        self.cover.set_track(track)
        self.info.set_track(track)
        self.info.set_status("")
        self._refresh_favorite()
        self._on_duration(track.duration_ms if track else 0)
        self._on_position(0)

    def refresh_track(self, track_id: str) -> None:
        """换源后同一首歌的封面/专辑可能已变，播放栏要跟着刷新。"""
        if self._track is None or self._track.id != str(track_id):
            return
        try:
            from ...ui.context import ctx

            fresh = ctx().library.tracks.get(str(track_id))
        except Exception:  # noqa: BLE001
            return
        if fresh is None:
            return
        self._track = fresh
        self.cover.set_track(fresh)
        self.info.set_track(fresh)

    def _on_state(self, state: str) -> None:
        self.play.set_playing(state == STATE_PLAYING)
        self._refresh_favorite()

    def _on_position(self, position: int) -> None:
        if not self._seeking:
            self.seek.set_position(position)
            self.elapsed.setText(format_duration(position))

    def _on_duration(self, duration: int) -> None:
        self._duration = duration
        self.seek.set_duration(duration)
        self.total.setText(format_duration(duration) if duration else "0:00")

    def _on_volume(self, value: float) -> None:
        self.volume.set_value(value)
        self._refresh_volume_icon()

    def _on_muted(self, muted: bool) -> None:
        self._refresh_volume_icon()

    def _refresh_volume_icon(self) -> None:
        player = ctx().player
        if player.muted or player.volume <= 0.001:
            self.mute.set_icon("volume_mute")
        else:
            self.mute.set_icon("volume")

    def _on_shuffle(self, enabled: bool) -> None:
        self.shuffle.setChecked(enabled)
        self.shuffle.setToolTip("随机播放：开" if enabled else "随机播放：关")

    def _on_repeat(self, mode: str) -> None:
        self.repeat.setChecked(mode != "off")
        if mode == "one":
            self.repeat.set_icon("repeat_one")
            self.repeat.setToolTip("单曲循环")
        else:
            self.repeat.set_icon("repeat")
            self.repeat.setToolTip("列表循环" if mode == "all" else "顺序播放")

    def _on_loading(self, loading: bool, message: str) -> None:
        self._loading = loading
        if loading:
            self.info.set_status("缓冲中")
        else:
            self.info.set_status("")
            self._restore_subtitle()

    def _restore_subtitle(self) -> None:
        track = self._track
        if track is None:
            self.info.set_subtitle("选择一首歌曲开始收听")
            return
        self.info.set_subtitle(track.display_artist)

    def set_active_source(self, name: str) -> None:
        self.info.set_active_source(name)

    def _refresh_queue_badge(self) -> None:
        try:
            count = ctx().player.queue.count
        except Exception:
            count = 0
        self.queue_button.setToolTip(f"播放队列（{count} 首）")

    def _refresh_favorite(self) -> None:
        if self._track is None:
            self.favorite.setEnabled(False)
            self.favorite.set_icon("heart")
            return
        self.favorite.setEnabled(True)
        try:
            favorite = ctx().library.is_favorite(self._track.id)
        except Exception:
            favorite = False
        self.favorite.set_icon("heart_fill" if favorite else "heart")
        self.favorite.setToolTip("取消喜欢" if favorite else "添加到「我喜欢」")

    def _toggle_favorite(self) -> None:
        if self._track is None:
            return
        app = ctx()
        app.library.set_favorite(self._track, not app.library.is_favorite(self._track.id))
        self._refresh_favorite()

    def _seek(self, value: int) -> None:
        ctx().player.seek(value)
        self.seek.set_position(value)
        self.elapsed.setText(format_duration(value))

    def _seek_start(self) -> None:
        self._seeking = True

    def _seek_end(self) -> None:
        self._seeking = False

    def refresh_theme(self) -> None:
        self.update()
        self.info.update()
        self.cover.update()

    def refresh_favorite(self) -> None:
        self._refresh_favorite()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.fillRect(rect, qcolor(palette.player))
        painter.setPen(QPen(rgba(palette.border, 0.8), 1))
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        wanted = theme().scaled(Metrics.player_h, factor=0.8)
        if self.height() != wanted:
            self.setFixedHeight(wanted)
        width = self.width()
        self.volume.setVisible(width >= 860)
        self.mute.setVisible(width >= 860)
        if not hasattr(self, "_centre"):
            return
        # Reserve the same width on both sides of the transport block so it
        # sits exactly in the middle of the bar; the title then uses whatever
        # is left of its own column (long names keep priority up to 520px).
        if width >= 900:
            centre_width = min(560, max(300, int(width * 0.30)))
        else:
            centre_width = min(320, max(240, int(width * 0.28)))
        self.favorite.setVisible(width >= 760)
        self._centre.setFixedWidth(centre_width)
        side = max(120, (width - 40 - 32 - centre_width) // 2)
        self._grid.setColumnMinimumWidth(0, side)
        self._grid.setColumnMinimumWidth(2, side)
        info_width = max(96, side - 54 - 28 - 24)
        self.info.setMinimumWidth(min(info_width, theme().scaled(150, factor=0.6)))
        self.info.setMaximumWidth(min(info_width, theme().scaled(200, factor=0.6)))


class TimeLabel(QWidget):
    def __init__(self, *, align_right: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = "0:00"
        self._align_right = align_right
        self.setFixedWidth(42)
        self.setFixedHeight(18)

    def setText(self, text: str) -> None:  # noqa: N802
        if text != self._text:
            self._text = text
            self.update()

    def text(self) -> str:
        return self._text

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setFont(theme().font(8.4, 500))
        painter.setPen(QPen(rgba(palette.text, 0.42)))
        align = (Qt.AlignRight if self._align_right else Qt.AlignLeft) | Qt.AlignVCenter
        painter.drawText(QRectF(self.rect()), int(align), self._text)
        painter.end()


__all__ = ["PlayerBar", "TrackInfo"]
