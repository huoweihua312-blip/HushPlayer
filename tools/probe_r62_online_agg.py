import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r62/data")
import shutil
shutil.rmtree(os.environ["HUSHPLAYER_DATA_DIR"], ignore_errors=True)
from pathlib import Path
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
lib = ctx().library
for p in Path("tests/fixtures/audio").rglob("*"):
    if p.is_file(): lib.import_files([str(p)])
online = Track(id="kw:99", title="家书", artist="加木", album="羲和", duration_ms=242000,
               source_id="kw", source_name="酷我", kind="online")
lib.toggle_favorite(online)
lib.record_play(online)
print("albums", [a.name for a in lib.albums()])
print("artist_has_jiamu", any(a.name == "加木" for a in lib.artists()))
print("recent", [t.title for t in lib.recent(limit=5)])
fav_albums = [a.name for a in lib.albums() if a.name == "羲和"]
print("online_album_present", bool(fav_albums))
hush.shutdown()
