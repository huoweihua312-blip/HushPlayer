import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r71/data3")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.25"
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.widgets.menu import themed_menu
from hushplayer.ui.widgets.settings_widgets import SettingCombo

app = QApplication(sys.argv); hush = HushApp(app); hush.start()

menu = themed_menu()
menu.addAction("新建歌单")
menu.addAction("从文件导入歌单…")
menu.addSeparator()
disabled = menu.addAction("检查订阅更新"); disabled.setEnabled(False)
menu.ensurePolished()
menu.resize(menu.sizeHint())
pm = QPixmap(menu.size()); pm.fill(Qt.GlobalColor.transparent)
menu.render(pm); pm.save("artifacts/qa/r71/menu_new.png")
print("menu", menu.size().width(), menu.size().height(), flush=True)

combo = SettingCombo([("过渡动画（从标题栏按钮扩散）", "reveal"), ("全屏日月动画", "sunrise"), ("关闭", "off")])
combo.resize(260, 36); combo.ensurePolished()
view = combo.view(); view.ensurePolished(); view.resize(view.sizeHint())
pm2 = QPixmap(view.size()); pm2.fill(Qt.GlobalColor.transparent)
view.render(pm2); pm2.save("artifacts/qa/r71/combo_new.png")
print("combo", view.size().width(), view.size().height(), flush=True)
print("RESULT PASS", flush=True)
app.quit(); hush.shutdown()
