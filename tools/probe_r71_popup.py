import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r71/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.25"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.widgets.menu import themed_menu
from hushplayer.ui.widgets.settings_widgets import SettingCombo

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
menu = themed_menu(); menu.addAction("新建歌单"); menu.addAction("从文件导入歌单…"); menu.addSeparator(); a = menu.addAction("检查订阅更新"); a.setEnabled(False)
combo = SettingCombo([("过渡动画（从标题栏按钮扩散）", "reveal"), ("全屏日月动画", "sunrise"), ("关闭", "off")])
combo.resize(260, 36); combo.show()

def shoot():
    menu.popup(0, 0)
    combo.showPopup()
    QTimer.singleShot(250, grab)

def grab():
    menu.grab().save("artifacts/qa/r71/menu_new.png")
    w = combo.view().window()
    print("popup", w.width(), w.height(), flush=True)
    w.grab().save("artifacts/qa/r71/combo_new.png")
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(400, shoot)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
