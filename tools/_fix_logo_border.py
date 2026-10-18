import pathlib
p = pathlib.Path("hushplayer/ui/widgets/sidebar.py")
t = p.read_text(encoding="utf-8")
old = """        if official is not None:
            painter.drawPixmap(QPointF(0, 0), official)
            painter.end()
            return"""
new = """        if official is not None:
            painter.drawPixmap(QPointF(0, 0), official)
            if not brand.has_official_logo():
                # The generated placeholder mark is charcoal on charcoal in the
                # dark sidebar; a hairline keeps it legible until the official
                # logo lands (see assets/brand/README.md).
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(rgba(theme().palette.text, 0.18), 1.0))
                painter.drawRoundedRect(rect, rect.width() * 0.30, rect.width() * 0.30)
            painter.end()
            return"""
assert old in t
t = t.replace(old, new)
if "QPen" not in t.split("class LogoMark")[0]:
    t = t.replace("from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap",
                  "from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap")
p.write_text(t, encoding="utf-8")
print("logo border added")
