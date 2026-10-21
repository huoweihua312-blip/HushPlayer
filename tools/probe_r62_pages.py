import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r62/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()
routes = ["albums", "artists", "recent"]

def step(i=0):
    if i >= len(routes):
        print("RESULT PASS", flush=True); app.quit(); return
    win.navigate(routes[i]); app.processEvents()
    QTimer.singleShot(400, lambda: shot(routes[i], i))

def shot(route, i):
    win.grab().save(f"artifacts/qa/r62/{route}.png")
    step(i + 1)

QTimer.singleShot(700, step)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
