"""Tooltips must use the themed HoverTip, not the square native one."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QWidget

from hushplayer.ui.widgets import hover_tip


def test_tooltip_event_routes_to_themed_tip(qapp) -> None:
    hover_tip.install_tooltip_router(QApplication.instance())
    widget = QWidget()
    widget.setToolTip("下一首 (Ctrl+Right)")

    event = QEvent(QEvent.Type.ToolTip)
    handled = QApplication.sendEvent(widget, event)

    assert handled is True  # native tooltip suppressed
    assert hover_tip._TIP is not None
    assert hover_tip._TIP.isVisible()
    assert hover_tip._TIP._label.text() == "下一首 (Ctrl+Right)"
    hover_tip.hide_tip()
    widget.deleteLater()
