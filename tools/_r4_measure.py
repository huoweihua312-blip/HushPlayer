import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r4/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = hush.window
win.resize(1600, 900)
bar = win.playerbar

track = Track(id="online:test", kind="online", title="colt.45（Live 版）feat. 加木 - 说唱梦工厂 第 6 期 现场完整收录",
              artist="王睿卓&加木", album="说唱梦工厂", duration_ms=305000,
              source_id="kg", source_name="酷狗 · e4e9e2")

def report():
    bar._on_track(track)
    app.processEvents()
    print("bar", bar.width(), "info", bar.info.width(), bar.info.geometry(), flush=True)
    print("centre", bar.seek.parent().width() if bar.seek.parent() else None, flush=True)
    print("max", bar.info.maximumWidth(), "hint", bar.info.sizeHint().width(), flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(800, report)
app.exec()
