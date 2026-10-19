import os, sys, time
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r25/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from pathlib import Path
import shutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.services.library import LibraryQuery
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
music = Path("artifacts/qa/r25/music")
if not music.exists():
    shutil.copytree("tests/fixtures/audio", music)
    files = [str(p) for p in music.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    ctx().library.import_files(files)

marks = {}

def run():
    tracks = [t for t in ctx().library.tracks_page(LibraryQuery(sort="title", limit=4)) if t.duration_ms <= 8000][:2]
    if len(tracks) < 2:
        tracks = ctx().library.tracks_page(LibraryQuery(sort="title", limit=2))
    print("tracks", [t.title for t in tracks], [t.duration_ms for t in tracks], flush=True)
    player = ctx().player
    player.state_changed.connect(lambda s: marks.setdefault(s, []).append(time.monotonic()))
    player.position_changed.connect(lambda p: marks.setdefault("pos", []).append((time.monotonic(), p)))
    player.play_tracks(tracks, 0, context="gapless")
    QTimer.singleShot(int(tracks[0].duration_ms + 4000), report)

def report():
    playing = marks.get("playing", [])
    stopped = marks.get("stopped", [])
    print("states", {k: len(v) for k, v in marks.items()}, flush=True)
    if len(playing) >= 2 and stopped:
        gap = (playing[1] - stopped[0]) * 1000
        print(f"switch gap {gap:.0f} ms", flush=True)
    else:
        print("sequence", [(k, [round(x, 3) for x in v]) for k, v in marks.items() if k != "pos"], flush=True)
    ctx().player.stop()
    os._exit(0)

QTimer.singleShot(800, run)
app.exec()
