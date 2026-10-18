import pathlib
p = pathlib.Path("hushplayer/ui/desktop_lyrics.py")
t = p.read_text(encoding="utf-8")
t = t.replace('''        self._settings.changed.connect(self._on_setting_changed)
        current = player.current''', '''        self._settings.changed.connect(self._on_setting_changed)
        self._position = player.position
        current = player.current''')
t = t.replace('''    def show_lyrics(self) -> None:
        self.apply_settings()''', '''    def show_lyrics(self) -> None:
        self.apply_settings()
        self._position = ctx().player.position''')
p.write_text(t, encoding="utf-8")
print("ok")
