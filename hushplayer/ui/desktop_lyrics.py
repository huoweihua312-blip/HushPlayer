"""桌面悬浮歌词窗口。

独立的无边框置顶窗口，与主窗口、沉浸式播放器互不依赖：
- 支持单行 / 双行、逐字（词）高亮、翻译；
- 可拖动、可锁定、可鼠标穿透；
- 字体大小 / 颜色 / 不透明度由设置中心驱动。

窗口本身不持有播放逻辑，只订阅 ``PlayerController`` 与 ``LyricsService`` 的信号。
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from ..core.logging_setup import get_logger, log_exception
from ..core.theme import rgba, theme
from .widgets.sweep import paint_sweep, sweep_pixels_for_line
from ..model.lyrics import LyricDocument
from ..model.track import Track
from .context import ctx

log = get_logger(__name__)

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020


def ensure_desktop_lyrics() -> "DesktopLyricsWindow | None":
    """返回（必要时创建）桌面歌词窗口。"""
    existing = getattr(ctx(), "desktop_lyrics", None)
    if existing is not None:
        return existing
    try:
        window = DesktopLyricsWindow()
    except Exception as exc:  # noqa: BLE001
        log_exception("创建桌面歌词窗口失败", exc)
        return None
    ctx().desktop_lyrics = window
    return window


class DesktopLyricsWindow(QWidget):
    """置顶的桌面歌词条。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)

        self._track: Track | None = None
        self._document: LyricDocument | None = None
        self._position = 0
        self._drag_offset: QPoint | None = None
        self._drag_started = False
        self._settings = ctx().settings
        self._lines = 2
        self._font_size = 32
        self._color = "#FFFFFF"
        self._highlight = "#C95770"
        self._show_translation = True
        self._opacity = 0.94
        self._locked = False
        self._click_through = False

        self._restore_position()
        self.apply_settings()
        self._wire()

    # ------------------------------------------------------------------ wiring
    def _wire(self) -> None:
        player = ctx().player
        player.track_changed.connect(self._on_track_changed)
        player.position_changed.connect(self._on_position)
        clock = ctx().clock
        if clock is not None:
            clock.tick.connect(self._on_clock_tick)
        player.state_changed.connect(self._on_state)
        ctx().lyrics.resolved.connect(self._on_lyrics)
        self._settings.changed.connect(self._on_setting_changed)
        self._position = player.position
        current = player.current
        if current is not None:
            self._on_track_changed(current)

    def _on_setting_changed(self, key: str, _value: Any) -> None:
        if key.startswith("desktop_lyrics."):
            self.apply_settings()

    def _on_track_changed(self, track: Track | None) -> None:
        self._track = track
        self._document = None
        self._position = 0
        if track is None:
            self.update()
            return
        cached = ctx().lyrics.cached(track.id)
        if cached is not None and cached.document is not None:
            self._document = cached.document
        else:
            ctx().lyrics.request(track)
        self.update()

    def _on_lyrics(self, result: Any) -> None:
        track = self._track
        if track is None or getattr(result, "track_id", "") != track.id:
            return
        self._document = getattr(result, "document", None)
        self.update()

    def _on_position(self, position: int) -> None:
        self._position = max(0, int(position))
        if self.isVisible():
            self.update()

    def _on_clock_tick(self, position_ms: int) -> None:
        """60 Hz interpolated position keeps the karaoke sweep continuous (BUG-06)."""
        if not self.isVisible() or self._document is None:
            return
        if position_ms == self._position:
            return
        self._position = position_ms
        self.update()

    def _on_state(self, _state: str) -> None:
        if self.isVisible():
            self.update()

    # ------------------------------------------------------------------ config
    def apply_settings(self) -> None:
        settings = self._settings
        self._lines = 2 if int(settings.get("desktop_lyrics.lines", 2) or 2) >= 2 else 1
        self._font_size = max(14, int(settings.get("desktop_lyrics.font_size", 32) or 32))
        self._color = str(settings.get("desktop_lyrics.color", "#FFFFFF") or "#FFFFFF")
        self._highlight = str(settings.get("desktop_lyrics.highlight_color", "#C95770") or "#C95770")
        self._show_translation = bool(settings.get("desktop_lyrics.show_translation", True))
        self._opacity = max(0.2, min(1.0, float(settings.get("desktop_lyrics.opacity", 0.94) or 0.94)))
        self._locked = bool(settings.get("desktop_lyrics.locked", False))
        self._click_through = bool(settings.get("desktop_lyrics.click_through", False))
        self.setWindowOpacity(self._opacity)
        self._apply_flags()
        self._resize_for_content()
        self.update()

    def _apply_flags(self) -> None:
        always_on_top = bool(self._settings.get("desktop_lyrics.always_on_top", True))
        flags = self.windowFlags()
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        if flags != self.windowFlags():
            self.setWindowFlags(flags)
            if self.isVisible():
                self.show()
        self._apply_click_through(self._click_through)

    def _apply_click_through(self, enabled: bool) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            if enabled:
                style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
            else:
                style &= ~_WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
        except Exception as exc:  # noqa: BLE001
            log.warning("设置鼠标穿透失败: %s", exc)

    def _metrics_slots(self) -> tuple[int, int, int, int]:
        """返回 (padding, 主行高, 翻译行高, 下一行高)。"""
        fs = self._font_size
        pad = max(6, int(fs * 0.26))
        main_h = int(fs * 1.34)
        trans_h = int(fs * 0.64) if self._show_translation else 0
        next_h = int(fs * 0.98) if self._lines >= 2 else 0
        return pad, main_h, trans_h, next_h

    def _resize_for_content(self) -> None:
        screen = self._screen()
        width = int(min(max(680, screen.availableGeometry().width() * 0.56), 1500))
        pad, main_h, trans_h, next_h = self._metrics_slots()
        height = pad * 2 + main_h + trans_h + next_h
        self.resize(width, max(76, height))

    def _screen(self):
        screen = self.screen() if self.isVisible() else None
        return screen or QGuiApplication.primaryScreen()

    def _restore_position(self) -> None:
        settings = self._settings
        x = settings.get("desktop_lyrics.x", None)
        y = settings.get("desktop_lyrics.y", None)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            self.move(int(x), int(y))
            self._clamp_to_screen()
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = int(min(max(680, area.width() * 0.56), 1500))
        height = 120
        self.resize(width, height)
        self.move(area.center().x() - width // 2, area.bottom() - height - 140)

    def _clamp_to_screen(self) -> None:
        point = self.pos()
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().contains(point + QPoint(40, 20)):
                area = screen.availableGeometry()
                x = max(area.left(), min(point.x(), area.right() - self.width()))
                y = max(area.top(), min(point.y(), area.bottom() - self.height()))
                if (x, y) != (point.x(), point.y()):
                    self.move(x, y)
                return
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 140)

    def _save_position(self) -> None:
        self._settings.set("desktop_lyrics.x", self.x())
        self._settings.set("desktop_lyrics.y", self.y())

    # ------------------------------------------------------------------ public
    def show_lyrics(self) -> None:
        self.apply_settings()
        self._position = ctx().player.position
        self._clamp_to_screen()
        self.show()
        self.raise_()
        self.update()

    def hide_lyrics(self) -> None:
        self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide_lyrics()
            self._settings.set("desktop_lyrics.enabled", False)
        else:
            self._settings.set("desktop_lyrics.enabled", True)
            self.show_lyrics()

    def set_click_through(self, enabled: bool) -> None:
        self._settings.set("desktop_lyrics.click_through", bool(enabled))
        self._click_through = bool(enabled)
        self._apply_click_through(self._click_through)

    def set_locked(self, locked: bool) -> None:
        self._settings.set("desktop_lyrics.locked", bool(locked))
        self._locked = bool(locked)

    # ------------------------------------------------------------------ events
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_flags()
        self._resize_for_content()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._locked:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_started = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._locked:
            target = event.globalPosition().toPoint() - self._drag_offset
            if not self._drag_started and (target - self.pos()).manhattanLength() > 3:
                self._drag_started = True
            if self._drag_started:
                self.move(target)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            if self._drag_started:
                self._save_position()
            self._drag_offset = None
            self._drag_started = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        window = getattr(ctx(), "window", None)
        if window is not None:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        lock = menu.addAction("锁定位置" if not self._locked else "解锁位置")
        through = menu.addAction("鼠标穿透")
        through.setCheckable(True)
        through.setChecked(self._click_through)
        menu.addSeparator()
        lines = menu.addMenu("显示行数")
        one = lines.addAction("单行")
        two = lines.addAction("双行")
        one.setCheckable(True)
        two.setCheckable(True)
        one.setChecked(self._lines == 1)
        two.setChecked(self._lines == 2)
        size = menu.addMenu("字号")
        bigger = size.addAction("放大")
        smaller = size.addAction("缩小")
        menu.addSeparator()
        hide = menu.addAction("隐藏桌面歌词")
        quit_action = menu.addAction("关闭桌面歌词")

        chosen = menu.exec(event.globalPos())
        if chosen is lock:
            self.set_locked(not self._locked)
            return
        if chosen is through:
            self.set_click_through(through.isChecked())
            return
        if chosen is one:
            self._settings.set("desktop_lyrics.lines", 1)
            return
        if chosen is two:
            self._settings.set("desktop_lyrics.lines", 2)
            return
        if chosen is bigger:
            self._settings.set("desktop_lyrics.font_size", min(64, self._font_size + 4))
            return
        if chosen is smaller:
            self._settings.set("desktop_lyrics.font_size", max(18, self._font_size - 4))
            return
        if chosen is hide:
            self.hide_lyrics()
            self._settings.set("desktop_lyrics.enabled", False)
            return
        if chosen is quit_action:
            self.hide_lyrics()
            self._settings.set("desktop_lyrics.enabled", False)
            ctx().desktop_lyrics = None
            self.deleteLater()

    def wheelEvent(self, event) -> None:  # noqa: N802
        step = 2 if event.angleDelta().y() > 0 else -2
        size = max(18, min(64, self._font_size + step))
        if size != self._font_size:
            self._settings.set("desktop_lyrics.font_size", size)
        event.accept()

    # ------------------------------------------------------------------ paint
    def _line_font(self, scale: float, weight: int = 700) -> QFont:
        font = QFont(theme().font(12, weight))
        font.setPixelSize(max(10, int(self._font_size * scale)))
        font.setWeight(QFont.Weight(weight))
        return font

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        document = self._document
        if document is None or document.is_empty():
            self._paint_placeholder(painter)
            painter.end()
            return

        index = document.index_at(self._position)
        if index < 0:
            index = 0
        if index >= len(document.lines):
            index = len(document.lines) - 1
        line = document.lines[index]

        pad, main_h, trans_h, next_h = self._metrics_slots()
        rect = QRectF(self.rect())
        left = rect.left() + 20
        width = rect.width() - 40
        top = rect.top() + pad

        primary = self._line_font(1.0)
        metrics = QFontMetrics(primary)
        text = line.text or "♪"
        main_rect = QRectF(left, top, width, main_h)
        self._draw_line(
            painter,
            main_rect,
            text,
            primary,
            QColor(self._color),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        progress = self._sweep_pixels(document, line, index, primary, metrics, text)
        if progress > 0:
            baseline = (
                main_rect.center().y()
                - (metrics.ascent() + metrics.descent()) / 2
                + metrics.ascent()
            )
            paint_sweep(
                painter,
                text=text,
                font=primary,
                color=QColor(self._highlight),
                x=main_rect.center().x() - metrics.horizontalAdvance(text) / 2,
                baseline=baseline,
                progress=progress,
            )

        y = top + main_h
        if self._show_translation and trans_h:
            if line.translation:
                self._draw_line(
                    painter,
                    QRectF(left, y, width, trans_h),
                    line.translation,
                    self._line_font(0.54, 500),
                    rgba(self._color, 0.72),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                )
            y += trans_h

        if self._lines >= 2 and next_h:
            next_text = ""
            if index + 1 < len(document.lines):
                next_text = document.lines[index + 1].text
            if next_text:
                self._draw_line(
                    painter,
                    QRectF(left, y + 2, width, next_h - 2),
                    next_text,
                    self._line_font(0.62, 600),
                    rgba(self._color, 0.58),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                )
        painter.end()

    def _draw_line(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        font: QFont,
        color: QColor,
        alignment: Qt.AlignmentFlag,
    ) -> None:
        painter.setFont(font)
        painter.setPen(QPen(QColor(0, 0, 0, 170)))
        painter.drawText(rect.translated(1.4, 2.0), alignment, text)
        painter.setPen(QPen(color))
        painter.drawText(rect, alignment, text)

    def _paint_placeholder(self, painter: QPainter) -> None:
        font = self._line_font(0.6, 600)
        painter.setFont(font)
        painter.setPen(QPen(rgba(self._color, 0.5)))
        painter.drawText(
            QRectF(self.rect()),
            Qt.AlignmentFlag.AlignCenter,
            "桌面歌词 · 暂无歌词" if self._track is not None else "桌面歌词",
        )

    def _sweep_pixels(self, document, line, index: int, font: QFont, metrics: QFontMetrics, text: str) -> float:
        """Sweep offset in fractional pixels, honouring real per-word timings."""
        position = self._position - getattr(document, "offset_ms", 0)
        if getattr(line, "words", None):
            return sweep_pixels_for_line(
                QFontMetricsF(font),
                text,
                progress=0.0,
                words=line.words,
                position=position,
            )
        if position <= line.start_ms:
            return 0.0
        if position >= line.end_ms:
            return float(metrics.horizontalAdvance(text))
        span = max(1, line.end_ms - line.start_ms)
        ratio = (position - line.start_ms) / span
        return float(metrics.horizontalAdvance(text)) * max(0.0, min(1.0, ratio))


__all__ = ["DesktopLyricsWindow", "ensure_desktop_lyrics"]

