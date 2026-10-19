import sys
sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from hushplayer.core import brand
from hushplayer.core.theme import apply_theme_to_app

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
tray = QSystemTrayIcon(brand.tray_icon())
tray.setToolTip("HushPlayer tray probe")
tray.setContextMenu(QMenu())
tray.show()
print("available", QSystemTrayIcon.isSystemTrayAvailable(), "visible", tray.isVisible(),
      "geometry", tray.geometry(), "sizes", [s.width() for s in tray.icon().availableSizes()], flush=True)

def grab():
    screen = app.primaryScreen()
    pix = screen.grabWindow(0)
    pix.save("artifacts/qa/r39/screen_tray_probe.png")
    print("grabbed", pix.size(), flush=True)

QTimer.singleShot(2500, grab)
QTimer.singleShot(3200, app.quit)
app.exec()
