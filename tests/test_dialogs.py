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
