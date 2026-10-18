import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
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

def pump(predicate, timeout=30000):
    loop = QEventLoop()
    deadline = QTimer(); deadline.setSingleShot(True)
    timer = QTimer(); timer.setInterval(120)
    def check():
        if predicate():
            timer.stop(); loop.quit()
    timer.timeout.connect(check)
    deadline.timeout.connect(loop.quit)
    timer.start(); deadline.start(timeout)
    loop.exec()

def step1():
    page._on_mode(1)
    page.segments.set_current(1, emit=False)
    page.field.set_text("加木")
    page._on_submit("加木")
    pump(lambda: page.online_list.table.model().rowCount() > 0)
    print("rows", page.online_list.table.model().rowCount(), flush=True)
    print("counts", page.source_filter._pills and {k: p._count for k, p in page.source_filter._pills.items()}, flush=True)
    page.history.set_history(["加木", "周杰伦 晴天", "夜航信号"])
    win.grab().save("artifacts/qa/r2/search_online_pills.png")
    print("saved search", flush=True)
    step2()

def step2():
    win.navigate("settings", "online")
    pump(lambda: True, 400)
    win.grab().save("artifacts/qa/r2/settings_online_manage.png")
    print("saved settings", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(700, step1)
app.exec()
