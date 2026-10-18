import pathlib
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
old = '''        path = OUT / f"{scene}_{mode}.png"
        pixmap = window.grab()
        if scene in ("immersive", "immersive_lyrics"):'''
new = '''        path = OUT / f"{scene}_{mode}.png"
        pixmap = None if scene == "desktop_lyrics" else window.grab()
        if pixmap is None:
            pixmap = backdrop
        if scene in ("immersive", "immersive_lyrics"):'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
