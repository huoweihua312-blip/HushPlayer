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
        self.setFixedSize(424, 140)
        self._drag: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 14, 14)
        layout.setSpacing(14)
        self.cover = CoverWidget(80, radius=12)
        layout.addWidget(self.cover, 0, Qt.AlignVCenter)

        right = QVBoxLayout()
        right.setContentsMargins(0, 1, 0, 0)
        right.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(6)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title = QLabel("未在播放")
        self.title.setFont(theme().font(10.2, 600))
        self.artist = QLabel("")
        self.artist.setFont(theme().font(8.8))
        titles.addWidget(self.title)
        titles.addWidget(self.artist)
        head.addLayout(titles, 1)

        self.restore = IconButton("restore", size=24, icon_size=12, tooltip="返回主界面")
        self.close_button = IconButton("close", size=24, icon_size=12, tooltip="关闭迷你播放器")
        head.addWidget(self.restore, 0, Qt.AlignTop)
        head.addWidget(self.close_button, 0, Qt.AlignTop)
        right.addLayout(head)
        right.addSpacing(4)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.seek = SeekBar()
        self.seek.setFixedHeight(16)
        self.total = QLabel("0:00")
        self.total.setFont(theme().font(8.2))
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.total, 0)
        right.addLayout(seek_row)
        right.addSpacing(2)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.previous = IconButton("prev", size=28, icon_size=15, tooltip="上一首")
        self.play = PlayButton(38)
        self.next = IconButton("next", size=28, icon_size=15, tooltip="下一首")
        self.elapsed = QLabel("0:00")
        self.elapsed.setFont(theme().font(8.2))
        controls.addWidget(self.previous)
        controls.addWidget(self.play)
        controls.addWidget(self.next)
        controls.addSpacing(6)
        controls.addWidget(self.elapsed)
        controls.addStretch(1)
        right.addLayout(controls)
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
        self.elapsed.setText("0:00")
        self.total.setText(format_duration(track.duration_ms if track else 0))
        self._restyle()

    def _on_state(self, state: str) -> None:
        self.play.set_playing(state == STATE_PLAYING)

    def _on_position(self, position: int) -> None:
        if not self.seek._dragging:
            self.seek.set_position(position)
        self.elapsed.setText(format_duration(position))

    def _restyle(self) -> None:
        palette = theme().palette
        self.title.setStyleSheet(f"color:{css_rgba(palette.text, 0.96)};")
        self.artist.setStyleSheet(f"color:{css_rgba(palette.text, 0.58)};")
        self.elapsed.setStyleSheet(f"color:{css_rgba(palette.text, 0.45)};")
        self.total.setStyleSheet(f"color:{css_rgba(palette.text, 0.45)};")

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
        painter.setPen(rgba(palette.border_strong, 0.55))
        painter.setBrush(rgba(palette.elevated, 0.99))
        painter.drawRoundedRect(rect, 18, 18)
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
