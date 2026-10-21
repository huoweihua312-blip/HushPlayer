import pathlib
p = pathlib.Path("hushplayer/core/theme.py")
t = p.read_text(encoding="utf-8")
start = t.index("    QMenu::item {{")
end = t.index("    QMenu::separator {{")
print(t[start:end])
