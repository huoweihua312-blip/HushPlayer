import pathlib
p = pathlib.Path("hushplayer/ui/desktop_lyrics.py")
t = p.read_text(encoding="utf-8")
t = t.replace('alpha_text(self._color, 0.72)', 'rgba(self._color, 0.72)')
t = t.replace('alpha_text(self._color, 0.55)', 'rgba(self._color, 0.55)')
t = t.replace('alpha_text(self._color, 0.5)', 'rgba(self._color, 0.5)')
t = t.replace('from ..core.theme import alpha_text, css_rgba, qcolor, theme', 'from ..core.theme import rgba, theme')
p.write_text(t, encoding="utf-8")
print("ok")
