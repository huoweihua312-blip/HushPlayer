import pathlib
p = pathlib.Path("hushplayer/app.py")
s = p.read_text(encoding="utf-8")
old = """        self.apply_theme()
        self.window = MainWindow()
        set_context(
            AppContext(
                library=self.library,
                player=self.player,
                lyrics=self.lyrics,
                cache=self.cache,
                covers=self.library.covers,
                client=self.client,
                proxy=self.proxy,
                keeper=self.keeper,
                settings=self.settings,
                window=self.window,
                desktop_lyrics=None,
                immersive=None,
            )
        )
        ctx().window = self.window
        self._configure_player()"""
new = """        self.apply_theme()
        self.window = MainWindow()
        context = ctx()
        if context is not None:
            context.window = self.window
        self._configure_player()"""
assert old in s
s = s.replace(old, new, 1)
s = s.replace('lambda: self.library.scan(folders) if not self.library.scanning else None,',
              'lambda: self.library.scan(folders) if not getattr(self.library, "scanning", False) else None,')
p.write_text(s, encoding="utf-8")
print("ok")
