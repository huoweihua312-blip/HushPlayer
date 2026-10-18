import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.ui.widgets.settings_widgets import SettingCombo
app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
w = QWidget(); w.resize(300, 120); l = QVBoxLayout(w)
c = SettingCombo([("首页", "home"), ("歌曲", "songs")]); l.addWidget(c)
w.show(); app.processEvents()
w.grab().save("artifacts/shots/_combo.png")
print("style sheet len", len(app.styleSheet()), "c style", c.styleSheet()[:40])
print("combo palette base", c.palette().base().color().name(), c.palette().text().color().name())
