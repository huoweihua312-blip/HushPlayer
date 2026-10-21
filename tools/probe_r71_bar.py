import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r71/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.25"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.playerbar import PlayerBar

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
bar = PlayerBar()
bar.setFixedWidth(1500)
bar.show(); app.processEvents(); app.processEvents()
bar.info.set_track(Track(id="kw:1", title="家书", artist="加木", album="羲和", duration_ms=242000, source_id="netease", source_name="网易音乐", kind="online"))
bar.play.set_playing(True); bar.shuffle.setChecked(True); bar.repeat.setChecked(True)
app.processEvents(); app.processEvents()
bar.grab().save("artifacts/qa/r71/bar_controls.png")
print("RESULT PASS", flush=True)
app.quit(); hush.shutdown()
