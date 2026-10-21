import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r68/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.queue_panel import QueuePanel

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
settings = ctx().settings
settings.set("appearance.theme", "light")
panel = QueuePanel(immersive=True)
panel.resize(428, 620)
panel.activate_palette()
panel.refresh_theme()
panel.list.set_tracks([
    Track(id=f"kw:{i}", title=f"Colt.45（Live 版）{i}", artist="弹壳Danko", album="黄金追踪者", duration_ms=179000, source_id="user_source_x", source_name="自建音源", kind="online")
    for i in range(6)
])
panel.list.set_current("kw:0", True)
panel.count.setText("6 首")
panel.show(); app.processEvents(); app.processEvents()
panel.grab().save("artifacts/qa/r68/queue_dark.png")
print("RESULT PASS", panel.palette().color(panel.backgroundRole()).name())
app.quit(); hush.shutdown()
