import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r13/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("search")
page = win._pages["search"]

def report():
    page._on_mode(1); page.field.set_text(""); page._run_online("")
    app.processEvents()
    e = page.online_empty
    print("empty visible", e.isVisible(), "geom", e.geometry(), "minh", e.minimumHeight(), flush=True)
    print("page visible", page._online_empty_page.isVisible(), page._online_empty_page.geometry(), flush=True)
    print("stack geom", page.online_stack.geometry(), "idx", page.online_stack.currentIndex(), flush=True)
    print("history", page.history.geometry(), flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(800, report)
app.exec()
