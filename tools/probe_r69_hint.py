import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from hushplayer.core.fonts import load_bundled_fonts

app = QApplication(sys.argv); load_bundled_fonts()
pm = QPixmap(520, 120); pm.fill(QColor("#F4F4F6"))
p = QPainter(pm)
rows = [("Full", QFont.HintingPreference.PreferFullHinting), ("None", QFont.HintingPreference.PreferNoHinting), ("Default", QFont.HintingPreference.PreferDefaultHinting)]
y = 14
for label, hint in rows:
    f = QFont(); f.setFamilies(["MiSans"]); f.setPixelSize(21); f.setWeight(QFont.Weight(600))
    f.setHintingPreference(hint); f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    p.setFont(f); p.setPen(QColor("#1C1B1D")); p.drawText(QPointF(10, y + 20), "播放队列 6 首")
    p.setFont(QFont("MiSans", -1, QFont.Weight(400), False)); 
    small = QFont(); small.setFamilies(["MiSans"]); small.setPixelSize(11); small.setWeight(QFont.Weight(400))
    p.setFont(small); p.setPen(QColor("#8A8A92")); p.drawText(QPointF(300, y + 20), label)
    y += 38
p.end(); pm.save("artifacts/qa/r69/hint_compare.png")
from PIL import Image
im = Image.open("artifacts/qa/r69/hint_compare.png")
im.crop((0, 0, 300, 120)).resize((1200, 480), Image.NEAREST).save("artifacts/qa/r69/hint_compare_4x.png")
print("ok")
