import os, sys, json
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r3/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.online import models

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
client = ctx().client

def call(fn, timeout=30000):
    box = {}
    loop = QEventLoop()
    fn(lambda r: (box.update(r), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return box

def go():
    srcs = models.build_sources(client.sources)
    for s in srcs:
        print(f"[{s.id[-6:]}] {s.label} play={s.can_play} search={s.searchable}", flush=True)
    target = [s for s in srcs if s.platform in ("kg", "qq", "xiaomi")]
    for s in target:
        r = call(lambda cb, sid=s.id: client.search(sid, "周杰伦 晴天", 1, cb, timeout=25000))
        items = r.get("data") or []
        print(s.id[-6:], s.label, "search ok=", r.get("ok"), "items=", len(items), "err=", (r.get("error") or "")[:120], flush=True)
        if not items:
            continue
        track = models.runtime_track(models.track_from_item(items[0], source=s))
        for q in ("standard", "higher", "320k", "flac", "128k", "high"):
            r2 = call(lambda cb, sid=s.id, q=q: client.resolve_playback(sid, track, cb, quality=q, timeout=25000))
            data = r2.get("data") or {}
            print("   q=", q, "ok=", r2.get("ok"), "url=", (data.get("url") or "")[:60], "err=", (r2.get("error") or "")[:100], flush=True)
            if r2.get("ok"):
                break
    hush.shutdown(); app.quit()

QTimer.singleShot(2500, go)
app.exec()
