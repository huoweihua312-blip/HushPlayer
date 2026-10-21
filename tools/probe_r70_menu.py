import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data5")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QComboBox, QMenu
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.show(); app.processEvents()

def go():
    menu = QMenu(win)
    menu.addAction("新建歌单")
    menu.addAction("从文件导入歌单…")
    menu.addSeparator()
    act = QAction("检查订阅更新", menu)
    act.setEnabled(False)
    menu.addAction(act)
    menu.popup(QPoint(400, 300)); app.processEvents(); app.processEvents()
    menu.grab().save("artifacts/qa/r70/menu_styled.png")
    menu.close()

    combo = QComboBox(win)
    combo.addItems(["过渡动画（从标题栏按钮扩散）", "全屏日月动画", "关闭"])
    combo.resize(320, 36); combo.move(400, 500); combo.show()
    combo.showPopup(); app.processEvents(); app.processEvents()
    combo.view().window().grab().save("artifacts/qa/r70/combo_styled.png")
    combo.hidePopup()
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(900, go)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
