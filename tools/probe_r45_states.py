import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r45/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
log = []
def step1():
    win.toggle_maximize(); app.processEvents(); log.append(("max", win.isMaximized(), win.width(), win.height()))
    win.toggle_maximize(); app.processEvents(); log.append(("normal", win.isMaximized(), win.width(), win.height()))
    win.showMinimized(); app.processEvents(); log.append(("min", win.isMinimized()))
    win.showNormal(); app.processEvents(); log.append(("restored", win.isMaximized(), win.isMinimized()))
    win.toggle_maximize(); app.processEvents(); log.append(("max2", win.isMaximized()))
    print("STEPS", log, flush=True)
    ok = log[0][1] and not log[1][1] and log[2][2] and not log[4][0] is False
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    app.quit()
QTimer.singleShot(900, step1)
app.exec(); hush.shutdown()
