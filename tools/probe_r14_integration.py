import os, sys, pathlib
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r14/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
import shutil, tempfile

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
data = pathlib.Path(os.environ["HUSHPLAYER_DATA_DIR"])
music = data / "music"
if not music.exists():
    shutil.copytree("tests/fixtures/audio", music)
    hush.library.import_files([str(p) for p in music.rglob("*") if p.suffix in {".mp3", ".flac", ".wav", ".ogg"}])

def pump(sec):
    loop = QEventLoop(); QTimer.singleShot(int(sec*1000), loop.quit); loop.exec()

def run():
    it = hush.integration
    from hushplayer.services.library import LibraryQuery
    tracks = hush.library.tracks_page(LibraryQuery(limit=1))
    print("tracks", len(tracks), flush=True)
    if tracks:
        hush.player.play_track(tracks[0]); pump(1.2)
        print("state", hush.player.state, "pos>0", hush.player.position > 0, flush=True)
        # simulate a hardware "pause" button from SMTC
        from winrt.windows.media import SystemMediaTransportControlsButton as B
        class Args: button = B.PAUSE
        it.smtc._on_button(None, Args()); pump(0.6)
        print("after smtc pause", hush.player.state, flush=True)
        class Args2: button = B.PLAY
        it.smtc._on_button(None, Args2()); pump(0.8)
        print("after smtc play", hush.player.state, flush=True)
        hush.player.stop(); pump(0.3)
    print("RESULT PASS", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, run)
app.exec()
