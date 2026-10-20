"""Lightweight snapshot cross-fade used for theme switching.

Painting a captured frame with ``QPainter.setOpacity`` is deliberately used
instead of ``QGraphicsOpacityEffect``: the effect puts the whole live widget
tree on an offscreen compositing surface, which at 2560x1392@125% costs a lot
and has caused visible flashes while lyrics scroll.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QRadialGradient
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
