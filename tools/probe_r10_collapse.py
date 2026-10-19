import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r10/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]


def pump(seconds=0.6):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def step1():
    ctx().settings.set("online.sources_expanded", False)
    page._show_section(keys.index("online"))
    page._fill_sources()
    pump(1.5)
    print("collapsed rows:", len(page._source_rows.children()), flush=True)
    win.grab().save("artifacts/qa/r10/sources_collapsed.png")
    page._toggle_sources_expanded()
    pump(0.8)
    win.grab().save("artifacts/qa/r10/sources_expanded.png")
    print("expanded setting:", ctx().settings.get("online.sources_expanded"), flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, step1)
app.exec()
