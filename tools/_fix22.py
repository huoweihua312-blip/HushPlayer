import pathlib
p = pathlib.Path("hushplayer/ui/main_window.py")
t = p.read_text(encoding="utf-8")
old = '''        menu.addSeparator()
        quit_action = QAction("退出", self)'''
new = '''        menu.addSeparator()
        lyrics_action = QAction("桌面歌词", self)
        lyrics_action.triggered.connect(self.toggle_desktop_lyrics)
        menu.addAction(lyrics_action)
        immersive_action = QAction("沉浸模式", self)
        immersive_action.triggered.connect(self.open_immersive)
        menu.addAction(immersive_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)'''
assert old in t
t = t.replace(old, new, 1)

old = '''    def _on_tray_activated(self, reason) -> None:'''
new = '''    def toggle_desktop_lyrics(self) -> None:
        from .desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            self.toast("桌面歌词暂时不可用", "warning")
            return
        window.toggle()
        if window.isVisible():
            self.toast("桌面歌词已开启", "success")

    def _on_tray_activated(self, reason) -> None:'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
