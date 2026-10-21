import sys
sys.path.insert(0, ".")
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QToolTip, QWidget
from hushplayer.core.theme import apply_theme_to_app

app = QApplication(sys.argv)
print("style", app.style().name())
apply_theme_to_app(app, preference="light")
host = QWidget(); host.resize(400, 300); host.show()
QToolTip.showText(QPoint(150, 150), "Colt.45 · 弹壳Danko\n来源：user_source_07866165651c", host)
app.processEvents()
labels = [w for w in QApplication.topLevelWidgets() if w.metaObject().className() in ("QLabel", "QTipLabel")]
print("tooltip widgets", [(w.metaObject().className(), w.size().width(), w.size().height()) for w in labels])
for w in labels:
    pm = w.grab(); img = pm.toImage()
    print("corner", img.pixelColor(2, 2).name(), "middle", img.pixelColor(img.width()//2, img.height()//2).name())
    pm.save("artifacts/qa/r63/tooltip.png")
    break
QTimer.singleShot(150, app.quit)
app.exec()
