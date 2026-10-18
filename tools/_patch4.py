import pathlib
p = pathlib.Path("hushplayer/ui/widgets/playerbar.py")
s = p.read_text(encoding="utf-8")
s = s.replace("        self._wire()\n        self._refresh_states()\n", "        self._wire()\n")
p.write_text(s, encoding="utf-8")
print("ok")
