import pathlib
p = pathlib.Path("hushplayer/ui/immersive.py")
t = p.read_text(encoding="utf-8")

t = t.replace('''        self.lyrics.setFixedHeight(118)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.94)
        self.lyrics.set_show_translation(False)''', '''        self.lyrics.setFixedHeight(158)
        self.lyrics.set_empty_text("", "")
        self.lyrics.set_font_scale(0.80)
        self.lyrics.set_show_translation(False)''')

t = t.replace('''        radius = max(rect.width(), rect.height()) * 0.5
        gradient = QRadialGradientCompat(center, radius)
        gradient.setColorAt(0.0, _alpha(self._mood.accent, 0.30))
        gradient.setColorAt(0.42, _alpha(self._mood.glow_a, 0.20))
        gradient.setColorAt(0.78, _alpha(self._mood.glow_a, 0.05))''', '''        radius = max(rect.width(), rect.height()) * 0.55
        gradient = QRadialGradientCompat(center, radius)
        gradient.setColorAt(0.0, _alpha(self._mood.accent, 0.42))
        gradient.setColorAt(0.40, _alpha(self._mood.glow_a, 0.24))
        gradient.setColorAt(0.76, _alpha(self._mood.glow_a, 0.07))''')

t = t.replace('f"color:#ffffff;font-size:{max(18.0, 22 * theme().font_scale):.1f}pt;font-weight:700;"',
              'f"color:#ffffff;font-size:{max(20.0, 25 * theme().font_scale):.1f}pt;font-weight:700;"')

# controls: public sync
old = '''    # ------------------------------------------------------------------ 同步
    def _on_position(self, position: int) -> None:'''
new = '''    # ------------------------------------------------------------------ 同步
    def sync_from_player(self) -> None:
        player = ctx().player
        self._on_duration(player.duration)
        self._on_position(player.position)
        self._on_volume(player.volume)
        self._on_muted(player.muted)
        self._on_state(player.state)
        self._sync_modes()

    def _on_position(self, position: int) -> None:'''
assert old in t
t = t.replace(old, new, 1)

# open: push full state into controls
old = '''        self._on_state(ctx().player.state)
        position = ctx().player.position
        self._on_position(position)
        self._update_track_meta()'''
new = '''        self._on_state(ctx().player.state)
        position = ctx().player.position
        self._on_position(position)
        self.controls.sync_from_player()
        self._update_track_meta()'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
