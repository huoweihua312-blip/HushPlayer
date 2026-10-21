"""Verify in-window submenu: opens inside the panel, and closes when hover leaves."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r75/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter
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
        painter.fillRect(self.rect(), QColor("#ECECF0"))
        painter.end()


host = Host()
host.resize(680, 460)
host.move(70, 70)
host.show()

menu = PopupMenu(host)
lock = menu.addAction("锁定位置")
lock.setCheckable(True)
through = menu.addAction("鼠标穿透")
through.setCheckable(True)
menu.addSeparator()
sub = menu.addMenu("显示行数")
one = sub.addAction("单行")
one.setCheckable(True)
two = sub.addAction("双行")
two.setCheckable(True)
two.setChecked(True)
size = menu.addMenu("字号")
size.addAction("放大")
size.addAction("缩小")
menu.addSeparator()
menu.addAction("隐藏桌面歌词")
menu.addAction("关闭桌面歌词")


def move_event(x: int, y: int) -> QMouseEvent:
    local = QPointF(x, y)
    return QMouseEvent(
        QEvent.Type.MouseMove,
        local,
        menu.mapToGlobal(local),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def open_and_grab() -> None:
    menu.popup(host.mapToGlobal(QPoint(180, 60)))
    QTimer.singleShot(300, with_sub)


def with_sub() -> None:
    menu._open_submenu(4)  # 字号
    app.processEvents()
    QTimer.singleShot(250, grab_open)


def grab_open() -> None:
    app.primaryScreen().grabWindow(0).copy(120, 90, 640, 440).save(
        "artifacts/qa/r75/sub_open.png"
    )
    # hover a row that is not the submenu row -> submenu must collapse
    menu.mouseMoveEvent(move_event(60, 30))
    app.processEvents()
    QTimer.singleShot(200, grab_closed)


def grab_closed() -> None:
    state = "collapsed" if menu._sub_open < 0 else "stuck"
    app.primaryScreen().grabWindow(0).copy(120, 90, 640, 440).save(
        "artifacts/qa/r75/sub_closed.png"
    )
    print("SUB_STATE", state, flush=True)
    menu.close()
    print("RESULT", "PASS" if state == "collapsed" else "FAIL", flush=True)
    app.quit()


QTimer.singleShot(600, open_and_grab)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
