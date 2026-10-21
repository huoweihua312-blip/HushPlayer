import os
import sys

sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r71/data4")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.25"

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.settings_widgets import SettingSlider

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
ctx().settings.set("appearance.theme", "light")


class Host(QWidget):
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.end()


host = Host()
host.resize(780, 120)
layout = QHBoxLayout(host)
layout.setContentsMargins(20, 20, 20, 20)
enabled = SettingSlider(150, 1200, 622.5, suffix=" ms", steps=120)
disabled = SettingSlider(150, 1200, 207.0, suffix=" ms", steps=120)
disabled.setEnabled(False)
layout.addWidget(enabled)
layout.addWidget(disabled)
host.show()
app.processEvents()
app.processEvents()
host.grab().save("artifacts/qa/r73/sliders_light.png")
print("RESULT PASS", flush=True)
app.quit()
hush.shutdown()
