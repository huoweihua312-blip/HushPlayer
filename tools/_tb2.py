import os, sys
sys.path.insert(0, ".")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app, theme, rgba
from hushplayer.core import icons
from hushplayer.ui.widgets.frameless import FramelessWindow
from hushplayer.ui.widgets.titlebar import TitleBar

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
w = FramelessWindow(); w.resize(900, 400)
bar = TitleBar(w); w.set_titlebar(bar)
w.show(); app.processEvents()
b = bar.close_button
print("icon_name", b._icon_name, "color", rgba(theme().palette.text, 0.55).name(), b.isVisible(), b.size())
pm = icons.pixmap("close", rgba(theme().palette.text, 0.55), 15)
print("pixmap", pm.size(), pm.isNull())
pm.save("artifacts/shots/_icon.png")
b.grab().save("artifacts/shots/_closebtn.png")
