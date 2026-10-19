import sys
sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle

app = QApplication(sys.argv)
pm = QPixmap(16, 16); pm.fill(QColor("#ff0000"))
tray_red = QSystemTrayIcon(QIcon(pm))
tray_red.setToolTip("RED TEST")
tray_red.setContextMenu(QMenu())
tray_red.show()
std = app.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
tray_std = QSystemTrayIcon(std)
tray_std.setToolTip("STD TEST")
tray_std.setContextMenu(QMenu())
tray_std.show()
print("red", tray_red.isVisible(), tray_red.geometry(), flush=True)
print("std", tray_std.isVisible(), tray_std.geometry(), flush=True)

def grab():
    app.primaryScreen().grabWindow(0).save("artifacts/qa/r39/screen_red_tray.png")
    print("grabbed", flush=True)

QTimer.singleShot(2000, grab)
QTimer.singleShot(2600, app.quit)
app.exec()
