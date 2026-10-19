import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r40/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
win._tray_ok = False
def go():
    win._hide_to_tray()
    QTimer.singleShot(400, done)
def done():
    mini = getattr(win, "_mini", None)
    print("main_visible", win.isVisible(), "mini", mini is not None and mini.isVisible(), flush=True)
    print("RESULT", "PASS" if (not win.isVisible() and mini is not None and mini.isVisible()) else "FAIL", flush=True)
    app.quit()
QTimer.singleShot(500, go); app.exec(); hush.shutdown()
