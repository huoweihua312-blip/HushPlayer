import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import QRectF, Qt
from hushplayer.core.theme import apply_theme_to_app, theme, rgba
from hushplayer.core import icons

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
pm = QPixmap(38, 30); pm.fill(Qt.black)
p = QPainter(pm)
p.setRenderHint(QPainter.Antialiasing, True)
r = QRectF(pm.rect())
target = QRectF(0, 0, 15, 15); target.moveCenter(r.center())
print("target", target)
icons.draw(p, "close", target, rgba(theme().palette.text, 0.9))
p.end()
pm.save("artifacts/shots/_drawtest.png")
print("saved", pm.width())
