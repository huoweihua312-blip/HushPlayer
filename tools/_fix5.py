import pathlib
p = pathlib.Path("hushplayer/ui/widgets/settings_widgets.py")
t = p.read_text(encoding="utf-8")
old = '''    def value(self) -> object:
        return self.currentData()
'''
new = '''    def value(self) -> object:
        return self.currentData()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = 14.0
        rect = QRectF(self.width() - 12 - size, (self.height() - size) / 2, size, size)
        from ...core import icons
        from ...core.theme import rgba, theme as _theme
        icons.draw(painter, "chevron_down", rect, rgba(_theme().palette.text_secondary, 0.9))
        painter.end()
'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
