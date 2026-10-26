"""沉浸式播放器：全幕歌词（All Screen）与封面舞台（Cover Stage）。"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import icons
from ..core.logging_setup import log_exception
from ..core.theme import Metrics, css_rgba, mix, rgba, theme
from ..lyrics.service import STATUS_ERROR, STATUS_INSTRUMENTAL, STATUS_NONE, STATUS_OK, LyricsResult
from ..model.track import Track, format_duration
from .context import ctx
from .visuals import NEUTRAL_DARK, Mood, mood_for_pixmap, paint_ambient
from .widgets.common import IconButton, TextButton
from .widgets.cover import HeroCover
from .widgets.lyrics_view import LyricsView
from .widgets.sliders import SeekBar, VolumeSlider

STAGE_COVER_MAX = 448
COVER_MIN = 210


def _use_stage_colors(view) -> None:  # noqa: ANN001
    """The immersive stages are always dark, even in the light theme."""
    view.set_override_colors(
        active="#F7F4F5",
        inactive=rgba("#F7F4F5", 0.46),
        accent="#F2879B",
        trans=rgba("#F7F4F5", 0.42),
        trans_active=rgba("#F7F4F5", 0.62),
        hint=rgba("#F7F4F5", 0.34),
    )

class _MoodBackground(QWidget):
    """负责绘制氛围光的窗口底层。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mood = NEUTRAL_DARK
        self._previous = NEUTRAL_DARK
        self._mix = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(680)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_mix)
        self.strength = 1.0

    def set_mood(self, mood: Mood, *, animate: bool = True) -> None:
        if mood == self._mood:
            return
        self._previous = self._mood
        self._mood = mood
        if animate and not theme().reduce_motion:
            self._mix = 0.0
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self._mix = 1.0
            self.update()

    def _on_mix(self, value) -> None:
        self._mix = float(value)
        self.update()

    def snap_to(self, mood: Mood) -> None:
        """Apply a mood without any cross-fade.

        Used for the very first frame when the window opens: animating from the
        neutral near-black base produced a visible dark flash (BUG-01, measured
        ~0.4 s / luma 80 -> 33 in the recording).
        """
        self._anim.stop()
        self._previous = mood
        self._mood = mood
        self._mix = 1.0
        self.update()

    def mood(self) -> Mood:
        return self._mood

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor("#08080a"))
        if self._mix < 1.0:
            paint_ambient(painter, rect, self._previous, opacity=1.0 - self._mix, coverage=0.9)
        paint_ambient(painter, rect, self._mood, opacity=self._mix, coverage=0.9)
        painter.end()


