import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from hushplayer.core import icons
app = QApplication(sys.argv)
for name in ["close","minimize","maximize","restore","shuffle","home","sidebar","search","play"]:
    pm = icons.pixmap(name, "#ffffff", 20, 1.0)
    img = pm.toImage()
    dark = sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x,y).alpha() > 10)
    print(name, pm.size(), "opaque_px=", dark)
