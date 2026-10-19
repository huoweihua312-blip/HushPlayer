"""Compact always-on-top player window."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..audio.engine import STATE_PLAYING
from ..core.theme import Metrics, css_rgba, rgba, theme
from ..model.track import Track, format_duration
from .context import ctx
from .widgets.common import IconButton, PlayButton
from .widgets.cover import CoverWidget
from .widgets.sliders import SeekBar


class MiniPlayer(QWidget):
    """Small window shown instead of the main window while listening."""

    closed = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFixedSize(380, 118)
        self._drag: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(12)
        self.cover = CoverWidget(64, radius=9)
        layout.addWidget(self.cover, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setContentsMargins(0, 2, 0, 0)
        right.setSpacing(2)
        self.title = QLabel("未在播放")
        self.title.setFont(theme().font(9.8, 600))
        self.artist = QLabel("")
        self.artist.setFont(theme().font(8.4))
        right.addWidget(self.title)
        right.addWidget(self.artist)
        right.addSpacing(2)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        self.previous = IconButton("prev", size=26, icon_size=14, tooltip="上一首")
        self.play = PlayButton(32)
        self.next = IconButton("next", size=26, icon_size=14, tooltip="下一首")
        self.restore = IconButton("restore", size=26, icon_size=13, tooltip="返回主界面")
        self.close_button = IconButton("close", size=26, icon_size=13, tooltip="关闭迷你播放器")
        for button in (self.previous, self.play, self.next):
            controls.addWidget(button)
        controls.addStretch(1)
        controls.addWidget(self.restore)
        controls.addWidget(self.close_button)
        right.addLayout(controls)

        self.seek = SeekBar()
        self.seek.setFixedHeight(14)
        right.addWidget(self.seek)
        layout.addLayout(right, 1)

        self.previous.clicked.connect(lambda: ctx().player.previous())
        self.next.clicked.connect(lambda: ctx().player.next())
        self.play.clicked.connect(lambda: ctx().player.toggle())
        self.restore.clicked.connect(self.close_to_main)
        self.close_button.clicked.connect(self.close_to_main)
        self.seek.seek_requested.connect(lambda value: ctx().player.seek(value))

        player = ctx().player
        player.track_changed.connect(self._on_track)
        player.state_changed.connect(self._on_state)
        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(self.seek.set_duration)
        self._wire_track(player.current_track)

    # ------------------------------------------------------------------ state
    def _wire_track(self, track: Track | None) -> None:
        self._on_track(track)

    def _on_track(self, track: Track | None) -> None:
        self.cover.set_track(track)
        self.title.setText(track.display_title if track else "未在播放")
        self.artist.setText(track.display_artist if track else "")
        self.title.setToolTip(self.title.text())
        self.seek.set_duration(track.duration_ms if track else 0)
        self.seek.set_position(0)
        self._restyle()

    def _on_state(self, state: str) -> None:
        self.play.set_playing(state == STATE_PLAYING)

    def _on_position(self, position: int) -> None:
        if not self.seek._dragging:
            self.seek.set_position(position)

    def _restyle(self) -> None:
        palette = theme().palette
        self.title.setStyleSheet(f"color:{css_rgba(palette.text, 0.96)};")
        self.artist.setStyleSheet(f"color:{css_rgba(palette.text, 0.55)};")

    # ------------------------------------------------------------------ window
    def show_player(self) -> None:
        self._restore_position()
        self.show()
        self.raise_()
        self.activateWindow()

    def close_to_main(self) -> None:
        self._save_position()
        self.hide()
        self.closed.emit()

    def _restore_position(self) -> None:
        settings = ctx().settings
        x = settings.get("general.mini_player_x", None)
        y = settings.get("general.mini_player_y", None)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            self.move(int(x), int(y))
            return
        screen = self.screen() or ctx().window.screen()
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 48, area.bottom() - self.height() - 64)

    def _save_position(self) -> None:
        settings = ctx().settings
        settings.set("general.mini_player_x", self.x())
        settings.set("general.mini_player_y", self.y())

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(rgba(palette.border_strong, 0.7))
        painter.setBrush(rgba(palette.elevated, 0.98))
        painter.drawRoundedRect(rect, Metrics.radius_lg, Metrics.radius_lg)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.childAt(event.position().toPoint()) is None:
            handle = getattr(self.windowHandle(), "startSystemMove", None)
            if handle is not None and handle():
                return
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.close_to_main()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close_to_main()
            return
        super().keyPressEvent(event)
