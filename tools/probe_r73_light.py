"""Light-theme screen grabs for the self-painted menu, submenu and combo popup."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r73/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.popup import PopupMenu
from hushplayer.ui.widgets.settings_widgets import SettingCombo

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
host.resize(600, 460)
host.move(60, 60)
host.show()

menu = PopupMenu(host)
menu.addAction("新建歌单")
menu.addAction("从文件导入歌单…")
menu.addSeparator()
update = menu.addAction("检查订阅更新")
update.setEnabled(False)
sub = menu.addMenu("显示行数")
sub.addAction("单行")
two = sub.addAction("双行")
two.setCheckable(True)
two.setChecked(True)

combo = SettingCombo([("过渡动画（从标题栏按钮扩散）", "reveal"), ("全屏日月动画", "sunrise"), ("关闭", "off")])
combo.move(320, 380)
combo.resize(240, 36)
combo.show()


def step1() -> None:
    menu.popup(host.mapToGlobal(QPoint(140, 60)))
    QTimer.singleShot(350, grab_main)


def grab_main() -> None:
    app.primaryScreen().grabWindow(0).copy(40, 30, 560, 420).save(
        "artifacts/qa/r73/menu_light.png"
    )
    menu._open_submenu(4)
    QTimer.singleShot(350, grab_sub)


def grab_sub() -> None:
    app.primaryScreen().grabWindow(0).copy(40, 30, 700, 440).save(
        "artifacts/qa/r73/menu_sub_light.png"
    )
    menu.close()
    QTimer.singleShot(250, open_combo)


def open_combo() -> None:
    combo.showPopup()
    QTimer.singleShot(400, grab_combo)


def grab_combo() -> None:
    app.primaryScreen().grabWindow(0).copy(220, 330, 520, 260).save(
        "artifacts/qa/r73/combo_light.png"
    )
    for widget in app.topLevelWidgets():
        if isinstance(widget, PopupMenu):
            widget.close()
    print("RESULT PASS", flush=True)
    app.quit()


QTimer.singleShot(600, step1)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
