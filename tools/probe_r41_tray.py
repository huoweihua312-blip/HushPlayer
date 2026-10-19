import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
def go():
    QTimer.singleShot(2800, check)
def check():
    print("tray_ok", getattr(win, "_tray_ok", None), "available", win._tray_available(), flush=True)
    win._hide_to_tray(); app.processEvents()
    mini = getattr(win, "_mini", None)
    print("main_visible", win.isVisible(), "mini", mini is not None and mini.isVisible(), flush=True)
    print("RESULT", "PASS" if (not win.isVisible() and (mini is None or not mini.isVisible())) else "FAIL", flush=True)
    app.quit()
QTimer.singleShot(400, go); app.exec(); hush.shutdown()
