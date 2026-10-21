import os, sys, pathlib
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r66/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.services.playlist_import import import_playlist_file
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in pathlib.Path("tests/fixtures/audio").rglob("*") if p.is_file()])
m3u = pathlib.Path("artifacts/qa/r66/我的歌单.m3u8")
m3u.parent.mkdir(parents=True, exist_ok=True)
m3u.write_text("#EXTM3U\n#EXTINF:12,The Paper Lanterns - Long Way Home\n\n#EXTINF:8,The Paper Lanterns - Paper Lanterns\n\n#EXTINF:0,加木 - 家书\n\n", encoding="utf-8")
summary = import_playlist_file(m3u, ctx().library)
print("summary", summary.matched, "/", summary.total, "missing", summary.unmatched)
win = ctx().window; win.resize(2560, 1392); win.show(); app.processEvents()
def go():
    win.navigate("playlist", summary.playlist_id); app.processEvents()
    QTimer.singleShot(600, shot)
def shot():
    win.grab().save("artifacts/qa/r66/imported_playlist.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(600, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