class _GlowCover(QWidget):
    """带环境光晕的中心封面。"""

    clicked = Signal()

    def __init__(self, size: int = 340, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._cover = HeroCover(size, radius=16, parent=self)
        self._cover.clicked.connect(self.clicked)
        self._track = None
        self._mood = NEUTRAL_DARK
        self.setFixedSize(size + 120, size + 120)
        self._cover.move(60, 60)

    def set_track(self, track) -> None:
        self._track = track
        self._cover.set_track(track)
        if track is not None:
            try:
                pixmap = ctx().covers.pixmap(track, 96)
                self._mood = mood_for_pixmap(pixmap)
            except Exception:
                self._mood = NEUTRAL_DARK
        self.update()

    def set_size_ratio(self, factor: float) -> None:
        size = int(max(COVER_MIN, min(STAGE_COVER_MAX, self._size * factor)))
        if size == self._cover._size:
            return
        self._cover.setFixedSize(size, size)
        self._cover._size = size
        self._cover.refresh()
        self._size = size
        self.setFixedSize(size + 120, size + 120)
        self._cover.move(60, 60)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        center = rect.center()
        radius = max(rect.width(), rect.height()) * 0.55
        gradient = QRadialGradientCompat(center, radius)
        gradient.setColorAt(0.0, _alpha(self._mood.accent, 0.42))
        gradient.setColorAt(0.40, _alpha(self._mood.glow_a, 0.24))
        gradient.setColorAt(0.76, _alpha(self._mood.glow_a, 0.07))
        gradient.setColorAt(1.0, _alpha(self._mood.glow_a, 0.0))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        painter.end()


from PySide6.QtGui import QRadialGradient as QRadialGradientCompat  # noqa: E402
from .widgets.menu import themed_menu


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


class _TopBar(QWidget):
    mode_changed = Signal(str)
    close_requested = Signal()
    minimize_requested = Signal()
    queue_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setMouseTracking(True)
        self._drag_offset: QPoint | None = None
        self._mode = "cover"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 6)
        layout.setSpacing(6)

        self.collapse = IconButton("chevron_down", size=32, icon_size=18, tooltip="退出沉浸模式 (Esc)")
        self.collapse.clicked.connect(self.close_requested)
        layout.addWidget(self.collapse)

        self.brand = QLabel("HushPlayer", self)
        self.brand.setStyleSheet(f"color:{css_rgba('#ffffff', 0.34)};font-size:{theme().pt(9):.1f}pt;")
        layout.addWidget(self.brand)
        layout.addStretch(1)

        self.stage_button = IconButton("disc", size=34, icon_size=18, tooltip="封面舞台 (1)", checkable=True)
        self.stage_button.clicked.connect(lambda: self._pick("cover"))
        self.lyrics_button = IconButton("lyrics", size=34, icon_size=18, tooltip="全幕歌词 (2)", checkable=True)
        self.lyrics_button.clicked.connect(lambda: self._pick("lyrics"))
        layout.addWidget(self.stage_button)
        layout.addWidget(self.lyrics_button)
        layout.addSpacing(10)

        self.queue_button = IconButton("queue", size=32, icon_size=18, tooltip="播放队列")
        self.queue_button.clicked.connect(self.queue_requested)
        layout.addWidget(self.queue_button)

        self.settings_button = IconButton("settings", size=32, icon_size=17, tooltip="歌词与画面设置")
        self.settings_button.clicked.connect(self.settings_requested)
        layout.addWidget(self.settings_button)

        self.minimize_button = IconButton("minimize", size=32, icon_size=16, tooltip="最小化")
        self.minimize_button.clicked.connect(self.minimize_requested)
        self.close_button = _RoundWindowButton("close", danger=True, tooltip="退出沉浸模式")
        self.close_button.clicked.connect(self.close_requested)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.close_button)
        self.set_mode("cover")

    def _pick(self, mode: str) -> None:
        self.set_mode(mode)
        self.mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.stage_button.setChecked(mode == "cover")
        self.lyrics_button.setChecked(mode == "lyrics")

    def set_track_title(self, text: str) -> None:
        self.brand.setText(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(0, 0, 0, 96))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), gradient)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.childAt(event.position().toPoint()) is None:
            window = self.window()
            handle = getattr(window, "windowHandle", lambda: None)()
            if handle is not None and handle.startSystemMove():
                return
            self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class _RoundWindowButton(IconButton):
    def __init__(self, icon_name: str, *, danger: bool = False, tooltip: str = "") -> None:
        super().__init__(icon_name, size=32, icon_size=15, tooltip=tooltip)
        self._danger = danger

    def _current_color(self):
        if self._danger and self._hover.value > 0.4:
            return QColor("#ffffff")
        return rgba("#ffffff", 0.72)

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF as _RectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self._danger and self._hover.value > 0.05:
            color = QColor("#e5484d")
            color.setAlphaF(0.9 * self._hover.value)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)
        elif self._hover.value > 0.02:
            painter.setBrush(rgba("#ffffff", 0.12 * self._hover.value))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)
        size = 14.0
        target = QRectF(0, 0, size, size)
        target.moveCenter(QRectF(self.rect()).center())
        icons.draw(painter, self._icon_name, target, self._current_color())
        painter.end()


