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
            rim = QColor(255, 186, 120) if not self._to_dark else QColor(120, 60, 84)
            rim.setAlphaF(0.45 * (1.0 - self._progress) ** 1.5)
            gradient = QRadialGradient(self._origin, max(radius, 1.0))
            gradient.setColorAt(max(0.0, 1.0 - 46.0 / max(radius, 46.0)), QColor(0, 0, 0, 0))
            gradient.setColorAt(1.0, rim)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(self._origin, radius, radius)
        painter.end()


class SunriseReveal(QWidget):
    """Full-window sunrise / sunset wipe between two theme snapshots.

    Going light the new frame rises from the bottom edge like a sunrise; going
    dark it descends from the top like a sunset. A soft warm band travels with
    the edge and fades out, so the switch reads as daylight changing rather than
    a UI repaint.
    """

    DURATION_MS = 900
    BAND_RATIO = 0.20
    STEPS = 48

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
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
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

    def _edge(self) -> float:
        height = float(self.height())
        band = max(48.0, height * self.BAND_RATIO)
        span = height + band
        if self._to_dark:
            return self._progress * span - band  # new frame descends from the top
        return height - self._progress * span  # new frame rises from the bottom

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = int(self.width())
        height = int(self.height())
        if width <= 0 or height <= 0:
            painter.end()
            return
        if not self._old.isNull():
            painter.drawPixmap(self.rect(), self._old)
        if self._new.isNull():
            painter.end()
            return

        band = int(max(48.0, height * self.BAND_RATIO))
        edge = int(round(self._edge()))
        if self._to_dark:
            band_top = max(0, edge - band)
            solid = QRect(0, 0, width, band_top)
        else:
            band_top = min(height - band, edge)
            solid = QRect(0, band_top + band, width, max(0, height - band_top - band))
        if solid.height() > 0:
            painter.drawPixmap(solid, self._new, solid)

        visible = min(band, height - max(0, band_top))
        if visible > 0:
            strip = QImage(width, visible, QImage.Format.Format_ARGB32_Premultiplied)
            strip.fill(Qt.GlobalColor.transparent)
            brush = QPainter(strip)
            source = QRect(0, max(0, band_top), width, visible)
            brush.drawPixmap(QRect(0, 0, width, visible), self._new, source)
            gradient = QLinearGradient(0.0, 0.0, 0.0, float(visible))
            if self._to_dark:
                gradient.setColorAt(0.0, QColor(0, 0, 0, 255))
                gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
            else:
                gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
                gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
            brush.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            brush.fillRect(strip.rect(), gradient)
            brush.end()
            painter.drawImage(QPoint(0, max(0, band_top)), strip)

        # Warm rim travelling with the edge, plus a low sun glow.
        fade = max(0.0, 1.0 - abs(self._progress - 0.5) * 0.7)
        glow = QColor(255, 183, 105) if not self._to_dark else QColor(201, 87, 112)
        gradient = QLinearGradient(0.0, edge - band, 0.0, edge + band)
        transparent = QColor(glow)
        transparent.setAlpha(0)
        centre = QColor(glow)
        centre.setAlphaF(0.42 * fade)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, centre)
        gradient.setColorAt(1.0, transparent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRect(QRectF(0.0, edge - band, float(width), float(band * 2)))

        sun_radius = max(40.0, min(width, height) * 0.07)
        sun_centre = QPointF(width * 0.5, float(edge))
        radial = QRadialGradient(sun_centre, sun_radius * 2.4)
        core = QColor(255, 214, 160) if not self._to_dark else QColor(232, 140, 160)
        core.setAlphaF(0.55 * fade)
        halo = QColor(core)
        halo.setAlpha(0)
        radial.setColorAt(0.0, core)
        radial.setColorAt(0.55, halo)
        radial.setColorAt(1.0, halo)
        painter.setBrush(radial)
        painter.drawEllipse(sun_centre, sun_radius * 2.4, sun_radius * 2.4)
        painter.end()
