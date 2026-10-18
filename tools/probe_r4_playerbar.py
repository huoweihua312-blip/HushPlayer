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
bar.resize(1600, bar.height())

track = Track(
    id="online:test", kind="online", title="colt.45（Live 版）feat. 加木 - 说唱梦工厂 第 6 期 现场完整收录",
    artist="王睿卓&加木", album="说唱梦工厂", duration_ms=305000,
    source_id="kg", source_name="酷狗 · e4e9e2",
)

def shot():
    bar._on_track(track)
    bar._on_position(111000)
    bar._on_duration(305000)
    app.processEvents()
    bar.grab().save("artifacts/qa/r4/playerbar_long.png")
    bar._on_loading(True, "")
    app.processEvents()
    bar.grab().save("artifacts/qa/r4/playerbar_loading.png")
    win.resize(1000, 820)
    app.processEvents()
    QTimer.singleShot(150, shot2)

def shot2():
    bar.grab().save("artifacts/qa/r4/playerbar_narrow.png")
    print("saved", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, shot)
app.exec()
