import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_shots/data")
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.store.db import Database
from hushplayer.services.library import LibraryService
from hushplayer.ui.widgets.cards import AlbumCard, cover_pixmap
from hushplayer.ui import context

app = QApplication(sys.argv); apply_theme_to_app(app, preference="dark")
db = Database(); db.initialize(); lib = LibraryService(db)
class Ctx: pass
c = Ctx(); c.library = lib; c.covers = lib.covers
context.set_context(c)
a = lib.albums()[0]
print("direct", cover_pixmap(a, 300))
card = AlbumCard(a, size=150)
print("card pixmap", card._pixmap)
