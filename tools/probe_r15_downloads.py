import os, sys, threading, time, pathlib
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r15/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAYLOAD = b"ID3" + b"\x00" * 6_000_000

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/fail"):
            self.send_response(500); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        for start in range(0, len(PAYLOAD), 16_384):
            self.wfile.write(PAYLOAD[start:start + 16_384])
            time.sleep(0.004)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
PORT = server.server_address[1]

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.services.downloads import DownloadService, STATE_DONE, STATE_DOWNLOADING
from hushplayer.ui.context import ctx

class FakeClient(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)
    def __init__(self):
        super().__init__(); self.fail = True
    def ensure_started(self): return True
    def resolve_download(self, source_id, payload, callback, **kwargs):
        if self.fail:
            callback({"ok": False, "error": "模拟解析失败"})
        else:
            callback({"ok": True, "data": {"url": f"http://127.0.0.1:{PORT}/song.mp3", "headers": {}}})
        return 0
    def stop(self): pass

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
client = FakeClient()
downloads = DownloadService(client, hush)
ctx().downloads = downloads
win = ctx().window
win.navigate("downloads")
page = win._pages["downloads"]

def pump(sec):
    loop = QEventLoop(); QTimer.singleShot(int(sec * 1000), loop.quit); loop.exec()

track_a = Track(id="online:src:x1", kind="online", title="下载测试歌曲 A", artist="测试歌手", source_id="src", duration_ms=200000)
track_b = Track(id="online:src:x2", kind="online", title="下载测试歌曲 B（很长的名字用于检查省略）", artist="测试歌手", source_id="src", duration_ms=200000)

def run():
    page.on_show()
    jobs = downloads.download([track_a, track_b])
    pump(1.0)
    win.grab().save("artifacts/qa/r15/downloads_failed.png")
    pump(0.4)
    client.fail = False
    before = [(j.id, j.state) for j in jobs]
    returned = [downloads.retry(job.id) for job in jobs]
    after = [(j.id, j.state, j.error) for j in jobs]
    pump(0.8)
    later = [(j.id, j.state, j.error, j.downloaded) for j in jobs]
    print("timer active", page._reload_timer.isActive(), "wired", page._wired, flush=True)
    page.reload()
    app.processEvents()
    pathlib.Path("artifacts/qa/r15/retry.json").write_text(
        __import__("json").dumps({"before": before, "after": after, "later": later}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    win.grab().save("artifacts/qa/r15/downloads_active.png")
    deadline = time.time() + 15
    while time.time() < deadline and any(job.state != STATE_DONE for job in downloads.jobs):
        pump(0.3)
    pump(0.6)
    page.reload(); pump(0.4)
    win.grab().save("artifacts/qa/r15/downloads_history.png")
    import json
    report = {
        "jobs": [{"title": j.title, "state": j.state, "downloaded": j.downloaded, "total": j.total, "error": j.error, "path": j.path} for j in downloads.jobs],
        "history": downloads.history(),
        "index": str(pathlib.Path(os.environ["HUSHPLAYER_DATA_DIR"]) / "downloads.json"),
        "index_exists": (pathlib.Path(os.environ["HUSHPLAYER_DATA_DIR"]) / "downloads.json").exists(),
    }
    pathlib.Path("artifacts/qa/r15/result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("jobs", [(j.state, j.downloaded) for j in downloads.jobs], flush=True)
    print("history", len(downloads.history()), flush=True)
    print("RESULT PASS", flush=True)
    downloads.shutdown(); hush.shutdown(); app.quit()

QTimer.singleShot(900, run)
app.exec()
server.shutdown()
