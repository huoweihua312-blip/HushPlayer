import pathlib
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
t = t.replace('        "search",\n        "queue",\n    ]', '        "search",\n        "queue",\n        "settings",\n        "album",\n        "artist",\n        "lyrics",\n    ]')
p.write_text(t, encoding="utf-8")
print("ok")
