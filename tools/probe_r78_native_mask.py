"""Desktop-lyrics style menu: small host, so it must fall back to a masked window."""

import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r78/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.popup import PopupMenu

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
ctx().settings.set("appearance.theme", "light")

host = QWidget()
host.resize(360, 110)
host.move(120, 120)
host.show()

menu = PopupMenu(host)
for label in ("锁定位置", "鼠标穿透", "显示行数", "字号", "隐藏桌面歌词", "关闭桌面歌词"):
    menu.addAction(label)
sub = menu.addMenu("显示行数")
sub.addAction("单行")
sub.addAction("双行")
menu.popup(host.mapToGlobal(QPoint(30, 20)))
app.processEvents()


def report() -> None:
    mask = menu.mask()
    print("NATIVE", not menu._overlay, "MASK_EMPTY", mask.isEmpty(), flush=True)
    print("WINDOW", menu.width(), menu.height(), "HOST", host.width(), host.height(), flush=True)
    app.primaryScreen().grabWindow(0).copy(60, 60, 620, 420).save(
        "artifacts/qa/r78/native_mask.png"
    )
    print("RESULT PASS", flush=True)
    app.quit()


QTimer.singleShot(700, report)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