class _CoverStage(QWidget):
    """模式 B：居中封面舞台。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._track: Track | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 6, 40, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        self.cover = _GlowCover(STAGE_COVER_MAX, self)
        self.cover.clicked.connect(lambda: self.info_title.setFocus())
        layout.addWidget(self.cover, 0, Qt.AlignHCenter)
        layout.addSpacing(10)

        self.info_title = QLabel("未在播放", self)
        self.info_title.setAlignment(Qt.AlignHCenter)
        self.info_title.setWordWrap(True)
        layout.addWidget(self.info_title)

        self.info_artist = QLabel("", self)
        self.info_artist.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.info_artist)

        self.info_album = QLabel("", self)
        self.info_album.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.info_album)

        layout.addSpacing(18)
        self.lyrics = LyricsView(self, centered=True)
        self.lyrics.setFixedHeight(178)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.74)
        self.lyrics.set_show_translation(False)
        self.lyrics.set_padding_ratio(0.16, 0.30)
        _use_stage_colors(self.lyrics)
        layout.addWidget(self.lyrics)
        layout.addStretch(1)
        self.refresh_theme()

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.cover.set_track(track)
        if track is None:
            self.info_title.setText("未在播放")
            self.info_artist.setText("")
            self.info_album.setText("")
            return
        self.info_title.setText(track.title or "未知歌曲")
        self.info_artist.setText(track.artist or "未知艺术家")
        self.info_album.setText(track.album or "")

    def set_document(self, document) -> None:
        self.lyrics.set_document(document)
        visible = bool(document and document.lines)
        self.lyrics.setVisible(visible)

    def set_position(self, position: int) -> None:
        self.lyrics.set_position(position)

    def set_translation(self, enabled: bool) -> None:
        self.lyrics.set_show_translation(enabled)

    def refresh_theme(self) -> None:
        self.info_title.setStyleSheet(
            f"color:#ffffff;font-size:{max(20.0, 25 * theme().type_scale):.1f}pt;font-weight:700;"
        )
        self.info_artist.setStyleSheet(
            f"color:{css_rgba('#ffffff', 0.66)};font-size:{12.4 * theme().type_scale:.1f}pt;"
        )
        self.info_album.setStyleSheet(
            f"color:{css_rgba('#ffffff', 0.38)};font-size:{9.4 * theme().type_scale:.1f}pt;"
        )
        self.lyrics.refresh_theme()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        height = self.height()
        ratio = 1.0
        if height < 620:
            ratio = 0.82
        elif height < 720:
            ratio = 0.92
        self.cover.set_size_ratio(ratio)


class _LyricsStage(QWidget):
    """模式 A：全幕歌词。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(54, 4, 54, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 8)
        header.setSpacing(12)
        self.cover = HeroCover(64, radius=10, parent=self)
        header.addWidget(self.cover, 0, Qt.AlignVCenter)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.info_title = QLabel("", self)
        self.info_artist = QLabel("", self)
        text_box.addWidget(self.info_title)
        text_box.addWidget(self.info_artist)
        header.addLayout(text_box)
        header.addStretch(1)
        self.source_label = QLabel("", self)
        header.addWidget(self.source_label)
        layout.addLayout(header)

        self.lyrics = LyricsView(self, centered=True)
        self.lyrics.set_font_scale(1.55)
        _use_stage_colors(self.lyrics)
        layout.addWidget(self.lyrics, 1)
        self.refresh_theme()

    def set_track(self, track: Track | None) -> None:
        self.cover.set_track(track)
        if track is None:
            self.info_title.setText("未在播放")
            self.info_artist.setText("")
            return
        self.info_title.setText(track.title or "未知歌曲")
        self.info_artist.setText(track.artist or "未知艺术家")

    def set_document(self, document, provider: str = "") -> None:
        self.lyrics.set_document(document)
        self.source_label.setText(provider)

    def set_position(self, position: int) -> None:
        self.lyrics.set_position(position)

    def set_translation(self, enabled: bool) -> None:
        self.lyrics.set_show_translation(enabled)

    def refresh_theme(self) -> None:
        self.info_title.setStyleSheet(
            f"color:#ffffff;font-size:{13.0 * theme().type_scale:.1f}pt;font-weight:600;"
        )
        self.info_artist.setStyleSheet(
            f"color:{css_rgba('#ffffff', 0.55)};font-size:{9.2 * theme().type_scale:.1f}pt;"
        )
        self.source_label.setStyleSheet(
            f"color:{css_rgba('#ffffff', 0.32)};font-size:{8.6 * theme().type_scale:.1f}pt;"
        )
        self.lyrics.refresh_theme()


