import sys
sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.model.track import Track
from hushplayer.ui.widgets.playerbar import PlayerBar
from hushplayer.ui.widgets.tracklist import TrackListWidget

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="light")
bar = PlayerBar(); bar.resize(1100, 96)
bar.info.set_track(Track(id="kw:1", title="Colt.45（Live 版）feat. 加木", artist="弹壳Danko",
                         album="黄金追踪者", duration_ms=242000, kind="online",
                         source_id="x", source_name="user_source_b7866165651c"))
bar.show(); app.processEvents()
bar.grab().save("artifacts/qa/r65/bar_source.png")

rows = TrackListWidget(); rows.resize(860, 300)
rows.set_tracks([
    Track(id="kw:1", title="Colt.45", artist="弹壳Danko", album="黄金追踪者",
          duration_ms=242000, kind="online", source_id="a", source_name="user_source_b7866165651c"),
    Track(id="ne:2", title="家书", artist="加木", album="羲和", duration_ms=242000,
          kind="online", source_id="b", source_name="网易音乐"),
])
rows.show(); app.processEvents()
rows.grab().save("artifacts/qa/r65/rows_source.png")
print("RESULT PASS", flush=True)
QTimer.singleShot(100, app.quit); app.exec()
