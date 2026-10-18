import pathlib, re
files = {
 "hushplayer/ui/pages/trackpage.py": 34,
 "hushplayer/ui/pages/search.py": 44,
 "hushplayer/ui/pages/albums.py": 103,
 "hushplayer/ui/pages/artists.py": 97,
}
for name in files:
    p = pathlib.Path(name)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if "QVBoxLayout(self)" in line and "self._layout" not in line:
            lines[i] = line.replace("QVBoxLayout(self)", "self.content_layout")
            print("patched", name, i+1, lines[i].strip())
    p.write_text("".join(lines), encoding="utf-8")