class _ControlsBar(QWidget):
    """沉浸模式底部控制区。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(112)
        player = ctx().player

        layout = QVBoxLayout(self)
        layout.setContentsMargins(46, 4, 46, 12)
        layout.setSpacing(6)

        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(0, 0, 0, 0)
        seek_row.setSpacing(12)
        self.time_now = _MonoLabel("0:00")
        self.time_total = _MonoLabel("0:00")
        self.seek = SeekBar(self)
        seek_row.addWidget(self.time_now, 0, Qt.AlignVCenter)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.time_total, 0, Qt.AlignVCenter)
        layout.addLayout(seek_row)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.volume_icon = IconButton("volume", size=32, icon_size=18, tooltip="静音")
        self.volume_icon.clicked.connect(player.toggle_mute)
        self.volume = VolumeSlider(self)
        row.addWidget(self.volume_icon)
        row.addWidget(self.volume)
        row.addStretch(1)

        self.shuffle = IconButton("shuffle", size=34, icon_size=18, tooltip="随机播放")
        self.shuffle.clicked.connect(player.toggle_shuffle)
        self.previous = IconButton("prev", size=38, icon_size=20, tooltip="上一首")
        self.previous.clicked.connect(lambda: player.previous())
        self.play = _BigPlayButton(self)
        self.play.clicked.connect(player.toggle)
        self.next = IconButton("next", size=38, icon_size=20, tooltip="下一首")
        self.next.clicked.connect(lambda: player.next())
        self.repeat = IconButton("repeat", size=34, icon_size=18, tooltip="循环模式")
        self.repeat.clicked.connect(player.cycle_repeat)
        for widget in (self.shuffle, self.previous, self.play, self.next, self.repeat):
            row.addWidget(widget)
        row.addStretch(1)

        self.translate = IconButton("translate", size=32, icon_size=18, tooltip="翻译", checkable=True)
        self.translate.clicked.connect(self._on_translate)
        self.desktop = IconButton("monitor", size=32, icon_size=18, tooltip="桌面歌词")
        self.desktop.clicked.connect(self._on_desktop)
        self.queue = IconButton("queue", size=32, icon_size=18, tooltip="播放队列")
        self.queue.clicked.connect(self._on_queue)
        self.fullscreen = IconButton("maximize", size=32, icon_size=16, tooltip="全屏 (F11)")
        self.fullscreen.clicked.connect(self._on_fullscreen)
        for widget in (self.translate, self.desktop, self.queue, self.fullscreen):
            row.addWidget(widget)
        layout.addLayout(row)

        self.queue_requested = self._on_queue
        self.desktop_requested = self._on_desktop
        self.fullscreen_requested = self._on_fullscreen

        self.volume.set_value(player.volume)
        self.seek.seek_requested.connect(player.seek)
        self.seek.drag_started.connect(lambda: self._set_dragging(True))
        self.seek.drag_finished.connect(lambda: self._set_dragging(False))
        self.volume.value_changed.connect(player.set_volume)
        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(self._on_duration)
        player.state_changed.connect(self._on_state)
        player.volume_changed.connect(self._on_volume)
        player.muted_changed.connect(self._on_muted)
        player.shuffle_changed.connect(self._sync_modes)
        player.repeat_changed.connect(self._sync_modes)
        self._dragging = False
        self._position = 0

        self.refresh_theme()
        self._sync_modes()

    # ------------------------------------------------------------------ 同步
    def sync_from_player(self) -> None:
        player = ctx().player
        self._on_duration(player.duration)
        self._on_position(player.position)
        self._on_volume(player.volume)
        self._on_muted(player.muted)
        self._on_state(player.state)
        self._sync_modes()

    def _on_position(self, position: int) -> None:
        self._position = position
        if not self._dragging:
            self.seek.set_position(position)
            self.time_now.setText(format_duration(position))

    def _on_duration(self, duration: int) -> None:
        self.seek.set_duration(max(0, duration))
        self.time_total.setText(format_duration(max(0, duration)))

    def _on_state(self, state: str) -> None:
        self.play.set_playing(state == "playing")

    def _on_volume(self, volume: float) -> None:
        self.volume.set_value(volume)
        self._sync_volume_icon()

    def _on_muted(self, muted: bool) -> None:
        self._sync_volume_icon()

    def _sync_volume_icon(self) -> None:
        player = ctx().player
        muted = player.muted or player.volume <= 0.001
        self.volume_icon.set_icon("volume_mute" if muted else "volume")

    def _sync_modes(self, *_args) -> None:
        player = ctx().player
        self.shuffle.setChecked(player.shuffle)
        mode = player.repeat
        self.repeat.set_icon("repeat_one" if mode == "one" else "repeat")
        self.repeat.setChecked(mode != "off")

    def _set_dragging(self, dragging: bool) -> None:
        self._dragging = dragging
        if not dragging:
            self.seek.set_position(self._position)

    def _on_translate(self, checked: bool) -> None:
        ctx().settings.set("lyrics.translate", bool(checked))
        if not checked:
            return
        document = self._document
        if document is None or document.is_empty() or document.has_translation:
            return
        if self._track is None:
            return
        self.controls.translate.setEnabled(False)
        ctx().lyrics.translate(self._track, document)

    def _on_desktop(self) -> None:
        window = getattr(ctx(), "desktop_lyrics", None)
        if window is not None:
            window.toggle()

    def _on_queue(self) -> None:
        window = self.window()
        handler = getattr(window, "toggle_queue", None)
        if callable(handler):
            handler()

    def _on_fullscreen(self) -> None:
        window = self.window()
        handler = getattr(window, "toggle_fullscreen", None)
        if callable(handler):
            handler()

    def refresh_theme(self) -> None:
        self.play.refresh_theme()


class _MonoLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedWidth(40)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"color:{css_rgba('#ffffff', 0.45)};font-size:{theme().pt(9):.1f}pt;")


class _BigPlayButton(IconButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("play", size=52, icon_size=24, tooltip="播放 / 暂停")
        self._playing = False
        self.setCursor(Qt.PointingHandCursor)

    def set_playing(self, playing: bool) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        self.update()

    def refresh_theme(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF as _RectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        hover = self._hover.value
        base = QColor("#ffffff")
        base.setAlphaF(0.14 + 0.10 * hover)
        painter.setBrush(base)
        painter.setPen(QPen(rgba("#ffffff", 0.18 + 0.16 * hover), 1.0))
        painter.drawEllipse(rect)
        size = 22.0
        target = QRectF(0, 0, size, size)
        target.moveCenter(QRectF(self.rect()).center())
        painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)
        icons.draw(painter, "pause" if self._playing else "play", target, QColor("#ffffff"))
        painter.end()


class ImmersiveWindow(QWidget):
    """独立的全屏沉浸式播放窗口。"""

    closed = Signal()

    MODE_COVER = "cover"
    MODE_LYRICS = "lyrics"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle("HushPlayer · 沉浸模式")
        self.setMinimumSize(900, 620)
        self._track: Track | None = None
        self._mode = self.MODE_COVER
        self._document = None
        self._fullscreen = False
        self._queue_panel = None

        self.background = _MoodBackground(self)
        self.background.lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = _TopBar(self)
        self.topbar.mode_changed.connect(self.set_mode)
        self.topbar.close_requested.connect(self.close_immersive)
        self.topbar.minimize_requested.connect(self.showMinimized)
        self.topbar.queue_requested.connect(self.toggle_queue)
        self.topbar.settings_requested.connect(self.show_quick_settings)
        root.addWidget(self.topbar)

        self.stack = QStackedWidget(self)
        self.stage = _CoverStage(self)
        self.lyrics_stage = _LyricsStage(self)
        self.stack.addWidget(self.stage)
        self.stack.addWidget(self.lyrics_stage)
        root.addWidget(self.stack, 1)

        self.controls = _ControlsBar(self)
        root.addWidget(self.controls)


        player = ctx().player
        player.track_changed.connect(self._on_track_changed)
        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(lambda _d: self._update_track_meta())
        player.state_changed.connect(self._on_state)
        ctx().lyrics.resolved.connect(self._on_lyrics_resolved)
        ctx().lyrics.translation_started.connect(self._on_translation_started)
        ctx().lyrics.translation_ready.connect(self._on_translation_ready)
        ctx().lyrics.translation_failed.connect(self._on_translation_failed)
        ctx().settings.changed.connect(self._on_setting)

        self._build_shortcuts()
        self._restore_mode()

    # ------------------------------------------------------------------ 构建
    def _build_shortcuts(self) -> None:
        player = ctx().player
        shortcuts = (
            ("Esc", self.close_immersive),
            ("Space", player.toggle),
            ("Left", lambda: player.skip_by(-5)),
            ("Right", lambda: player.skip_by(5)),
            ("Ctrl+Left", lambda: player.previous()),
            ("Ctrl+Right", lambda: player.next()),
            ("Up", lambda: player.set_volume(min(1.0, player.volume + 0.05))),
            ("Down", lambda: player.set_volume(max(0.0, player.volume - 0.05))),
            ("M", player.toggle_mute),
            ("S", player.toggle_shuffle),
            ("R", player.cycle_repeat),
            ("Q", self.toggle_queue),
            ("F", self.toggle_fullscreen),
            ("F11", self.toggle_fullscreen),
            ("Ctrl+W", self.close_immersive),
            ("1", lambda: self.set_mode(self.MODE_COVER)),
            ("2", lambda: self.set_mode(self.MODE_LYRICS)),
            ("L", self.cycle_mode),
        )
        self._shortcuts = []
        for sequence, handler in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _restore_mode(self) -> None:
        mode = str(ctx().settings.get("immersive.mode", "cover") or "cover")
        self._mode = mode if mode in (self.MODE_COVER, self.MODE_LYRICS) else self.MODE_COVER
        self.topbar.set_mode(self._mode)
        self.stack.setCurrentIndex(0 if self._mode == self.MODE_COVER else 1)
        self.controls.translate.setChecked(bool(ctx().settings.get("lyrics.translate", True)))

    # ------------------------------------------------------------------ 模式
    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str, *, animate: bool = True) -> None:
        if mode not in (self.MODE_COVER, self.MODE_LYRICS):
            return
        if mode == self._mode and self.stack.currentIndex() == (0 if mode == self.MODE_COVER else 1):
            self.topbar.set_mode(mode)
            return
        self._mode = mode
        self.topbar.set_mode(mode)
        ctx().settings.set("immersive.mode", mode)
        index = 0 if mode == self.MODE_COVER else 1
        if not animate or theme().reduce_motion:
            self.stack.setCurrentIndex(index)
            return
        # Capture the outgoing stage and fade that bitmap out on top of the
        # incoming one. Never put a QGraphicsOpacityEffect on live widgets: the
        # offscreen surface it forces flickers while lyrics repaint at 60 Hz.
        try:
            snapshot = self.stack.grab()
        except Exception:  # noqa: BLE001
            snapshot = None
        self.stack.setCurrentIndex(index)
        if snapshot is not None and not snapshot.isNull():
            from .widgets.transition import FadeOverlay

            overlay = FadeOverlay(self, snapshot)
            overlay.setGeometry(self.stack.geometry())
            overlay.start()

    def cycle_mode(self) -> None:
        self.set_mode(self.MODE_LYRICS if self._mode == self.MODE_COVER else self.MODE_COVER)

    # ------------------------------------------------------------------ 窗口
    def open_immersive(self) -> None:
        window = ctx().window
        screen = window.screen() if window is not None else self.screen()
        if screen is not None:
            geometry = screen.availableGeometry()
            self.setGeometry(geometry)
        self._restore_mode()
        # BUG-01: build the complete first frame *before* the window is mapped.
        # Showing first and filling it afterwards produced a black frame plus a
        # 680 ms mood cross-fade from near-black every time the player opened.
        self._on_track_changed(ctx().player.current, force=True, animate_mood=False)
        self.set_mode(self._mode, animate=False)
        self.controls.sync_from_player()
        self._on_state(ctx().player.state)
        self._on_position(ctx().player.position)
        self._update_track_meta()
        # A frameless top-level window is mapped with the platform background
        # for at least one frame; make that frame the mood base colour instead
        # of the default white so entering the player can never flash white.
        try:
            from PySide6.QtGui import QColor, QPalette

            pal = self.palette()
            base = QColor(self.background.mood.base)
            pal.setColor(QPalette.Window, base)
            self.setPalette(pal)
            self.setAutoFillBackground(True)
        except Exception:  # noqa: BLE001
            pass
        self.ensurePolished()
        self.layout().activate()
        # force layout + cover/lyrics rasterisation into the backing store so the
        # first mapped frame already has content
        self.grab()
        self.show()
        self.raise_()
        self.activateWindow()

    def close_immersive(self) -> None:
        if self._fullscreen:
            self.showNormal()
            self._fullscreen = False
        self.hide()
        self.closed.emit()

    def toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self.showNormal()
            self._fullscreen = False
        else:
            self.showFullScreen()
            self._fullscreen = True

    def show_quick_settings(self) -> None:
        """Small popover: lyrics size/translation/alignment and background."""
        from PySide6.QtWidgets import QMenu

        from ..core.theme import theme

        settings = ctx().settings
        menu = themed_menu(self)
        header = menu.addAction("歌词与画面")
        header.setEnabled(False)
        menu.addSeparator()

        scale = float(settings.get("lyrics.font_scale", 1.0) or 1.0)
        bigger = menu.addAction("放大歌词")
        smaller = menu.addAction("缩小歌词")
        bigger.triggered.connect(lambda: self._nudge_lyrics_scale(0.1))
        smaller.triggered.connect(lambda: self._nudge_lyrics_scale(-0.1))

        translate = menu.addAction("显示翻译")
        translate.setCheckable(True)
        translate.setChecked(bool(settings.get("lyrics.translate", True)))
        translate.toggled.connect(lambda value: settings.set("lyrics.translate", bool(value)))

        align = menu.addAction("左对齐歌词")
        align.setCheckable(True)
        align.setChecked(str(settings.get("lyrics.alignment", "center")) == "left")
        align.toggled.connect(
            lambda value: settings.set("lyrics.alignment", "left" if value else "center")
        )

        menu.addSeparator()
        switch = menu.addAction("切换全幕歌词" if self._mode == self.MODE_COVER else "切换封面舞台")
        switch.triggered.connect(
            lambda: self.set_mode(self.MODE_LYRICS if self._mode == self.MODE_COVER else self.MODE_COVER)
        )
        self._quick_menu = menu
        menu.popup(self.topbar.settings_button.mapToGlobal(self.topbar.settings_button.rect().bottomLeft()))

    def _nudge_lyrics_scale(self, delta: float) -> None:
        settings = ctx().settings
        current = float(settings.get("lyrics.font_scale", 1.0) or 1.0)
        value = max(0.7, min(2.0, round(current + delta, 2)))
        settings.set("lyrics.font_scale", value)

    def toggle_queue(self) -> None:
        from .widgets.queue_panel import QueuePanel

        if self._queue_panel is None:
            self._queue_panel = QueuePanel(self, immersive=True)
            self._queue_panel.close_requested.connect(self._hide_queue)
        if self._queue_panel.isVisible():
            self._hide_queue()
            return
        self._queue_panel.activate_palette()
        self._queue_panel.refresh()
        self._queue_panel.refresh_theme()
        self._queue_panel.setGeometry(
            self.width() - self._queue_panel.width(),
            self.topbar.height(),
            self._queue_panel.width(),
            max(160, self.height() - self.controls.height() - self.topbar.height()),
        )
        self._queue_panel.show()
        self._queue_panel.raise_()

    def _hide_queue(self) -> None:
        if self._queue_panel is not None:
            self._queue_panel.hide()
            self._queue_panel.release_palette()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.background.setGeometry(self.rect())
        if self._queue_panel is not None and self._queue_panel.isVisible():
            self.toggle_queue()
            self.toggle_queue()

    # ------------------------------------------------------------------ 同步
    def _on_track_changed(self, track: Track | None, *, force: bool = False,
                          animate_mood: bool = True) -> None:
        if track is self._track and not force:
            return
        self._track = track
        self._document = None
        self.stage.set_track(track)
        self.lyrics_stage.set_track(track)
        mood = NEUTRAL_DARK
        if track is not None:
            try:
                mood = mood_for_pixmap(ctx().covers.pixmap(track, 96))
            except Exception:
                mood = NEUTRAL_DARK
        if animate_mood:
            self.background.set_mood(mood)
        else:
            self.background.snap_to(mood)
        self.stage.set_document(None)
        self.lyrics_stage.set_document(None)
        if track is not None:
            try:
                result = ctx().lyrics.request(track)
                if result is not None and result.track_id == track.id:
                    self._apply_lyrics(result)
            except Exception as exc:  # noqa: BLE001
                log_exception("沉浸模式获取歌词失败", exc)
        self._update_track_meta()

    def _on_lyrics_resolved(self, result: LyricsResult) -> None:
        if self._track is None or result.track_id != self._track.id:
            return
        self._apply_lyrics(result)

    def _apply_lyrics(self, result: LyricsResult) -> None:
        self._document = result.document
        provider = _provider_label(result)
        good = result.status == STATUS_OK and result.document is not None and not result.document.is_empty()
        if good:
            self.stage.set_document(result.document)
            self.lyrics_stage.set_document(result.document, provider)
            translate = bool(ctx().settings.get("lyrics.translate", True)) and result.document.has_translation
            self.stage.set_translation(translate)
            self.lyrics_stage.set_translation(translate)
            self.controls.translate.setChecked(translate)
            self.controls.translate.setEnabled(True)
            return
        self.stage.set_document(None)
        self.lyrics_stage.set_document(None, "")
        if result.status == STATUS_INSTRUMENTAL:
            self.lyrics_stage.lyrics.set_empty_text("纯音乐", "这首歌没有歌词，请静候")
        elif result.status == STATUS_ERROR:
            self.lyrics_stage.lyrics.set_empty_text("歌词加载失败", result.message or "")
        else:
            self.lyrics_stage.lyrics.set_empty_text("暂无歌词", result.message or "")
        self.controls.translate.setEnabled(False)

    def _on_translation_started(self, track_id: str) -> None:
        if self._track is None or str(track_id) != self._track.id:
            return
        self.controls.translate.setEnabled(False)

    def _on_translation_ready(self, result: LyricsResult) -> None:
        if self._track is None or result.track_id != self._track.id:
            return
        self._apply_lyrics(result)
        self.controls.translate.setEnabled(True)
        self.controls.translate.setChecked(True)

    def _on_translation_failed(self, message: str) -> None:
        self.controls.translate.setChecked(False)
        self.controls.translate.setEnabled(self._document is not None)
        window = self.window()
        toast = getattr(window, "toast", None)
        if callable(toast):
            toast(message or "翻译失败", "warning")

    def _on_position(self, position: int) -> None:
        self.stage.set_position(position)
        self.lyrics_stage.set_position(position)

    def _on_state(self, state: str) -> None:
        self.controls.play.set_playing(state == "playing")

    def _update_track_meta(self) -> None:
        track = self._track
        if track is None:
            self.topbar.set_track_title("HushPlayer")
            return
        self.topbar.set_track_title(f"HushPlayer · {track.title}")

    def _on_setting(self, key: str, value: object) -> None:
        if key in ("appearance.reduce_motion", "appearance.font_scale", "appearance.theme"):
            self.stage.refresh_theme()
            self.lyrics_stage.refresh_theme()
            self.controls.refresh_theme()
        elif key == "lyrics.translate":
            enabled = bool(value)
            self.stage.set_translation(enabled)
            self.lyrics_stage.set_translation(enabled)
            self.controls.translate.setChecked(enabled)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._queue_panel is not None:
            self._queue_panel.release_palette()
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close_immersive()
            return
        super().keyPressEvent(event)


def _provider_label(result: LyricsResult) -> str:
    from .pages.lyrics import PROVIDER_LABELS

    if result.provider:
        return PROVIDER_LABELS.get(result.provider, result.provider)
    return ""
