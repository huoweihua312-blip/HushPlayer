import os, sys, json
sys.path.insert(0, ".")
from PySide6.QtCore import QCoreApplication, QTimer
from hushplayer.online.client import OnlineSourceClient
from hushplayer.online import models
import requests

app = QCoreApplication(sys.argv)
c = OnlineSourceClient()

def on_search(r):
    items = r.get("data") or []
    t = models.track_from_item(items[0])
    print("TRACK", t.title, t.artist, t.source_id)
    c.resolve_playback(t.source_id, models.runtime_track(t), lambda res: on_res(res, t))

def on_res(r, t):
    print("OK", r.get("ok"))
    if not r.get("ok"):
        print(r.get("error")); app.quit(); return
    d = r["data"]
    print("URL", d.get("url"))
    print("HEADERS", json.dumps({k: str(v)[:60] for k, v in (d.get("headers") or {}).items()}, ensure_ascii=False))
    print("MIME", d.get("mimeType"), "expires", d.get("expiresAt"))
    try:
        resp = requests.get(d["url"], headers=d.get("headers") or {}, stream=True, timeout=15)
        print("GET", resp.status_code, resp.headers.get("Content-Type"), resp.headers.get("Content-Length"))
        chunk = next(resp.iter_content(2048), b"")
        print("first bytes", len(chunk), chunk[:16])
    except Exception as exc:
        print("ERR", exc)
    app.quit()

def begin():
    c.ensure_started()
    QTimer.singleShot(1500, lambda: c.search("custom_source_52a08ed9d22b", "周杰伦 晴天", 1, on_search, timeout=25000))

QTimer.singleShot(200, begin)
QTimer.singleShot(60000, app.quit)
app.exec()
c.stop()
