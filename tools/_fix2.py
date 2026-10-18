import pathlib
p = pathlib.Path("hushplayer/ui/pages/trackpage.py")
t = p.read_text(encoding="utf-8")
t = t.replace("        layout.setContentsMargins(0, 0, 0, 0)\n        layout.setSpacing(0)\n",
              "        layout.setContentsMargins(Metrics.page_pad, 14, Metrics.page_pad, 8)\n        layout.setSpacing(8)\n")
t = t.replace("from ...model.track import Track, format_duration\n",
              "from ...core.theme import Metrics\nfrom ...model.track import Track, format_duration\n")
p.write_text(t, encoding="utf-8")
print("ok")
