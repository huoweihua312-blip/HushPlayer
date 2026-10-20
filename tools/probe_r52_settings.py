import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r52/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(2560, 1392); win.show(); app.processEvents()
def go():
    win.navigate("settings"); app.processEvents()
    win._page("settings")._show_section(1); app.processEvents()
    QTimer.singleShot(700, shot)
def shot():
    win.grab().save("artifacts/qa/r52/settings_appearance.png")
    print("RESULT PASS", flush=True)
    app.quit()
QTimer.singleShot(700, go)
QTimer.singleShot(8000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
