import pathlib
p = pathlib.Path("hushplayer/ui/pages/lyrics.py")
t = p.read_text(encoding="utf-8")
t = t.replace('''            f"color:{rgba(palette.text, 0.72).name() if False else palette.text_secondary};"''',
              '''            f"color:{palette.text_secondary};"''')
t = t.replace('''            f"color:{rgba(palette.text, 0.45).name() if False else palette.text_tertiary};"''',
              '''            f"color:{palette.text_tertiary};"''')
t = t.replace('from ...core.theme import Metrics, rgba, theme', 'from ...core.theme import rgba, theme')
p.write_text(t, encoding="utf-8")
print("ok")
