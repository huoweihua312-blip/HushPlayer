import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data3")
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.settings_widgets import ActionCard

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
card = ActionCard("plus", "添加音源", "安装本地插件", lambda: None)
card.resize(600, 58)
card.show()
app.processEvents()
print("shown", flush=True)
pix = card.grab()
print("grabbed", pix.size(), flush=True)
pix.save("artifacts/qa/r70/actioncard.png")
print("RESULT PASS", flush=True)
app.quit(); hush.shutdown()
