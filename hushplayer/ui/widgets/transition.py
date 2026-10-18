"""Lightweight snapshot cross-fade used for theme switching.

Painting a captured frame with ``QPainter.setOpacity`` is deliberately used
instead of ``QGraphicsOpacityEffect``: the effect puts the whole live widget
tree on an offscreen compositing surface, which at 2560x1392@125% costs a lot
and has caused visible flashes while lyrics scroll.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ...core.theme import theme

__all__ = ["FadeOverlay"]

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
