import os, sys, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data6")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
os.environ.pop("HUSHPLAYER_NO_CLOSE_PROMPT", None)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

log = open("artifacts/qa/r39/close_probe.log", "w", encoding="utf-8")
def p(*a):
    print(*a, file=log, flush=True)

try:
    app = QApplication(sys.argv); hush = HushApp(app); hush.start()
    win = ctx().window; win.show(); app.processEvents()
    p("shown", win.isVisible())
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        p("prompt", calls["n"])
        return "cancel"
    win._ask_close_action = fake
    def go():
        try:
            p("closing x3")
            win.close(); p("after1", win.isVisible())
            win.close(); p("after2", win.isVisible())
            win.close(); p("after3", win.isVisible())
        except Exception:
            traceback.print_exc(file=log)
        QTimer.singleShot(300, done)
    def done():
        p("calls", calls["n"])
        p("RESULT", "PASS" if calls["n"] == 1 else "FAIL")
        app.quit()
    QTimer.singleShot(300, go)
    QTimer.singleShot(6000, lambda: (p("TIMEOUT"), app.quit()))
    app.exec()
    p("loop done")
    hush.shutdown()
    p("shutdown done")
except Exception:
    traceback.print_exc(file=log)
finally:
    log.close()
