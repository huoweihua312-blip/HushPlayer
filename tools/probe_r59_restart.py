import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r59/data2")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
ctx().settings.set("appearance.ui_scale", "1.5"); ctx().settings.flush()
page = win._page("settings")
print("pref saved:", ctx().settings.get("appearance.ui_scale"), flush=True)
QTimer.singleShot(300, page._restart_app)
app.exec()
print("OLD EXITED", flush=True)
