import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_probe/data")
os.environ["HUSH_CONSOLE"] = "0"
from hushplayer.core.paths import ensure_dirs
from hushplayer.core.logging_setup import setup_logging
from hushplayer.store.db import Database
from hushplayer.store.repository import TrackRepository, MetaStore
from hushplayer.library.artwork import ArtworkStore
from hushplayer.library.scanner import Scanner, walk_audio
setup_logging("WARNING", console=False); ensure_dirs()
db = Database(); db.initialize()
tracks = TrackRepository(db); meta = MetaStore(db); art = ArtworkStore()
music = os.path.abspath("artifacts/tmp_probe/music")
sc = Scanner(tracks, meta, art)
r = sc.import_files(list(walk_audio(music)))
print("imported", r.added, "errors", r.errors)
for a in tracks.albums():
    print("ALBUM", a.name, "| cover_track_id:", a.cover_track_id, "| artwork:", (a.artwork_path or "")[-40:])
for t in tracks.list()[:5]:
    print("TRACK", t.title, "| art:", (t.artwork_path or "NONE")[-45:], os.path.exists(t.artwork_path or ""))
