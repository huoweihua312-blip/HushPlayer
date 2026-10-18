import pathlib
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
old = '            if immersive is not None and scene == "immersive_lyrics":\n                immersive.set_mode("lyrics", animate=False)\n                app.processEvents()'
new = '            if immersive is not None:\n                immersive.set_mode("lyrics" if scene == "immersive_lyrics" else "cover", animate=False)\n                app.processEvents()'
assert old in t, "still missing"
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
