import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r64/data2")
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.queue_panel import QueuePanel

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
tracks = [Track(id=f"kw:{i}", title=f"家书 {i}", artist="加木", album="羲和",
                duration_ms=242000, source_id="x", source_name="user_source_540939a8398b", kind="online")
          for i in range(12)]
ctx().player.queue.set_tracks(tracks)
panel = QueuePanel(); panel.resize(380, 760); panel.layout().activate() if panel.layout() else None
panel.refresh(); app.processEvents()
table = panel.list.table
panel.grab().save("artifacts/qa/r64/queue_crop.png")
print("size", panel.width(), panel.height(), "cols", [table.columnWidth(i) for i in range(6)], "hidden", [table.isColumnHidden(i) for i in range(6)], "scroll", table.verticalScrollBar().isVisible(), "rows", table.model().rowCount(), flush=True)
hush.shutdown()
