import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r34/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QApplication, QLineEdit
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.core.theme import theme

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
app_font = QApplication.font(); fi = QFontInfo(app_font)
print("APP", app_font.family(), "pt", app_font.pointSizeF(), "px", app_font.pixelSize(), "w", int(app_font.weight()), "hint", app_font.hintingPreference(), "resolved", fi.family())
win = ctx().window
win.navigate("search")
for w in win.findChildren(QLineEdit):
    f = w.font(); F = QFontInfo(f)
    print("LINEEDIT", f.family(), "pt", f.pointSizeF(), "px", f.pixelSize(), "w", int(f.weight()), "-> resolved", F.family(), F.pointSizeF(), int(F.weight()))
for size, weight in ((9.6, 400), (9.6, 500), (10.5, 400), (10.5, 500)):
    f = theme().font(size, weight); F = QFontInfo(f)
    print("THEME", size, weight, "->", f.pointSizeF(), f.pixelSize(), int(f.weight()), "resolved", F.family(), F.pointSizeF(), int(F.weight()))
print("TYPE", theme().type_scale, theme().ui_scale)
hush.shutdown(); app.quit()
