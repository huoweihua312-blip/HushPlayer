import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data4")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from hushplayer.app import HushApp
from hushplayer.core.theme import theme
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.settings_widgets import ActionCard

app = QApplication(sys.argv); hush = HushApp(app); hush.start()

class Host(QWidget):
    def paintEvent(self, e):
        p = QPainter(self); p.fillRect(self.rect(), theme().palette.elevated); p.end()

host = Host(); host.resize(560, 330)
lay = QVBoxLayout(host); lay.setContentsMargins(16, 16, 16, 16); lay.setSpacing(8)
for icon, title, hint in (
    ("plus", "添加音源", "安装本地的 .js / .json 插件，只保存在用户数据目录"),
    ("cloud", "从链接添加", "粘贴插件地址，程序会下载并校验大小"),
    ("download", "导入订阅", "粘贴 MusicFree 订阅地址，一次导入其中的全部音源"),
):
    lay.addWidget(ActionCard(icon, title, hint, lambda: None))
host.show(); app.processEvents(); app.processEvents()
host.grab().save("artifacts/qa/r70/cards_host.png")
print("RESULT PASS", flush=True)
app.quit(); hush.shutdown()
