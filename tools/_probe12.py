import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.ui.widgets.settings_widgets import SettingCombo, SettingsCard, SettingRow
app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
w = QWidget(); w.resize(700, 180); l = QVBoxLayout(w)
card = SettingsCard("启动", "测试")
combo = SettingCombo([("首页", "home"), ("歌曲", "songs")])
card.add_row(SettingRow("启动页面", "打开应用时首先显示的页面", control=combo))
l.addWidget(card)
w.show(); app.processEvents()
w.grab().save("artifacts/shots/_combo2.png")
print("palette", combo.palette().base().color().name())
