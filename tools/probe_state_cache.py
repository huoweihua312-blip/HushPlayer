"""Session state + cache service smoke test in a temporary data directory."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEMP = Path(tempfile.mkdtemp(prefix="hush-state-"))
os.environ["HUSHPLAYER_DATA_DIR"] = str(TEMP / "data")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from hushplayer.audio.controller import PlayerController  # noqa: E402
from hushplayer.core import paths  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.library.artwork import ArtworkStore  # noqa: E402
from hushplayer.library.metadata import read_track  # noqa: E402
from hushplayer.library.scanner import Scanner  # noqa: E402
from hushplayer.online.proxy import AudioProxy  # noqa: E402
from hushplayer.services.cache import CacheService  # noqa: E402
from hushplayer.services.state import PlaybackKeeper, queue_file  # noqa: E402
from hushplayer.store.db import Database  # noqa: E402
from hushplayer.store.repository import MetaStore, TrackRepository  # noqa: E402

paths.ensure_dirs()
setup_logging("INFO", console=False)
db = Database()
db.initialize()
tracks = TrackRepository(db)
meta = MetaStore(db)
artwork = ArtworkStore()
scanner = Scanner(tracks, meta, artwork)
result = scanner.import_files([str(ROOT / "tests" / "fixtures" / "audio" / "夜航信号" / "01 - 夜航信号.mp3"),
                               str(ROOT / "tests" / "fixtures" / "audio" / "夜航信号" / "02 - 凌晨四点的海.flac")])
print("scan:", result.to_dict())

items = tracks.list(limit=10)
print("tracks:", [(t.title, t.duration_ms) for t in items])

controller = PlayerController()
controller.configure(volume=0.5)
keeper = PlaybackKeeper(controller, tracks)
controller.play_tracks(items, 1, context="专辑 · 夜航信号")
print("queue count:", controller.queue.count, "current:", controller.queue.current.title)

# simulate a playhead without touching the audio device
controller._position = 4321  # noqa: SLF001 - deliberate probe
keeper.save_now()
print("state file:", queue_file(), os.path.isfile(queue_file()))
with open(queue_file(), "r", encoding="utf-8") as handle:
    payload = json.load(handle)
print("saved:", payload["current_id"], payload["position_ms"], len(payload["tracks"]), payload["context"])

controller.queue.clear()
print("cleared:", controller.queue.count)

keeper2 = PlaybackKeeper(controller, tracks)
position = keeper2.restore()
print("restored count:", controller.queue.count, "position:", position,
      "current:", controller.queue.current.title if controller.queue.current else None,
      "shuffle:", controller.queue.shuffle, "repeat:", controller.queue.repeat)
assert controller.queue.count == 2 and position == 4321

# cache service
proxy = AudioProxy()
svc = CacheService(proxy, artwork)
folder = Path(paths.audio_cache_dir())
folder.mkdir(parents=True, exist_ok=True)
(folder / "deadbeef.mp3").write_bytes(b"0123456789")
(folder / "deadbeef.meta.json").write_text(json.dumps({"complete": True, "size": 5}), encoding="utf-8")
(folder / "cafe.mp3").write_bytes(b"orphan")
stats = svc.stats()
print("stats:", stats.to_dict())
repair = svc.repair()
print("repair:", repair.to_dict())
print("after repair files:", sorted(p.name for p in folder.iterdir()))
print("summary:", svc.summary_text())

controller.shutdown()
proxy.shutdown()
db.close_current_thread()
import shutil  # noqa: E402

shutil.rmtree(TEMP, ignore_errors=True)
print("OK")
