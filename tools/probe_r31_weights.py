import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r31/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.resize(2560, 1392)

def shot():
    win.navigate("search")
    app.processEvents()
    QTimer.singleShot(400, grab)

def grab():
    img = win.grab()
    img.save("artifacts/qa/r31/weights.png")
    # sidebar left block and search field block, at 1.5 type scale
    img.copy(0, 130, 260, 620).save("artifacts/qa/r31/_nav.png")
    img.copy(260, 60, 800, 90).save("artifacts/qa/r31/_field.png")
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(900, shot)
app.exec()
hush.shutdown()
