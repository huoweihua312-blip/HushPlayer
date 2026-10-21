import pathlib
p = pathlib.Path("hushplayer/core/theme.py")
t = p.read_text(encoding="utf-8")
i = t.find("QMenu::item")
print(t[i-200:i+500])
