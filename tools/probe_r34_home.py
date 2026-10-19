import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r34/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.resize(2560, 1392)
def shot():
    win.navigate("home"); app.processEvents(); QTimer.singleShot(400, grab)
def grab():
    win.grab().save("artifacts/qa/r34/home_150.png"); print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(900, shot); app.exec(); hush.shutdown()
