import pathlib
p = pathlib.Path("hushplayer/ui/main_window.py")
t = p.read_text(encoding="utf-8")
t = t.replace('        add("Ctrl+L", lambda: self.navigate("lyrics"))',
              '        add("Ctrl+L", lambda: self.navigate("lyrics"))\n        add("Ctrl+Shift+L", self.toggle_desktop_lyrics)\n        add("F11", self.open_immersive)')
p.write_text(t, encoding="utf-8")

p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
old = '''        elif scene in ("immersive", "immersive_lyrics"):'''
new = '''        elif scene == "desktop_lyrics":
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None:
                if ctx().player.current is not track:
                    ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                    app.processEvents()
                ctx().player.seek(4200)
                app.processEvents()
            from hushplayer.ui.desktop_lyrics import ensure_desktop_lyrics

            desktop = ensure_desktop_lyrics()
            if desktop is not None:
                desktop.apply_settings()
                desktop.show_lyrics()
                desktop.move(240, 160)
                for _ in range(3):
                    app.processEvents()
                backdrop = QPixmap(desktop.width(), desktop.height())
                backdrop.fill(QColor(26, 27, 32))
                painter = QPainter(backdrop)
                painter.drawPixmap(0, 0, desktop.grab())
                painter.end()
                pixmap = backdrop
        elif scene in ("immersive", "immersive_lyrics"):'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
