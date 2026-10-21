import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data2")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.settings_widgets import SettingRow, SettingsCard

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(880, 580); win.show(); app.processEvents()

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(0); app.processEvents()
    QTimer.singleShot(600, inspect)

def inspect():
    page = win._page("settings")
    for card in page.findChildren(SettingsCard):
        print("CARD min", card.minimumSizeHint().width(), "w", card.width(), flush=True)
        for row in card.findChildren(SettingRow):
            print("  ROW min", row.minimumSizeHint().width(), "w", row.width(),
                  "text", row.title_label.minimumSizeHint().width(),
                  "ctrl", row.control.minimumSizeHint().width() if row.control else None, flush=True)
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(600, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
