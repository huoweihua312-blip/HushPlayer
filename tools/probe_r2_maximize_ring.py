import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = hush.window

def shoot():
    win.toggle_maximize(); app.processEvents()
    QTimer.singleShot(900, grab)

def grab():
    screen = app.primaryScreen()
    pix = screen.grabWindow(0, 0, 0, 300, 300)
    pix.save("artifacts/qa/r2/max_corner.png")
    img = pix.toImage()
    print("corner colors", [img.pixelColor(x, 2).name() for x in range(0, 40, 4)], flush=True)
    print("left col", [img.pixelColor(2, y).name() for y in range(0, 40, 4)], flush=True)
    print("maximized", win.isMaximized(), win.width(), win.height(), flush=True)
    win.close(); app.quit()

QTimer.singleShot(1500, shoot)
QTimer.singleShot(20000, app.quit)
app.exec()
hush.shutdown()
