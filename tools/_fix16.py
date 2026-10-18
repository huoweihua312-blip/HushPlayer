import pathlib

p = pathlib.Path("hushplayer/ui/immersive.py")
t = p.read_text(encoding="utf-8")

# 1) center stage content
old = '''        layout.setContentsMargins(40, 6, 40, 0)
        layout.setSpacing(0)

        self.cover = _GlowCover(STAGE_COVER_MAX, self)'''
new = '''        layout.setContentsMargins(40, 6, 40, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        self.cover = _GlowCover(STAGE_COVER_MAX, self)'''
assert old in t
t = t.replace(old, new, 1)
old = '''        layout.addWidget(self.lyrics)
        layout.addStretch(1)
        self.refresh_theme()'''
new = '''        layout.addWidget(self.lyrics)
        layout.addStretch(1)
        self.refresh_theme()'''
# preview: no translation, a bit taller
t = t.replace('''        self.lyrics.setFixedHeight(128)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.92)
        self.lyrics.set_show_translation(True)''', '''        self.lyrics.setFixedHeight(118)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.94)
        self.lyrics.set_show_translation(False)''')

# 2) circular glow that fades before the widget edge
old = '''        rect = QRectF(self.rect())
        center = rect.center()
        radius = self._size * 1.05
        gradient = QRadialGradientCompat(center, radius)
        gradient.setColorAt(0.0, _alpha(self._mood.accent, 0.34))
        gradient.setColorAt(0.55, _alpha(self._mood.glow_a, 0.20))
        gradient.setColorAt(1.0, _alpha(self._mood.glow_a, 0.0))
        painter.fillRect(rect, gradient)
        painter.end()'''
new = '''        rect = QRectF(self.rect())
        center = rect.center()
        radius = max(rect.width(), rect.height()) * 0.5
        gradient = QRadialGradientCompat(center, radius)
        gradient.setColorAt(0.0, _alpha(self._mood.accent, 0.30))
        gradient.setColorAt(0.42, _alpha(self._mood.glow_a, 0.20))
        gradient.setColorAt(0.78, _alpha(self._mood.glow_a, 0.05))
        gradient.setColorAt(1.0, _alpha(self._mood.glow_a, 0.0))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        painter.end()'''
assert old in t
t = t.replace(old, new, 1)

# 3) stronger ambient
t = t.replace('glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.52))', 'glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.60))')
p.write_text(t, encoding="utf-8")

p = pathlib.Path("hushplayer/ui/visuals.py")
t = p.read_text(encoding="utf-8")
t = t.replace('base = mix(primary, QColor("#0b0b0e"), 0.82)', 'base = mix(primary, QColor("#0b0b0e"), 0.72)')
p.write_text(t, encoding="utf-8")

# 4) shot scene for lyrics mode
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
t = t.replace('''        "queue",
        "settings",''', '''        "queue",
        "settings",''')
t = t.replace('''        elif scene == "immersive":''', '''        elif scene in ("immersive", "immersive_lyrics"):''')
t = t.replace('''            window.open_immersive()
            app.processEvents()''', '''            window.open_immersive()
            app.processEvents()
            immersive = getattr(window, "_immersive", None)
            if immersive is not None and scene == "immersive_lyrics":
                immersive.set_mode("lyrics", animate=False)
                app.processEvents()''', 1)
t = t.replace('''        if scene == "immersive":''', '''        if scene in ("immersive", "immersive_lyrics"):''')
p.write_text(t, encoding="utf-8")
print("ok")
