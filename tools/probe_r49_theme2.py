import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r49/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
result = {"errors": []}

def burst():
    try:
        for _ in range(6):
            win.titlebar.theme_button.click()
            app.processEvents()
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(repr(exc))
    QTimer.singleShot(1600, check)

def check():
    overlay = getattr(hush, "_theme_reveal", None)
    alive = overlay is not None and overlay.isVisible()
    print("overlay_alive", alive, flush=True)
    print("mode", hush._resolved_mode, flush=True)
    print("errors", result["errors"], flush=True)
    print("RESULT", "PASS" if not alive and not result["errors"] else "FAIL", flush=True)
    app.quit()

QTimer.singleShot(500, burst)
QTimer.singleShot(9000, app.quit)
app.exec(); hush.shutdown()
