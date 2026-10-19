import os, sys, time, shutil, traceback
sys.path.insert(0, ".")
_data = os.path.abspath("artifacts/qa/r9/data")
shutil.rmtree(_data, ignore_errors=True)
os.environ["HUSHPLAYER_DATA_DIR"] = _data
os.environ["HUSH_CONSOLE"] = "0"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.online import registry as registry_module

errors = []
sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))

folder = Path("artifacts/qa/r9/plugins")
shutil.rmtree(folder, ignore_errors=True)
folder.mkdir(parents=True, exist_ok=True)

def plugin(name, version="0.1.0"):
    return f'''module.exports = {{
    platform: "{name}",
    version: "{version}",
    author: "QA",
    async search(query) {{ return [{{ id: "1", title: name + " / " + query }}]; }},
    async getMediaSource(song) {{ return {{ url: "https://example.com/x.mp3" }}; }},
}};
'''

(folder / "alpha.js").write_text(plugin("批量源 A"), encoding="utf-8")
(folder / "beta.js").write_text(plugin("批量源 B", "0.3.0"), encoding="utf-8")
(folder / "alpha-copy.js").write_text(plugin("批量源 A"), encoding="utf-8")
(folder / "readme.txt").write_text("not a plugin", encoding="utf-8")

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = hush.window

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)

def step1():
    win.navigate("settings", "online")
    pump(1.0)
    page = win._pages["settings"]
    files = registry_module.collect_plugin_files(folder)
    print("collected", [p.name for p in files], flush=True)
    page._install_source_files([str(p) for p in files])
    pump(1.2)
    labels = []
    for i in range(page._source_rows.count()):
        w = page._source_rows.itemAt(i).widget()
        if w and hasattr(w, "title_label"):
            labels.append(w.title_label.text())
    print("rows", labels, flush=True)
    print("installed", [l for l in labels if "批量源" in l], flush=True)
    from PySide6.QtWidgets import QScrollArea
    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar(); bar.setValue(bar.maximum())
    pump(0.4)
    win.grab().save("artifacts/qa/r9/settings_batch_import.png")
    QTimer.singleShot(200, step2)

def step2():
    print("errors", len(errors), flush=True)
    print("RESULT", "PASS" if not errors else "FAIL", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, step1)
app.exec()
