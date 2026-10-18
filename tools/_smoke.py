import sys, os, tempfile
sys.path.insert(0, ".")
tmp = tempfile.mkdtemp()
os.environ["HUSHPLAYER_DATA_DIR"] = tmp
from hushplayer.store.db import Database
from hushplayer.store.repository import TrackRepository, PlaylistRepository, MetaStore
from hushplayer.model.track import Track, local_track_id
from hushplayer.lyrics.parser import parse
db = Database(os.path.join(tmp, "test.db"))
tr = TrackRepository(db)
tr.upsert_many([Track(id="local:a", kind="local", title="Alpha", artist="A", album="X", duration_ms=1000, path=os.path.join(tmp,"a.mp3"))])
print("count", tr.count(), "stats", tr.stats())
print("search", [t.title for t in tr.search_local("alp")])
doc = parse("[00:01.00]hello <00:01.50>world\n[00:03.00](100,200,0)你(300,200,0)好")
print("lines", len(doc.lines), doc.lines[0].text, doc.lines[0].words, doc.lines[1].text, doc.lines[1].words)
print("idx@2500", doc.index_at(2500), doc.lines[1].start_ms)
