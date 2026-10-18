import os, sys, time
from urllib.parse import urlparse
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/probe_wy/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.online import models
from hushplayer.ui import context as appctx

LOG = []
def log(msg):
    LOG.append(str(msg)); print(str(msg), flush=True)

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
ctx = appctx.ctx()
player = ctx.player; engine = player.engine; client = ctx.client

for sig, name in ((player.state_changed, "ctrl"), (engine.state_changed, "eng")):
    sig.connect(lambda s, n=name: log(f"  state {n} -> {s}"))
player.loading_changed.connect(lambda busy, hint: log(f"  loading busy={busy} hint={hint}"))

orig_resolve = client.resolve_playback
def wrapped(source_id, track, callback, **kw):
    def cb(resp):
        data = resp.get("data") or {}
        url = data.get("url") or ""
        host = urlparse(url).hostname if url else ""
        log(f"  resolve ok={resp.get('ok')} host={host} err={resp.get('error')}")
        callback(resp)
    return orig_resolve(source_id, track, cb, **kw)
client.resolve_playback = wrapped

T0 = time.monotonic()
positions = []
player.position_changed.connect(lambda ms: positions.append((round(time.monotonic()-T0,2), ms)))
idx = 0
tracks = []

def start():
    src = next(s for s in models.build_sources(client.sources) if "网易" in s.label)
    log(f"source={src.id} {src.label} playable={src.can_play} download={src.can_download}")
    def on_resp(resp):
        global tracks
        if not resp.get("ok"):
            log(f"search error {resp.get('error')}"); app.quit(); return
        tracks = models.tracks_from_items(resp.get("data") or [], source=src)
        log(f"results={len(tracks)} first={tracks[0].title if tracks else '-'}")
        attempt()
    client.search(src.id, "周杰伦 稻香", 1, on_resp, timeout=30000)

def attempt():
    global idx
    if idx >= min(5, len(tracks)):
        log("no playable"); app.quit(); return
    t = tracks[idx]; idx += 1
    log(f"try #{idx}: {t.title} / {t.artist} dur={t.duration_ms}")
    player.play_tracks([t], 0, context="probe")
    QTimer.singleShot(7000, check)

def check():
    if engine.state == "playing":
        eng("playing")
        log("-> pause"); player.toggle()
        QTimer.singleShot(2000, after_pause)
    else:
        eng("failed"); attempt()

def eng(tag):
    p = engine.player
    log(f"[{tag}] ctrl={player.state} eng={engine.state} qt={p.playbackState().name} media={p.mediaStatus().name} pos={p.position()} err={p.errorString()!r}")

def after_pause():
    eng("after-pause"); log(f"pos tail={positions[-3:]}")
    log("-> resume"); player.toggle()
    QTimer.singleShot(2500, after_resume)

def after_resume():
    eng("after-resume"); log(f"pos tail={positions[-3:]}")
    log("-> stop"); player.stop()
    QTimer.singleShot(1500, after_stop)

def after_stop():
    eng("after-stop"); log(f"pos tail={positions[-2:]}")
    app.quit()

QTimer.singleShot(2200, start)
app.exec()
hush.shutdown()
open("artifacts/probe_wy_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
