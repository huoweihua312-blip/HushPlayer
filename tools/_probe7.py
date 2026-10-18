import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_shots/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui import context
app = QApplication(sys.argv)
h = HushApp(app); h.start()
h.window.resize(1280, 820); h.window.show()
app.processEvents()
page = h.window._page("home")
print("page", type(page).__name__)
from hushplayer.ui.widgets.cards import AlbumCard
cards = page.findChildren(AlbumCard)
print("cards", len(cards))
for c in cards[:4]:
    print("card", c._title, "pix", c._pixmap is not None, c._pixmap.size() if c._pixmap else None)
al = context.ctx().library.albums()[0]
print("album", al.name, "art", os.path.exists(al.artwork_path), "pix", context.ctx().covers.pixmap(al if False else context.ctx().library.track(al.cover_track_id), 150))
h.shutdown()
