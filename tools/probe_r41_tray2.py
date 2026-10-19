import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().settings.set("general.tray_hint_shown", True)
win = ctx().window; win.show(); app.processEvents()
def check():
    print("available", win._tray_available(), flush=True)
    win._hide_to_tray(); app.processEvents()
    mini = getattr(win, "_mini", None)
    print("main_visible", win.isVisible(), "mini", mini is not None and mini.isVisible(), flush=True)
    app.quit()
QTimer.singleShot(2800, check); app.exec(); hush.shutdown()
print("done", flush=True)
