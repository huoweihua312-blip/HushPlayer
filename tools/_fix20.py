import pathlib

p = pathlib.Path("hushplayer/ui/widgets/lyrics_view.py")
t = p.read_text(encoding="utf-8")
t = t.replace('''    def _ensure_padding(self) -> None:
        height = max(160, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * 0.42, height * 0.55)''',
'''    def set_padding_ratio(self, top: float, bottom: float) -> None:
        self._pad_top_ratio = max(0.0, min(1.0, top))
        self._pad_bottom_ratio = max(0.0, min(1.0, bottom))
        self._ensure_padding()

    def _ensure_padding(self) -> None:
        height = max(120, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * self._pad_top_ratio, height * self._pad_bottom_ratio)''')
t = t.replace('''        self._follow = True
        self._follow_timer''', '''        self._follow = True
        self._pad_top_ratio = 0.42
        self._pad_bottom_ratio = 0.55
        self._follow_timer''')
p.write_text(t, encoding="utf-8")

p = pathlib.Path("hushplayer/ui/immersive.py")
t = p.read_text(encoding="utf-8")
t = t.replace("STAGE_COVER_MAX = 372", "STAGE_COVER_MAX = 448")
t = t.replace('''        self.lyrics.setFixedHeight(158)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.80)
        self.lyrics.set_show_translation(False)''', '''        self.lyrics.setFixedHeight(178)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.74)
        self.lyrics.set_show_translation(False)
        self.lyrics.set_padding_ratio(0.16, 0.30)''')
p.write_text(t, encoding="utf-8")
print("ok")
