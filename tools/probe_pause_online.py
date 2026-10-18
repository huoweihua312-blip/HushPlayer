import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/probe_pause/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.online import models
from hushplayer.ui import context as appctx

LOG = []
def log(msg):
    LOG.append(str(msg)); print(msg, flush=True)

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
ctx = appctx.ctx()
player = ctx.player; engine = player.engine

def eng(tag):
    p = engine.player
    log(f"[{tag}] ctrl={player.state} eng={engine.state} qt={p.playbackState().name} media={p.mediaStatus().name} pos={p.position()} dur={p.duration()}")

positions = []
player.position_changed.connect(lambda ms: positions.append((round(time.monotonic()-T0,2), ms)))

T0 = time.monotonic()
queue = []
idx = 0

def pick_source(plat):
    return next((s for s in models.build_sources(ctx.client.sources) if plat in s.label or plat in s.platform), None)

def do_search():
    src = pick_source(sys.argv[1] if len(sys.argv) > 1 else "酷我")
    log(f"source={src.id} {src.label} playable={src.can_play}")
    def on_resp(resp):
        global queue
        if not resp.get("ok"):
            log(f"search error {resp.get('error')}"); app.quit(); return
        queue = models.tracks_from_items(resp.get("data") or [], source=src)
        log(f"results={len(queue)}")
        try_play()
    ctx.client.search(src.id, sys.argv[2] if len(sys.argv) > 2 else "晴天 周杰伦", 1, on_resp, timeout=30000)

def try_play():
    global idx
    if idx >= min(6, len(queue)):
        log("none playable"); app.quit(); return
    t = queue[idx]; idx += 1
    log(f"play #{idx} {t.title} / {t.artist}")
    player.play_tracks([t], 0, context="probe")
    QTimer.singleShot(6000, check_playing)

def check_playing():
    if engine.state == "playing":
        eng("playing-6s"); test_pause()
    else:
        eng("failed"); try_play()

def test_pause():
    log("-> pause")
    player.toggle()
    QTimer.singleShot(1800, after_pause)

def after_pause():
    eng("after-pause"); log(f"pos tail={positions[-4:]}")
    log("-> resume")
    player.toggle()
    QTimer.singleShot(1800, after_resume)

def after_resume():
    eng("after-resume"); log(f"pos tail={positions[-4:]}")
    log("-> stop")
    player.stop()
    QTimer.singleShot(1200, after_stop)

def after_stop():
    eng("after-stop"); log(f"pos tail={positions[-3:]}")
    app.quit()

QTimer.singleShot(2200, do_search)
app.exec()
hush.shutdown()
open("artifacts/probe_pause_log.txt", "w", encoding="utf-8").write("\n".join(LOG))
