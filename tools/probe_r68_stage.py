import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r68/data4")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.queue_panel import QueuePanel

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().settings.set("appearance.theme", "light")

class Stage(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0.0, QColor("#3a1d22"))
        g.setColorAt(0.55, QColor("#6b3038"))
        g.setColorAt(1.0, QColor("#1a1416"))
        p.fillRect(self.rect(), g)

stage = Stage(); stage.resize(900, 620)
panel = QueuePanel(stage, immersive=True)
panel.resize(428, 620); panel.move(900 - 428, 0)
panel.activate_palette()
panel.list.set_tracks([
    Track(id=f"kw:{i}", title=f"家书 {i}", artist="加木", album="羲和", duration_ms=242000, source_id="netease", source_name="网易音乐", kind="online")
    for i in range(5)
])
panel.list.set_current("kw:1", True)
panel.count.setText("5 首")
panel.show(); stage.show(); app.processEvents(); app.processEvents()
stage.grab().save("artifacts/qa/r68/stage_queue.png")
print("RESULT PASS")
app.quit(); hush.shutdown()
