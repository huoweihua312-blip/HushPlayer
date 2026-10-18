import pathlib
p = pathlib.Path("hushplayer/ui/pages/lyrics.py")
t = p.read_text(encoding="utf-8")
t = t.replace("from ...core.theme import rgba, theme", "from ...core.theme import Metrics, rgba, theme")
t = t.replace('''        root = QHBoxLayout()''', '''        self.content_layout.setContentsMargins(Metrics.page_pad, 16, Metrics.page_pad - 6, 8)
        root = QHBoxLayout()''', 1)
p.write_text(t, encoding="utf-8")
print("ok")
