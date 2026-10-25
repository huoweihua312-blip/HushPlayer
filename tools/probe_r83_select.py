import os, time

os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r83/data"))
import sys
sys.path.insert(0, os.path.abspath("."))
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtGui import QPainter, QColor
from hushplayer.core.theme import theme
from hushplayer.model.track import Track
from hushplayer.ui.widgets.tracklist import TrackTable

class Host(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
theme().apply(mode="light")
tracks = [Track(id=f"local:t{i}", kind="local", title=f"歌曲 {i}", artist="歌手", duration_ms=180000) for i in range(4)]
host = Host(); layout = QVBoxLayout(host); layout.setContentsMargins(0, 0, 0, 0)
table = TrackTable(); table.setMinimumHeight(240); layout.addWidget(table)
table.set_tracks(tracks)
host.resize(900, 320); host.show(); table.show()
for _ in range(10):
    app.processEvents(); time.sleep(0.01)
table.selectRow(0)
for _ in range(10):
    app.processEvents(); time.sleep(0.01)

def sample(img, x, y):
    c = img.pixelColor(x, y); return (c.red(), c.green(), c.blue())

def snap():
    for _ in range(4):
        app.processEvents(); time.sleep(0.01)
    return host.grab().toImage()

r = table.visualRect(table.model().index(0, 0))
y = table.y() + r.top() + r.height() // 2
x_title = table.x() + table.columnViewportPosition(1) + table.columnWidth(1) - 30
x_artist = table.x() + table.columnViewportPosition(2) + 40
img = snap()
print("after select:", sample(img, x_title, y), sample(img, x_artist, y))
vrect = table.visualRect(table.model().index(0, 1))
table.viewport().update(vrect)
img2 = snap()
print("after title-only repaint:", sample(img2, x_title, y), sample(img2, x_artist, y))
img2.save("artifacts/qa/r83_select_fixed.png")
a, b = sample(img2, x_title, y), sample(img2, x_artist, y)
print("PASS" if a != (255,255,255) and abs(a[0]-b[0]) < 8 else "FAIL")
