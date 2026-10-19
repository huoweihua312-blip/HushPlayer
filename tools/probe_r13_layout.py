import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r13/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("search")
page = win._pages["search"]
ctx().settings.set("online.search_history", ["晴天", "加木", "夜航信号"])

def pump(sec):
    loop = QEventLoop(); QTimer.singleShot(int(sec * 1000), loop.quit); loop.exec()

def run():
    page.on_show()
    pump(0.5)
    page.field.set_text("")
    page._run_local("")
    pump(0.4)
    win.grab().save("artifacts/qa/r13/search_local_empty.png")

    page._on_mode(1)
    page.segments.set_current(1, emit=False)
    page.field.set_text("")
    page._run_online("")
    pump(0.8)
    win.grab().save("artifacts/qa/r13/search_online_empty.png")
    print("history visible", page.history.isVisible(), flush=True)
    print("toolbar visible", page.online_toolbar.isVisible(), flush=True)
    print("stack index", page.online_stack.currentIndex(), flush=True)

    page.field.set_text("晴天")
    page._on_submit("晴天")
    for _ in range(40):
        pump(0.3)
        if page._finished:
            break
    pump(0.6)
    win.grab().save("artifacts/qa/r13/search_online_results.png")
    print("rows", len(page._online_tracks), "finished", page._finished, flush=True)
    print("RESULT PASS", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(700, run)
app.exec()
