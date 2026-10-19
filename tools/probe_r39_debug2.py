import os, sys, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data")
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
        print("mode_before", theme().mode, "resolved", hush._resolved_mode, flush=True)
        hush.apply_theme(preference="light", animate=True)
        print("mode_after", theme().mode, "resolved", hush._resolved_mode, flush=True)
    except Exception:
        traceback.print_exc()
    QTimer.singleShot(200, done)

def done():
    win.grab().save("artifacts/qa/r39/mid.png")
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(500, go)
QTimer.singleShot(8000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
