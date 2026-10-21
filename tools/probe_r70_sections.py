import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data2")
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SettingsPage

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
page = SettingsPage()
page.resize(1100, 1200)
print("built", flush=True)
for index in range(9):
    print("section", index, flush=True)
    page._show_section(index)
    app.processEvents()
print("RESULT PASS", flush=True)
app.quit(); hush.shutdown()
