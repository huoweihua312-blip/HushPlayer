import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from hushplayer.core.fonts import load_bundled_fonts

app = QApplication(sys.argv)
load_bundled_fonts()
text = "播放队列 6 首 · HushPlayer"
variants = []
for label, weight, hint, families in [
    ("w600 family=MiSans hint=Full (current)", 600, QFont.HintingPreference.PreferFullHinting, ["MiSans"]),
    ("w600 family=MiSans hint=Default", 600, QFont.HintingPreference.PreferDefaultHinting, ["MiSans"]),
    ("w600 family=MiSans Semibold hint=Default", 600, QFont.HintingPreference.PreferDefaultHinting, ["MiSans Semibold", "MiSans"]),
    ("w500 family=MiSans hint=Default", 500, QFont.HintingPreference.PreferDefaultHinting, ["MiSans"]),
    ("w700 family=MiSans hint=Default", 700, QFont.HintingPreference.PreferDefaultHinting, ["MiSans"]),
]:
    variants.append((label, weight, hint, families))

pm = QPixmap(760, 40 * len(variants) + 20)
pm.fill(QColor("#F4F4F6"))
p = QPainter(pm)
p.setRenderHint(QPainter.Antialiasing, True)
p.setRenderHint(QPainter.TextAntialiasing, True)
y = 20
for label, weight, hint, families in variants:
    f = QFont(); f.setFamilies(families); f.setPixelSize(21); f.setWeight(QFont.Weight(weight))
    f.setHintingPreference(hint); f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    p.setFont(f); p.setPen(QColor("#8A8A92")); p.drawText(QPointF(14, y - 4), label)
    p.setPen(QColor("#1C1B1D")); p.drawText(QPointF(14, y + 22), text)
    y += 40
p.end()
pm.save("artifacts/qa/r69/font_variants.png")
print("saved")
