import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r42/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
os.environ["HUSHPLAYER_TRAY_HOLD"] = "1"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().settings.set("general.tray_hint_shown", True)
win = ctx().window; win.show(); app.processEvents()
def hide():
    win._hide_to_tray(); app.processEvents()
    print("hidden", win.isVisible(), flush=True)
    # keep the process alive so the icon can be inspected in the tray
    QTimer.singleShot(25000, app.quit)
QTimer.singleShot(2800, hide)
app.exec(); hush.shutdown(); print("done", flush=True)
