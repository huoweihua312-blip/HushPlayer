import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from hushplayer.core import theme
from hushplayer.model.track import Track
from hushplayer.ui.widgets.tracklist import TrackListWidget

app = QApplication(sys.argv)
theme().apply_theme_type_scale()
host = QWidget(); host.resize(1100, 700)
layout = QVBoxLayout(host)
lst = TrackListWidget(); layout.addWidget(lst)
tracks = [
    Track(title=f"茶花开了，该回家了 第{i+1}版", artist="王睿卓、加木", album="茶花开了，该回家了", duration_ms=180000, source_id="kw", source_name="酷我")
    for i in range(6)
]
lst.set_tracks(tracks)
host.show()
def shot():
    host.grab().save("artifacts/qa/r37/offline_rows.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(700, shot); app.exec()
