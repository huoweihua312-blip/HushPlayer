import sys
sys.path.insert(0, ".")
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QHelpEvent
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.model.track import Track
from hushplayer.ui.widgets import hover_tip
from hushplayer.ui.widgets.tracklist import TrackListWidget

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="light")
w = TrackListWidget(); w.resize(320, 260)
w.set_tracks([
    Track(id="kw:1", title="Colt.45", artist="弹壳Danko", album="黄金追踪者",
          duration_ms=180000, source_id="x", source_name="user_source_540939a8398b",
          kind="online"),
    Track(id="kw:2", title="家书", artist="加木", album="羲和", duration_ms=242000,
          source_id="y", source_name="酷我", kind="online"),
])
w.show(); app.processEvents()
w.grab().save("artifacts/qa/r63/queue_rows.png")
table = w.table
idx = table.indexAt(QPoint(60, 40))
ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(60, 40), table.viewport().mapToGlobal(QPoint(60, 40)))
consumed = table.eventFilter(table.viewport(), ev)
print("consumed", consumed, "valid", idx.isValid())
tip = hover_tip._TIP
print("tip visible", tip.isVisible() if tip else None)
if tip is not None and tip.isVisible():
    tip.grab().save("artifacts/qa/r63/tooltip_light.png")
    print("tip size", tip.size().width(), tip.size().height())
QTimer.singleShot(100, app.quit); app.exec()
