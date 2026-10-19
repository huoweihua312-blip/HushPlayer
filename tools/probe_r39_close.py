import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data5")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
os.environ.pop("HUSHPLAYER_NO_CLOSE_PROMPT", None)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()
calls = {"n": 0}
def fake():
    calls["n"] += 1
    return "cancel"
win._ask_close_action = fake
def go():
    win.close(); win.close(); win.close()
    QTimer.singleShot(400, done)
def done():
    print("prompt_calls", calls["n"], "visible", win.isVisible(), flush=True)
    print("RESULT", "PASS" if calls["n"] == 1 else "FAIL", flush=True)
    app.quit()
QTimer.singleShot(400, go); app.exec(); hush.shutdown()
