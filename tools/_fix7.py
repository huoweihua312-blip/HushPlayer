import pathlib
p = pathlib.Path("hushplayer/ui/widgets/lyrics_view.py")
t = p.read_text(encoding="utf-8")
t = t.replace('''            active = index == self._index
            hovered = index == self._hover_row and not active
            text_color = self._active_color if active else self._inactive_color
            if hovered:
                text_color = rgba(text_color, 0.72) if text_color.startswith("#") else text_color
''', '''            active = index == self._index
            hovered = index == self._hover_row and not active
            if active:
                text_color = QColor(self._active_color)
            elif hovered:
                text_color = rgba(self._active_color, 0.62)
            else:
                text_color = QColor(self._inactive_color)
''')
t = t.replace('''        layout = QWidget(self)
        from PySide6.QtWidgets import QVBoxLayout

        outer = QVBoxLayout(self)''', '''        from PySide6.QtWidgets import QVBoxLayout

        outer = QVBoxLayout(self)''')
t = t.replace('from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea, QSizePolicy, QWidget',
              'from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget')
t = t.replace('from ...core.theme import Metrics, css_rgba, rgba, theme',
              'from ...core.theme import rgba, theme')
t = t.replace('''        self._follow = True
        self._follow_timer.stop()
        if document and document.lines:
            self.body.set_position(self.body._position)''', '''        self._follow = True
        self._follow_timer.stop()''')
p.write_text(t, encoding="utf-8")
print("ok")
