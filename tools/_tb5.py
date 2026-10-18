import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.ui.widgets.frameless import FramelessWindow
from hushplayer.ui.widgets.titlebar import TitleBar, WindowButton

app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
w = FramelessWindow(); w.resize(900, 400)
bar = TitleBar(w); w.set_titlebar(bar)
w.show(); app.processEvents()
b = bar.close_button

def patched(event):
    print("paint called", b._icon_name, b.size())
    from PySide6.QtGui import QPainter
    from PySide6.QtCore import QRectF, Qt
    from hushplayer.core.theme import rgba
    from hushplayer.core import icons
    p = QPainter(b)
    print("painter active", p.isActive())
    r = QRectF(b.rect())
    target = QRectF(0,0,15,15); target.moveCenter(r.center())
    icons.draw(p, "close", target, rgba(theme().palette.text, 0.9))
    p.end()
b.paintEvent = patched
b.update()
app.processEvents()
b.grab().save("artifacts/shots/_closebtn2.png")
