"""Stable overlay host used by the Quiet Orbit immersive presentation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget


class ImmersiveOverlayHost(QWidget):
    """Transparent child layer that owns floating panels for one page lifetime."""

    background_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("immersiveOverlayHost")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # Keep the host in the hit-test tree so its child panels receive native
        # coordinate clicks. The page handles a host click as an outside click.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.background_pressed.emit()
        event.accept()
