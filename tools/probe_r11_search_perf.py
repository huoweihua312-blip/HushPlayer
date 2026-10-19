import os, sys, shutil, time

root = os.path.abspath("artifacts/qa/r11/data")
shutil.rmtree(root, ignore_errors=True)
os.makedirs(root, exist_ok=True)
os.environ["HUSHPLAYER_DATA_DIR"] = root
os.environ.setdefault("HUSH_CONSOLE", "0")
sys.path.insert(0, ".")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.online import registry as registry_mod
from hushplayer.online.client import OnlineSourceClient
from hushplayer.online import models

count = int(sys.argv[1]) if len(sys.argv) > 1 else 64
reg = registry_mod.registry()
reg.ensure()
netease = next(s for s in reg.entries() if str(s.get("id", "")).endswith("52a08ed9d22b"))
base = (reg.home / netease["filename"]).read_text(encoding="utf-8")

while len(reg.entries()) < count:
    index = len(reg.entries())
    tmp = reg.home / "user_sources" / ("bench_%d.js" % index)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(base + "\n// benchmark variant %d\n" % index, encoding="utf-8")
    try:
        reg.install_file(tmp, content_policy="user_owned")
    finally:
        tmp.unlink(missing_ok=True)

print("sources:", len(reg.entries()), flush=True)

app = QApplication(sys.argv[:1])
client = OnlineSourceClient()
sources = []


def wait(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def on_sources(items):
    global sources
    sources = models.build_sources(items)


client.sources_changed.connect(on_sources)
client.ensure_started()
wait(3.0)
client.refresh_sources()
wait(4.0)
print("loaded:", len(sources), flush=True)

keyword = sys.argv[2] if len(sys.argv) > 2 else "\u6674\u5929"
started = time.monotonic()
result = {"first": None, "pending": 0, "tracks": 0}


def run():
    targets = [s for s in sources if s.enabled and s.searchable]
    result["pending"] = len(targets)
    print("searching", len(targets), flush=True)
    for source in targets:
        client.search(source.id, keyword, 1, lambda response, sid=source.id: done(sid, response), timeout=9000)


def done(source_id, response):
    result["pending"] -= 1
    if response.get("ok") and response.get("data"):
        result["tracks"] += len(response["data"])
        if result["first"] is None:
            result["first"] = time.monotonic() - started
            print("first result %.2fs" % result["first"], flush=True)
    if result["pending"] <= 0:
        print("all done %.2fs tracks=%d" % (time.monotonic() - started, result["tracks"]), flush=True)
        QTimer.singleShot(50, app.quit)


QTimer.singleShot(300, run)
QTimer.singleShot(30000, app.quit)
app.exec()
client.stop()
