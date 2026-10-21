import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.2"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1180, 1300); win.show(); app.processEvents()
def go():
    win.navigate("settings"); app.processEvents()
    win._page("settings")._show_section(6); app.processEvents()
    QTimer.singleShot(800, shot)
def shot():
    win.grab().save("artifacts/qa/r70/settings_online3.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(800, go)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
