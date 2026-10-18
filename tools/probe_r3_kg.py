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

def call(fn, timeout=25000):
    box = {}
    loop = QEventLoop()
    fn(lambda r: (box.update(r), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return box

def go():
    src = [s for s in models.build_sources(client.sources) if s.platform == "kg"][0]
    r = call(lambda cb: client.search(src.id, "周杰伦 晴天", 1, cb))
    items = r.get("data") or []
    item = items[0]
    print("item keys", sorted(item.keys()), flush=True)
    raw = item.get("raw") or {}
    print("raw keys", sorted(raw.keys())[:30], flush=True)
    print("raw sample", json.dumps({k: raw[k] for k in list(raw)[:8]}, ensure_ascii=False)[:300], flush=True)
    variants = {
        "normalized": item,
        "raw": raw,
        "runtime": models.runtime_track(models.track_from_item(item, source=src)),
        "minimal": {"id": item.get("id"), "songmid": item.get("songmid"), "title": item.get("title"), "artist": item.get("artist")},
    }
    for name, tr in variants.items():
        rr = call(lambda cb, t=tr: client.resolve_playback(src.id, t, cb, quality="standard"))
        d = rr.get("data") or {}
        print(f"{name:10} ok={rr.get('ok')} err={(rr.get('error') or '')[:70]} url={(d.get('url') or '')[:50]}", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(2500, go)
app.exec()
