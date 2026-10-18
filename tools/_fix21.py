import pathlib
p = pathlib.Path("hushplayer/ui/pages/lyrics.py")
t = p.read_text(encoding="utf-8")
old = '''    def _toggle_desktop_lyrics(self) -> None:
        window = getattr(ctx(), "desktop_lyrics", None)
        if window is None:
            ctx().window.toast("桌面歌词暂时不可用", "warning")
            return
        window.toggle()'''
new = '''    def _toggle_desktop_lyrics(self) -> None:
        from ..desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            ctx().window.toast("桌面歌词暂时不可用", "warning")
            return
        window.toggle()'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")

p = pathlib.Path("hushplayer/ui/pages/settings.py")
t = p.read_text(encoding="utf-8")
old = '''        window = ctx().desktop_lyrics
        if window is None:
            try:
                from ..desktop_lyrics import DesktopLyricsWindow

                window = DesktopLyricsWindow()
                ctx().desktop_lyrics = window
            except Exception as exc:  # noqa: BLE001
                log_exception("创建桌面歌词窗口失败", exc)
                return'''
new = '''        from ..desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            return'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
