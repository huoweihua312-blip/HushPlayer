import os, sys
sys.path.insert(0, ".")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.core.settings import settings
from hushplayer.ui.widgets.frameless import FramelessWindow
from hushplayer.ui.widgets.titlebar import TitleBar

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
app.setStyleSheet(theme().qss())
w = FramelessWindow(); w.resize(900, 400)
bar = TitleBar(w); w.set_titlebar(bar)
bar.set_title("测试标题")
w.show(); app.processEvents()
pix = bar.grab(); pix.save("artifacts/shots/_titlebar.png")
print("btn", bar.close_button.geometry(), bar.close_button.isVisible(), bar.close_button.size())
print("bar", bar.width(), bar.height())
