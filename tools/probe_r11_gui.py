import os, sys, time
root = os.path.abspath("artifacts/qa/r11/data")
os.environ["HUSHPLAYER_DATA_DIR"] = root
os.environ.setdefault("HUSH_CONSOLE", "0")
sys.path.insert(0, ".")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("search")
page = win._pages["search"]

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

pump(2500)
page._on_mode(1)
started = time.monotonic()
page.field.set_text("\u6674\u5929")
page._on_submit("\u6674\u5929")

first_paint = None
while time.monotonic() - started < 20:
    rows = page.online_list.table.model().rowCount()
    if rows > 0 and first_paint is None:
        first_paint = time.monotonic() - started
        win.grab().save("artifacts/qa/r11/search_streaming.png")
        print("first paint %.2fs rows=%d" % (first_paint, rows), flush=True)
    if getattr(page, "_finished", False):
        break
    pump(40)

print("finished %.2fs rows=%d status=%s" % (time.monotonic() - started, page.online_list.table.model().rowCount(), page.online_status.text()), flush=True)

started2 = time.monotonic()
page._on_submit("\u5468\u6770\u4f26")
pump(120)
while time.monotonic() - started2 < 20 and not getattr(page, "_finished", False):
    pump(40)
print("warm search %.2fs rows=%d" % (time.monotonic() - started2, page.online_list.table.model().rowCount()), flush=True)
win.grab().save("artifacts/qa/r11/search_done.png")
hush.shutdown(); app.quit()
