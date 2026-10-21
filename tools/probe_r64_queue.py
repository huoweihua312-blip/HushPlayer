import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r64/data")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.queue_panel import QueuePanel

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
queue = ctx().player.queue
tracks = [
    Track(id=f"kw:{i}", title=f"家书 {i}", artist="加木", album="羲和",
          duration_ms=242000, source_id="x", source_name="user_source_540939a8398b", kind="online")
    for i in range(14)
]
queue.set_tracks(tracks)
host = QWidget(); host.resize(900, 620)
layout = QHBoxLayout(host); layout.setContentsMargins(0, 0, 0, 0)
panel = QueuePanel(); layout.addWidget(panel); panel.refresh()
host.show(); app.processEvents()
def shot():
    host.grab().save("artifacts/qa/r64/queue_panel.png")
    table = panel.list.table
    print("panel_w", panel.width(), "dur_col", table.columnWidth(3), "scroll", table.verticalScrollBar().isVisible(), flush=True)
    app.quit()
QTimer.singleShot(600, shot)
app.exec(); hush.shutdown()
