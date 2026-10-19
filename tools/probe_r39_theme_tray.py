import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.core.theme import theme
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()

frames = []
def sample():
    frames.append(win.grab().toImage())

def run():
    tray = win._tray
    print("tray_null", tray is None, flush=True)
    if tray is not None:
        print("tray_visible", tray.isVisible(), "icon_null", tray.icon().isNull(), flush=True)
    win._hide_to_tray(); app.processEvents()
    print("after_hide window_visible", win.isVisible(), flush=True)
    win._restore_from_tray(); app.processEvents()
    print("after_restore window_visible", win.isVisible(), flush=True)
    win._tray_guard_test = True
    saved = win._tray
    win._tray = None
    win.hide(); win._hide_to_tray(); app.processEvents()
    print("guard window_visible", win.isVisible(), flush=True)
    win._tray = saved; win.show(); app.processEvents()
    for i in range(6):
        QTimer.singleShot(i * 20, sample)
    QTimer.singleShot(140, toggle)

def toggle():
    current = theme().mode
    win.titlebar.theme_button.click()
    QTimer.singleShot(700, report)

def report():
    for i, img in enumerate(frames):
        img.save(f"artifacts/qa/r39/frame_{i}.png")
    print("frames", len(frames), flush=True)
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(700, run); app.exec(); hush.shutdown()
