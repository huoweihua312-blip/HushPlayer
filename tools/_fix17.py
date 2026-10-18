import pathlib

# visuals: darker base, subtler glow
p = pathlib.Path("hushplayer/ui/visuals.py")
t = p.read_text(encoding="utf-8")
t = t.replace('base = mix(primary, QColor("#0b0b0e"), 0.72)', 'base = mix(primary, QColor("#0a0a0d"), 0.87)')
t = t.replace('glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.60))', 'glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.34))')
t = t.replace('glow.setColorAt(0.45, _with_alpha(mood.glow_a, 0.16))', 'glow.setColorAt(0.45, _with_alpha(mood.glow_a, 0.10))')
t = t.replace('glow2.setColorAt(0.0, _with_alpha(mood.glow_b, 0.34))', 'glow2.setColorAt(0.0, _with_alpha(mood.glow_b, 0.22))')
t = t.replace('glow2.setColorAt(0.5, _with_alpha(mood.glow_b, 0.10))', 'glow2.setColorAt(0.5, _with_alpha(mood.glow_b, 0.06))')
t = t.replace('vignette.setColorAt(1.0, QColor(0, 0, 0, 96))', 'vignette.setColorAt(1.0, QColor(0, 0, 0, 140))')
p.write_text(t, encoding="utf-8")

# lyrics view: padding kept in sync with real viewport + bigger base font
p = pathlib.Path("hushplayer/ui/widgets/lyrics_view.py")
t = p.read_text(encoding="utf-8")
t = t.replace('        base = 17.0 * self._font_scale', '        base = 18.0 * self._font_scale')
old = '''    def _scroll_to_index(self, index: int, *, animate: bool) -> None:
        if index < 0:
            return'''
new = '''    def _ensure_padding(self) -> None:
        height = max(160, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * 0.42, height * 0.55)

    def _scroll_to_index(self, index: int, *, animate: bool) -> None:
        if index < 0:
            return
        self._ensure_padding()'''
assert old in t
t = t.replace(old, new, 1)
t = t.replace('''    def set_document(self, document: LyricDocument | None) -> None:
        self.body.set_document(document)''', '''    def set_document(self, document: LyricDocument | None) -> None:
        self._ensure_padding()
        self.body.set_document(document)''')
p.write_text(t, encoding="utf-8")

# immersive: bigger lyrics in all-screen mode, larger header
p = pathlib.Path("hushplayer/ui/immersive.py")
t = p.read_text(encoding="utf-8")
t = t.replace('        self.lyrics = LyricsView(self, centered=True)\n        self.lyrics.set_font_scale(1.14)',
              '        self.lyrics = LyricsView(self, centered=True)\n        self.lyrics.set_font_scale(1.55)')
t = t.replace('self.cover = HeroCover(58, radius=8, parent=self)', 'self.cover = HeroCover(64, radius=10, parent=self)')
t = t.replace('f"color:#ffffff;font-size:{11.6 * theme().font_scale:.1f}pt;font-weight:600;"',
              'f"color:#ffffff;font-size:{13.0 * theme().font_scale:.1f}pt;font-weight:600;"')
t = t.replace('layout.setContentsMargins(40, 0, 40, 0)\n        layout.setSpacing(0)\n\n        header', 'layout.setContentsMargins(54, 4, 54, 0)\n        layout.setSpacing(0)\n\n        header')
p.write_text(t, encoding="utf-8")
print("ok")
