"""Grab the mixed checkable/plain menu (desktop lyrics case) in both themes."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r74/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.popup import PopupMenu

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
ctx().settings.set("appearance.theme", "light")
app.processEvents()


class Host(QWidget):
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme_bg))
        painter.end()


theme_bg = "#ECECF0"
host = Host()
host.resize(520, 420)
host.move(70, 70)
host.show()


def build() -> PopupMenu:
    menu = PopupMenu(host)
    lock = menu.addAction("锁定位置")
    lock.setCheckable(True)
    through = menu.addAction("鼠标穿透")
    through.setCheckable(True)
    menu.addSeparator()
    lines = menu.addMenu("显示行数")
    one = lines.addAction("单行")
    one.setCheckable(True)
    two = lines.addAction("双行")
    two.setCheckable(True)
    two.setChecked(True)
    size = menu.addMenu("字号")
    size.addAction("放大")
    size.addAction("缩小")
    menu.addSeparator()
    menu.addAction("隐藏桌面歌词")
    menu.addAction("关闭桌面歌词")
    return menu


state = {"step": 0}


def start() -> None:
    global theme_bg
    theme_bg = "#ECECF0"
    host.update()
    menu = build()
    state["menu"] = menu
    menu.popup(host.mapToGlobal(QPoint(160, 40)))
    QTimer.singleShot(350, grab_light)


def grab_light() -> None:
    app.primaryScreen().grabWindow(0).copy(120, 60, 460, 400).save(
        "artifacts/qa/r74/menu_mixed_light.png"
    )
    state["menu"].close()
    QTimer.singleShot(300, dark)


def dark() -> None:
    global theme_bg
    ctx().settings.set("appearance.theme", "dark")
    app.processEvents()
    theme_bg = "#1C1B1D"
    host.update()
    menu = build()
    state["menu"] = menu
    menu.popup(host.mapToGlobal(QPoint(160, 40)))
    QTimer.singleShot(350, grab_dark)


def grab_dark() -> None:
    app.primaryScreen().grabWindow(0).copy(120, 60, 460, 400).save(
        "artifacts/qa/r74/menu_mixed_dark.png"
    )
    state["menu"].close()
    print("RESULT PASS", flush=True)
    app.quit()


QTimer.singleShot(700, start)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
