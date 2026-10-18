import os, sys, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_shots/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
app = QApplication(sys.argv)
h = HushApp(app); h.start(); h.window.resize(1280, 820); h.window.show(); app.processEvents()
from hushplayer.ui.pages.songs import SongsPage
try:
    page = SongsPage()
    print("built ok", page.size(), page.isVisible())
    h.window.stack.addWidget(page)
    h.window.stack.setCurrentWidget(page)
    app.processEvents()
    print("after set", page.size(), page.findChildren(type(page.list))[:1].__len__())
    print("header", page.header.geometry() if hasattr(page, "header") else None)
    print("list", page.list.geometry() if hasattr(page, "list") else None)
    print("tracks", len(page.list.tracks()))
    print("layout count", page.content_layout.count())
except Exception:
    traceback.print_exc()
h.shutdown()
