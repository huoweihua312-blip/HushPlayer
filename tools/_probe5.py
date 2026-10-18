import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_shots/data")
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.store.db import Database
from hushplayer.services.library import LibraryService

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
db = Database(); db.initialize()
lib = LibraryService(db)
albums = lib.albums()
print("albums", len(albums))
for a in albums[:3]:
    print("A", a.name, "|", a.artwork_path, os.path.exists(a.artwork_path or ""))
a = albums[0]
t = lib.track(a.cover_track_id)
print("cover track", t.title if t else None)
print("pixmap", lib.covers.pixmap(t, 336) if t else "no track")
