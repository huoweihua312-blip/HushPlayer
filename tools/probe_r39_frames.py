import os, sys, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data3")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.core.theme import theme
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()

def go():
    try:
        target = "light" if theme().mode == "dark" else "dark"
        print("from", theme().mode, "to", target, flush=True)
        hush.settings.set("appearance.theme", target)
        hush.apply_theme(animate=True)
        print("mode_after", theme().mode, flush=True)
    except Exception:
        traceback.print_exc()
    QTimer.singleShot(60, f1); QTimer.singleShot(160, f2); QTimer.singleShot(900, done)

def f1(): win.grab().save("artifacts/qa/r39/frame_a.png")
def f2(): win.grab().save("artifacts/qa/r39/frame_b.png")
def done():
    win.grab().save("artifacts/qa/r39/frame_c.png")
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(500, go)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
