import os, sys, time
sys.path.insert(0, os.getcwd())
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.join(os.getcwd(), "artifacts", "qa", "r91", "data")
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
from pathlib import Path
Path(os.environ["HUSHPLAYER_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp

out = Path("artifacts/qa/r91"); out.mkdir(parents=True, exist_ok=True)
FIX = Path("tests/fixtures/audio")

def pump(ms=600):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents(); time.sleep(0.015)

qt = QApplication.instance() or QApplication(sys.argv[:1])
app = HushApp(qt)
app.start()
for _ in range(150):
    QApplication.processEvents()
    if app.window is not None: break
    time.sleep(0.02)
win = app.window
app.settings.set("lyrics.online_enabled", False)
app.lyrics._request_lrclib = lambda *a, **k: None
files = sorted(str(p) for p in FIX.rglob("*") if p.is_file())
app.library.import_files(files)
pump(800)
tracks = [t for t in app.library.tracks.list() if t.kind == "local"]
print("TRACKS", len(tracks))
app.player.play_tracks(tracks, 0)
pump(1600)
win.navigate("lyrics")
pump(1400)
page = win._pages.get("lyrics")
print("PAGE", page is not None, getattr(page, "_track", None))
track = page._track
print("OLD_ALBUM", track.album)
win.grab().save(str(out / "lyrics_before.png"))

new_art = Path(os.getcwd(), "assets", "hushplayer.png").as_uri()
with app.library.db.connection() as conn:
    conn.execute("UPDATE tracks SET artwork_url='', artwork_path=?, album=?, album_id=? WHERE id=?",
                 (str(Path(os.getcwd(), 'assets', 'hushplayer.png')), "替换后的专辑", "album:replaced", track.id))
    conn.commit()
calls = []
orig = app.lyrics.request
def spy(t, **kw):
    calls.append(bool(kw.get("force")))
    return orig(t, **kw)
app.lyrics.request = spy
app.library.track_updated.emit(track.id)
pump(1000)
print("NEW_ALBUM", page._track.album)
print("FORCE", calls)
win.grab().save(str(out / "lyrics_after.png"))
ok = page._track.album == "替换后的专辑" and any(calls)
print("RESULT", "PASS" if ok else "FAIL")
app.lyrics.shutdown() if hasattr(app.lyrics, "shutdown") else None
pump(600)
app.quit()







