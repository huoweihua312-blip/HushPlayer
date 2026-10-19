import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r36/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.resize(2560, 1392)
steps = []
def grab(tag):
    win.grab().save(f"artifacts/qa/r36/{tag}.png")
def seq():
    win.navigate("songs"); app.processEvents(); QTimer.singleShot(300, lambda: (grab("songs"), step2()))
def step2():
    settings = ctx().window.findChild(type(ctx().window._page("settings")), None)
    win.navigate("settings"); app.processEvents()
    page = ctx().window._page("settings")
    page.show_section("appearance") if hasattr(page, "show_section") else None
    QTimer.singleShot(400, lambda: (grab("settings"), step3()))
def step3():
    win.navigate("home"); app.processEvents(); QTimer.singleShot(400, lambda: (grab("home"), finish()))
def finish():
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(800, seq); app.exec(); hush.shutdown()
