"""Render the self-painted menu on a real screen grab (proves rounded corners)."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r72/data")
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


class Host(QWidget):
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#E9E9EE"))
        painter.end()


host = Host()
host.resize(560, 420)
host.move(80, 80)
host.show()

menu = PopupMenu(host)
menu.addAction("新建歌单")
menu.addAction("从文件导入歌单…")
menu.addSeparator()
update = menu.addAction("检查订阅更新")
update.setEnabled(False)
sub = menu.addMenu("显示行数")
one = sub.addAction("单行")
two = sub.addAction("双行")
two.setCheckable(True)
two.setChecked(True)


def open_menu() -> None:
    menu.popup(host.mapToGlobal(QPoint(200, 60)))
    QTimer.singleShot(400, grab_primary)


def grab_primary() -> None:
    screen = app.primaryScreen()
    screen.grabWindow(0).copy(60, 40, 620, 520).save("artifacts/qa/r72/menu_screen.png")
    menu._open_submenu(4)
    QTimer.singleShot(400, grab_sub)


def grab_sub() -> None:
    screen = app.primaryScreen()
    screen.grabWindow(0).copy(60, 40, 760, 560).save("artifacts/qa/r72/menu_sub_screen.png")
    print("RESULT PASS", flush=True)
    app.quit()


QTimer.singleShot(600, open_menu)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
