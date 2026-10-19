import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r27/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window

def shot():
    win.grab().save("artifacts/qa/r27/home_empty_150.png")
    win.navigate("settings")
    app.processEvents()
    win.grab().save("artifacts/qa/r27/settings_150.png")
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(900, shot)
app.exec()
hush.shutdown()
