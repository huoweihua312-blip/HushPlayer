import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QPalette
app = QApplication(sys.argv)
for css in ["rgba(255,255,255,0.5)", "rgba(255,255,255,128)", "rgba(255,255,255,50%)"]:
    lbl = QLabel("测试")
    lbl.setStyleSheet(f"color: {css};")
    lbl.show(); app.processEvents()
    img = lbl.grab().toImage()
    # find darkest/brightest pixel
    vals = [img.pixelColor(x, y) for y in range(img.height()) for x in range(img.width())]
    alpha = max(c.alpha() for c in vals)
    print(css, "max alpha", alpha)
