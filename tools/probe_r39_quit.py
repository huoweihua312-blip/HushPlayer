import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data7")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
os.environ.pop("HUSHPLAYER_NO_CLOSE_PROMPT", None)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

log = open("artifacts/qa/r39/quit_probe.log", "w", encoding="utf-8")
def p(*a): print(*a, file=log, flush=True)

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().settings.set("general.close_action", "quit")
win = ctx().window; win.show(); app.processEvents()
calls = {"n": 0}
def fake():
    calls["n"] += 1
    return "quit"
win._ask_close_action = fake
QTimer.singleShot(300, win.close)
QTimer.singleShot(2500, lambda: (p("still_alive prompts", calls["n"]), app.quit()))
app.exec()
p("loop_exited prompts", calls["n"])
hush.shutdown(); p("shutdown_ok"); log.close()
