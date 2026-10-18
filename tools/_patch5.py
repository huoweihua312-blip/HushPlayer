import pathlib
p = pathlib.Path("tools/shot_app.py")
s = p.read_text(encoding="utf-8")
s = s.replace('os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")', 'if os.environ.get("HUSH_OFFSCREEN") == "1":\n    os.environ["QT_QPA_PLATFORM"] = "offscreen"')
p.write_text(s, encoding="utf-8")
print("ok")
