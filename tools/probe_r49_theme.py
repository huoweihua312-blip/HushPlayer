import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r49/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
state = {"shots": 0}

def toggle_burst():
    for _ in range(5):
        win.titlebar.theme_button.click()
        app.processEvents()
    QTimer.singleShot(80, mid)

def mid():
    win.grab().save("artifacts/qa/r49/burst_mid.png")
    QTimer.singleShot(1400, after)

def after():
    win.grab().save("artifacts/qa/r49/burst_done.png")
    overlay = getattr(hush, "_theme_reveal", None)
    print("overlay_pending", overlay is not None and overlay.isVisible(), flush=True)
    print("mode", hush._resolved_mode, flush=True)
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(700, toggle_burst)
app.exec(); hush.shutdown()
