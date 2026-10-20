"""Lightweight snapshot cross-fade used for theme switching.

Painting a captured frame with ``QPainter.setOpacity`` is deliberately used
instead of ``QGraphicsOpacityEffect``: the effect puts the whole live widget
tree on an offscreen compositing surface, which at 2560x1392@125% costs a lot
and has caused visible flashes while lyrics scroll.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QPen,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ...core.theme import theme

__all__ = ["FadeOverlay", "ThemeReveal"]

_DURATION_MS = 260


class FadeOverlay(QWidget):
    """Full-window snapshot that fades out, revealing the freshly themed UI."""

    def __init__(self, parent: QWidget, snapshot: QPixmap) -> None:
        super().__init__(parent)
        self._pixmap = snapshot
        self._opacity = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setGeometry(parent.rect())
        self._animation = QPropertyAnimation(self, b"overlayOpacity", self)
        self._animation.setDuration(theme().duration(_DURATION_MS))
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self.close)

    # ------------------------------------------------------------- 属性
    def get_overlay_opacity(self) -> float:
        return self._opacity

    def set_overlay_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        self.update()

    overlayOpacity = Property(float, get_overlay_opacity, set_overlay_opacity)

    # ------------------------------------------------------------- 行为
    def start(self) -> None:
        self.show()
        self.raise_()
        if theme().reduce_motion:
            self.close()
            return
        self._animation.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._pixmap.isNull() or self._opacity <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._animation.stop()
        QTimer.singleShot(0, self.close)


class ThemeReveal(QWidget):
    """Circular "sunrise / sunset" wipe between two theme snapshots.

    ``old`` is the frame before the palette changed, ``new`` the frame after;
    the new theme grows out of the theme button as an expanding circle with a
    warm rim, which reads as sunrise when turning light and sunset when turning
    dark without touching the live widget tree.
    """

    DURATION_MS = 620

    def __init__(
        self,
        parent: QWidget,
        old: QPixmap,
        new: QPixmap,
        origin: object,
        *,
        to_dark: bool,
    ) -> None:
        super().__init__(parent)
        self._old = old
        self._new = new
        self._origin = origin
        self._to_dark = to_dark
        self._progress = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setGeometry(parent.rect())
        self._animation = QPropertyAnimation(self, b"revealProgress", self)
        self._animation.setDuration(theme().duration(self.DURATION_MS))
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self.close)

    def get_reveal_progress(self) -> float:
        return self._progress

    def set_reveal_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    revealProgress = Property(float, get_reveal_progress, set_reveal_progress)

    def start(self) -> None:
        self.show()
        self.raise_()
        if theme().reduce_motion:
            self.close()
            return
        self._animation.start()

    def freeze(self) -> None:
        """Show the old frame only, so the palette change cannot leak a frame."""
        self.set_reveal_progress(0.0)
        self.show()
        self.raise_()

    def resume_with(self, new: QPixmap) -> None:
        """Swap in the freshly themed frame and start the wipe."""
        self._new = new
        self.show()
        self.raise_()
        if theme().reduce_motion:
            self.close()
            return
        self._animation.start()

    def finish(self) -> None:
        """Stop right now (used when another theme change supersedes this one)."""
        self._animation.stop()
        self._progress = 1.0
        self.hide()
        self.close()

    def _radius_max(self) -> float:
        x, y = self._origin.x(), self._origin.y()
        corners = [
            (0.0, 0.0), (float(self.width()), 0.0),
            (0.0, float(self.height())), (float(self.width()), float(self.height())),
        ]
        return max(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for cx, cy in corners)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if not self._old.isNull():
            painter.drawPixmap(self.rect(), self._old)
        radius = self._radius_max() * self._progress
        if not self._new.isNull() and radius > 0:
            path = QPainterPath()
            path.addEllipse(self._origin, radius, radius)
            painter.setClipPath(path)
            painter.drawPixmap(self.rect(), self._new)
            painter.setClipping(False)
            # Pure black / white rim only: white against a dark frame, black
            # against a light one.
            rim = QColor("#FFFFFF") if self._to_dark else QColor("#000000")
            rim.setAlphaF(0.45 * (1.0 - self._progress) ** 1.5)
            gradient = QRadialGradient(self._origin, max(radius, 1.0))
            gradient.setColorAt(max(0.0, 1.0 - 46.0 / max(radius, 46.0)), QColor(0, 0, 0, 0))
            gradient.setColorAt(1.0, rim)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(self._origin, radius, radius)
        painter.end()


class SunMoonReveal(QWidget):
    """Centre sun / moon pops in, then the whole window cross-fades.

    Two cheap passes only — the old snapshot, then the new one at a uniform
    opacity — so the animation stays smooth at 2560px. The icon is pure white on
    dark backgrounds and pure black on light ones: no accent colours anywhere.
    """

    DURATION_MS = 820
    POP_END = 0.26  # icon growth finishes here
    ICON_HOLD = 0.30
    ICON_GONE = 0.54  # icon is gone before the wash fully covers the frame
    DIP_IN = 0.24  # wash starts while the icon is still visible
    DIP_HOLD = 0.58  # wash peaks here; the new frame then fades in underneath

    def __init__(
        self,
        parent: QWidget,
        old: QPixmap,
        new: QPixmap,
        origin: object = None,
        *,
        to_dark: bool,
    ) -> None:
        super().__init__(parent)
        self._old = old
        self._new = new
        self._to_dark = to_dark
        self._progress = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setGeometry(parent.rect())
        self._animation = QPropertyAnimation(self, b"revealProgress", self)
        self._animation.setDuration(theme().duration(self.DURATION_MS))
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self.close)

    def get_reveal_progress(self) -> float:
        return self._progress

    def set_reveal_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    revealProgress = Property(float, get_reveal_progress, set_reveal_progress)

    def start(self) -> None:
        self.show()
        self.raise_()
        if theme().reduce_motion:
            self.close()
            return
        self._animation.start()

    def freeze(self) -> None:
        self.set_reveal_progress(0.0)
        self.show()
        self.raise_()

    def resume_with(self, new: QPixmap) -> None:
        self._new = new
        self.show()
        self.raise_()
        if theme().reduce_motion:
            self.close()
            return
        self._animation.start()

    def finish(self) -> None:
        self._animation.stop()
        self._progress = 1.0
        self.hide()
        self.close()

    # ------------------------------------------------------------------ 取值
    @staticmethod
    def _smoothstep(value: float) -> float:
        x = max(0.0, min(1.0, value))
        return x * x * (3.0 - 2.0 * x)

    def dip_alpha(self) -> float:
        """Solid black/white wash: rises after the icon, then yields to the new frame."""
        if self._progress <= self.DIP_IN:
            return 0.0
        if self._progress <= self.DIP_HOLD:
            span = max(1e-6, self.DIP_HOLD - self.DIP_IN)
            return self._smoothstep((self._progress - self.DIP_IN) / span)
        # Stay fully covered: the new frame fades in on top, so the wash must
        # not drop to zero or the old frame flashes back for a few frames.
        return 1.0

    def new_frame_alpha(self) -> float:
        """The new theme only appears after the wash has fully covered the old one."""
        if self._progress <= self.DIP_HOLD:
            return 0.0
        span = max(1e-6, 1.0 - self.DIP_HOLD)
        return self._smoothstep((self._progress - self.DIP_HOLD) / span)

    def icon_scale(self) -> float:
        """Icon grows from 0.55 to 1.0 while it pops, then holds."""
        if self._progress >= self.POP_END:
            return 1.0
        t = self._progress / max(1e-6, self.POP_END)
        return 0.55 + 0.45 * (1.0 - (1.0 - t) ** 3)

    def icon_alpha(self) -> float:
        """Fade the icon in quickly, then out before the wash peaks."""
        if self._progress < 0.10:
            return self._progress / 0.10
        if self._progress <= self.ICON_HOLD:
            return 1.0
        span = max(1e-6, self.ICON_GONE - self.ICON_HOLD)
        return max(0.0, 1.0 - (self._progress - self.ICON_HOLD) / span)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if not self._old.isNull():
            painter.drawPixmap(self.rect(), self._old)
        wash = self.dip_alpha()
        if wash > 0.0:
            colour = QColor("#FFFFFF") if not self._to_dark else QColor("#000000")
            colour.setAlphaF(min(1.0, wash))
            painter.fillRect(self.rect(), colour)
        alpha = self.new_frame_alpha()
        if not self._new.isNull() and alpha > 0.0:
            painter.setOpacity(alpha)
            painter.drawPixmap(self.rect(), self._new)
            painter.setOpacity(1.0)
        icon_alpha = self.icon_alpha()
        if icon_alpha > 0.0:
            self._paint_icon(painter, icon_alpha)
        painter.end()

    def _paint_icon(self, painter: QPainter, alpha: float) -> None:
        size = min(self.width(), self.height())
        radius = max(18.0, size * 0.055) * self.icon_scale()
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        # Contrast against the frame we are coming *from*; both pure B/W.
        colour = QColor("#000000") if self._to_dark else QColor("#FFFFFF")
        colour.setAlphaF(min(1.0, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        if self._to_dark:
            # Crescent: big disc, offset counter-disc knocked out with the frame.
            painter.save()
            path = QPainterPath()
            path.addEllipse(centre, radius, radius)
            bite = QPainterPath()
            bite.addEllipse(
                QPointF(centre.x() + radius * 0.55, centre.y() - radius * 0.35),
                radius * 0.92,
                radius * 0.92,
            )
            painter.setClipPath(path.subtracted(bite))
            painter.drawEllipse(centre, radius, radius)
            painter.restore()
        else:
            painter.drawEllipse(centre, radius, radius)
            painter.save()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(colour)
            pen.setWidthF(max(1.5, radius * 0.14))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            rays = 8
            inner = radius * 1.42
            outer = radius * 1.92
            for index in range(rays):
                angle = index * (360.0 / rays)
                painter.save()
                painter.translate(centre)
                painter.rotate(angle)
                painter.drawLine(QPointF(0.0, -inner), QPointF(0.0, -outer))
                painter.restore()
            painter.restore()
