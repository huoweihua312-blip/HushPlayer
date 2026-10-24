"""Tests for the self-drawn dialog helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.core.theme import apply_theme_to_app  # noqa: E402
from hushplayer.ui.dialogs import CardDialog, MessageDialog, TextInputDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme_to_app(app, preference="dark")
    yield app


def test_card_dialog_is_frameless_and_round(qapp):
    dialog = CardDialog(None, "标题")
    assert dialog.windowFlags() & Qt.FramelessWindowHint
    assert dialog.windowTitle() == "标题"
    assert dialog._card.objectName() == "HushDialogCard"
    dialog.close()


def test_message_dialog_returns_requested_value(qapp):
    dialog = MessageDialog(None, "确认", "要删除吗？", kind="warning", buttons=[("cancel", "取消"), ("ok", "删除")])
    assert dialog.selected() == ""
    dialog.button_for("ok").click()
    assert dialog.selected() == "ok"
    dialog.close()


def test_message_dialog_cancel_is_default(qapp):
    dialog = MessageDialog(None, "确认", "继续？", buttons=[("cancel", "取消"), ("ok", "继续")])
    dialog.button_for("cancel").click()
    assert dialog.selected() == "cancel"
    dialog.close()


def test_text_input_dialog_returns_entered_text(qapp):
    dialog = TextInputDialog(None, "新建歌单", "起个名字", text="默认名")
    assert dialog.value() == "默认名"
    dialog.edit.returnPressed.emit()
    assert dialog.selected() == "ok"
    dialog.close()

def test_checkbox_hover_uses_hover_animation_api(qapp):
    """Regression: CheckBox used HoverAnimation.set_end which does not exist."""
    import time

    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    from hushplayer.ui.widgets.check import CheckBox

    box = CheckBox("自动采用", size=16)
    box.show()

    center = QPointF(box.width() / 2, box.height() / 2)
    box.enterEvent(QEnterEvent(center, center, center))
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and box._hover.value < 0.5:
        qapp.processEvents()
        time.sleep(0.01)
    assert box._hover.value > 0.5

    box.leaveEvent(QEvent(QEvent.Type.Leave))
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and box._hover.value > 0.5:
        qapp.processEvents()
        time.sleep(0.01)
    assert box._hover.value < 0.5
