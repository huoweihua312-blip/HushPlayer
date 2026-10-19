import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r37/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(2560, 1392)
page = win._page("search")
def start():
    win.navigate("search"); app.processEvents()
    page._segmented.set_value("online") if hasattr(page, "_segmented") else None
    page._search.setText("加木")
    QTimer.singleShot(9000, shot)
def shot():
    win.grab().save("artifacts/qa/r37/online_rows.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(800, start); app.exec(); hush.shutdown()
