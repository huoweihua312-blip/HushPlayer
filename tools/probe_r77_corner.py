"""Read-only diagnosis: does the popup window have an opaque backing surface?

Renders a light menu over a *dark* host and takes a real screen grab, then probes
window flags/ex-styles and samples the corner pixels. No app code is modified.
"""

import ctypes
import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r77/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"

from PySide6.QtCore import QPoint, Qt, QTimer
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


class DarkHost(QWidget):
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101014"))
        painter.end()


host = DarkHost()
host.resize(600, 420)
host.move(80, 80)
host.show()

menu = PopupMenu(host)
menu.addAction("新建歌单")
menu.addAction("从文件导入歌单…")

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000


def inspect() -> None:
    menu.popup(host.mapToGlobal(QPoint(180, 90)))
    QTimer.singleShot(300, report)


def report() -> None:
    hwnd = int(menu.winId())
    ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    print("EXSTYLE", hex(ex & 0xFFFFFFFF), "LAYERED", bool(ex & WS_EX_LAYERED), flush=True)
    print("MASK_EMPTY", menu.mask().isEmpty(), "ATTR_TRANSLUCENT",
          menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), flush=True)
    print("SIZE", menu.width(), menu.height(), "POS", menu.x(), menu.y(), flush=True)
    screen = app.primaryScreen()
    grab = screen.grabWindow(0)
    grab.save("artifacts/qa/r77/screen_dark_host.png")
    # sample a small grid around the top-left corner of the panel
    img = grab.toImage()
    left, top = menu.x(), menu.y()
    samples = []
    for dx, dy in ((0, 0), (1, 1), (2, 2), (3, 3), (6, 6), (10, 10), (-4, -4)):
        px = img.pixelColor(left + dx, top + dy)
        samples.append((dx, dy, px.red(), px.green(), px.blue()))
    print("CORNER_SAMPLES", samples, flush=True)
    menu.close()
    print("RESULT PASS", flush=True)
    app.quit()


QTimer.singleShot(600, inspect)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
