"""Verify the combo popup stays open, can be clicked, and applies the choice."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r76/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.settings_widgets import SettingCombo

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
ctx().settings.set("appearance.theme", "light")
app.processEvents()

combo = SettingCombo([("过渡动画（从标题栏按钮扩散）", "reveal"), ("全屏日月动画", "sunrise"), ("关闭", "off")])
combo.resize(320, 40)
combo.move(200, 200)
combo.show()

state = {}


def open_popup() -> None:
    combo.showPopup()
    QTimer.singleShot(300, inspect)


def inspect() -> None:
    menu = getattr(combo, "_popup_menu", None)
    state["menu"] = menu
    state["visible"] = bool(menu is not None and menu.isVisible())
    if menu is not None:
        state["size"] = (menu.width(), menu.height())
        # click the third row (关闭)
        rows = menu._rows()
        top, height = rows[2]
        point = QPointF(menu.width() / 2 - 40, top + height / 2)
        menu.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                point,
                menu.mapToGlobal(point),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
    app.processEvents()
    QTimer.singleShot(200, done)


def done() -> None:
    menu = state.get("menu")
    visible = state.get("visible", False)
    index = combo.currentIndex()
    closed = menu is None or not menu.isVisible()
    ok = visible and index == 2 and closed
    print("POPUP_VISIBLE", visible, "INDEX", index, "CLOSED", closed, flush=True)
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    app.quit()


QTimer.singleShot(600, open_popup)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
