import pathlib

p = pathlib.Path("hushplayer/ui/visuals.py")
t = p.read_text(encoding="utf-8")
old = '''    radius = max(rect.width(), rect.height()) * coverage
    glow = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.78),
        radius * 0.9,
    )
    glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.34))
    glow.setColorAt(0.45, _with_alpha(mood.glow_a, 0.10))
    glow.setColorAt(1.0, _with_alpha(mood.glow_a, 0.0))
    painter.fillRect(rect, glow)

    glow2 = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.88, rect.top() + rect.height() * 0.12),
        radius * 0.75,
    )
    glow2.setColorAt(0.0, _with_alpha(mood.glow_b, 0.22))
    glow2.setColorAt(0.5, _with_alpha(mood.glow_b, 0.06))
    glow2.setColorAt(1.0, _with_alpha(mood.glow_b, 0.0))
    painter.fillRect(rect, glow2)'''
new = '''    radius = max(rect.width(), rect.height()) * coverage
    warm = mix(mood.glow_a, mood.base, 0.55)
    cool = mix(mood.glow_b, mood.base, 0.5)
    glow = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.16, rect.top() + rect.height() * 0.82),
        radius * 0.85,
    )
    glow.setColorAt(0.0, _with_alpha(warm, 0.26))
    glow.setColorAt(0.42, _with_alpha(warm, 0.07))
    glow.setColorAt(1.0, _with_alpha(warm, 0.0))
    painter.fillRect(rect, glow)

    glow2 = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.9, rect.top() + rect.height() * 0.08),
        radius * 0.7,
    )
    glow2.setColorAt(0.0, _with_alpha(cool, 0.16))
    glow2.setColorAt(0.5, _with_alpha(cool, 0.04))
    glow2.setColorAt(1.0, _with_alpha(cool, 0.0))
    painter.fillRect(rect, glow2)'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")

p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
old = '''            immersive = getattr(window, "_immersive", None)
            if immersive is not None and scene == "immersive_lyrics":
                immersive.set_mode("lyrics", animate=False)
                app.processEvents()'''
new = '''            immersive = getattr(window, "_immersive", None)
            if immersive is not None:
                immersive.set_mode("lyrics" if scene == "immersive_lyrics" else "cover", animate=False)
                app.processEvents()'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
