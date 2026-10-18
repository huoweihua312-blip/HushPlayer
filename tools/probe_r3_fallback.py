import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r3/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.core.logging_setup import setup_logging
from hushplayer.online import models
from hushplayer.ui.context import ctx

setup_logging(console=False)
app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
player = ctx().player
client = ctx().client

messages = []
player.status_message.connect(lambda text: (messages.append(text), print("status:", text, flush=True)))
player.error_message.connect(lambda text: print("error:", text, flush=True))

def pump(pred, timeout=45000):
    loop = QEventLoop(); dl = QTimer(); dl.setSingleShot(True)
    tm = QTimer(); tm.setInterval(150)
    tm.timeout.connect(lambda: (pred() and (tm.stop(), loop.quit())))
    dl.timeout.connect(loop.quit)
    tm.start(); dl.start(timeout); loop.exec()

def search(source_id, keyword):
    box = {}
    def cb(resp):
        box["resp"] = resp; box["done"] = True
    client.search(source_id, keyword, 1, cb, timeout=20000)
    pump(lambda: box.get("done"), 25000)
    return box.get("resp") or {}

def go():
    client.ensure_started()
    pump(lambda: bool(client.sources), 15000)
    sources = models.build_sources(client.sources)
    kg = next((s for s in sources if "酷狗" in s.label), None)
    print("kg source", kg.id, kg.label, flush=True)
    resp = search(kg.id, "周杰伦 晴天")
    items = resp.get("data") or []
    print("kg results", len(items), flush=True)
    if not items:
        app.quit(); return
    track = models.track_from_item(items[0], source=kg)
    print("track", track.title, track.artist, track.duration_ms, flush=True)
    player.play_tracks([track], 0, context="fallback probe")
    pump(lambda: player.state == "playing", 60000)
    print("state", player.state, "track", (player.current.title if player.current else None),
          "source", (player.current.source_name if player.current else None), flush=True)
    pump(lambda: player.position > 1500 or player.state in ("stopped", "paused"), 25000)
    print("position", player.position, flush=True)
    print("messages", messages, flush=True)
    player.stop(); hush.shutdown(); app.quit()

QTimer.singleShot(120_000, app.quit)
QTimer.singleShot(600, go)
app.exec()
print("exit ok", flush=True)
