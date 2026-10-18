"""Lyrics service smoke test against a temporary data directory."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEMP = Path(tempfile.mkdtemp(prefix="hush-lyrics-"))
os.environ["HUSHPLAYER_DATA_DIR"] = str(TEMP / "data")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

app = QCoreApplication(sys.argv)

from hushplayer.core.settings import settings  # noqa: E402
from hushplayer.library.metadata import read_track  # noqa: E402
from hushplayer.lyrics.service import LyricsService  # noqa: E402
from hushplayer.store.db import Database  # noqa: E402
from hushplayer.store.repository import (  # noqa: E402
    LyricBindingRepository,
    MetaStore,
    TrackRepository,
)

db = Database()
db.initialize()
tracks = TrackRepository(db)
bindings = LyricBindingRepository(db)
meta = MetaStore(db)

source = ROOT / "tests" / "fixtures" / "audio" / "夜航信号" / "01 - 夜航信号.mp3"
work = TEMP / "music"
work.mkdir(parents=True)
target = work / "01 - 夜航信号.mp3"
shutil.copy2(source, target)

track, cover, error = read_track(str(target))
print("track:", track.title, "/", track.artist, "/", track.duration_ms, "ms cover:", len(cover or b""), error)
tracks.upsert(track)

(work / "01 - 夜航信号.lrc").write_text(
    "[ti:夜航信号]\n[ar:Aurora Field]\n[00:00.50]第一行歌词\n[00:04.00]第二行歌词\n[00:08.00]第三行歌词\n",
    encoding="utf-8",
)

service = LyricsService(tracks, bindings, meta, None)
results: list = []


def on_resolved(result) -> None:
    results.append(result)
    print("status:", result.status, "provider:", result.provider, "kind:", result.document.kind)
    print("lines:", len(result.document.lines), "synced:", result.document.synced)
    for line in result.document.lines:
        print(f"  {line.start_ms:>6}-{line.end_ms:>6} {line.text!r}")
    print("index_at(4500):", result.document.index_at(4500))
    service.set_offset(track, 500)
    print("after offset index_at(4500):", result.document.index_at(4500), "offset:", result.document.offset_ms)
    QTimer.singleShot(10, app.quit)


service.resolved.connect(on_resolved)
QTimer.singleShot(0, lambda: service.request(track))
QTimer.singleShot(15000, app.quit)
app.exec()

# second request hits the cache path
if results:
    again = service.request(track, force=True)
    print("cached doc lines:", len(again.document.lines), "status:", again.status)

db.close_current_thread()
shutil.rmtree(TEMP, ignore_errors=True)
print("TEMP cleaned")


