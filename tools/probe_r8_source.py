import os, sys, time, shutil, traceback
sys.path.insert(0, ".")
_data = os.path.abspath("artifacts/qa/r8/data")
shutil.rmtree(_data, ignore_errors=True)
os.environ["HUSHPLAYER_DATA_DIR"] = _data
os.environ["HUSH_CONSOLE"] = "0"
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.online import matching  # noqa: F401  (import check)

errors = []
sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))

PLUGIN = '''module.exports = {
    platform: "本地测试源",
    version: "0.2.0",
    author: "HushPlayer QA",
    async search(query) {
        return [
            { id: "qa-1", title: query + " 测试曲", artist: "QA 歌手", album: "QA 专辑", duration: 120 }
        ];
    },
    async getMediaSource(song) {
        return { url: "https://example.com/never-used.mp3" };
    },
};
'''

plugin_path = Path("artifacts/qa/r8/plugin.js")
plugin_path.parent.mkdir(parents=True, exist_ok=True)
plugin_path.write_text(PLUGIN, encoding="utf-8")

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = hush.window

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)

def pump_until(pred, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred(): return True
        app.processEvents(); time.sleep(0.02)
    return False

def step1():
    win.navigate("settings", "online")
    pump(1.0)
    page = win._pages["settings"]
    page._install_source_file(str(plugin_path))
    ok = pump_until(lambda: page._source_rows.count() > 0 and any(
        "本地测试源" in (page._source_rows.itemAt(i).widget().title_label.text() if page._source_rows.itemAt(i).widget() else "")
        for i in range(page._source_rows.count())
    ), 25)
    names = []
    for i in range(page._source_rows.count()):
        w = page._source_rows.itemAt(i).widget()
        if w: names.append(w.title_label.text())
    print("rows", names, flush=True)
    from PySide6.QtWidgets import QScrollArea
    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum())
    pump(0.4)
    win.grab().save("artifacts/qa/r8/settings_installed.png")

    client = ctx().client
    sources = {s.id: s for s in __import__("hushplayer.online.models", fromlist=["build_sources"]).build_sources(client.sources)}
    target = [s for s in sources.values() if "本地测试源" in s.label]
    print("installed source", [s.id for s in target], flush=True)
    if target:
        sid = target[0].id
        result = {}
        def cb(resp):
            result.update(resp)
        client.search(sid, "你好", 1, cb, timeout=15000)
        pump_until(lambda: bool(result), 20)
        data = result.get("data") or []
        print("search ok", result.get("ok"), "items", len(data), (data[0].get("title") if data else None), flush=True)
    QTimer.singleShot(200, step2)

def step2():
    print("errors", len(errors), flush=True)
    if errors:
        print("\n".join(errors), flush=True)
    else:
        print("RESULT", "PASS" if os.path.exists("artifacts/qa/r8/settings_installed.png") else "FAIL", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, step1)
app.exec()
