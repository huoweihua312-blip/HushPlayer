import pathlib
p = pathlib.Path("hushplayer/audio/controller.py")
s = p.read_text(encoding="utf-8")
anchor = """    # ------------------------------------------------------------ transport"""
addition = """    def restore_current(self, position_ms: int = 0, *, autoplay: bool = False) -> None:
        \"\"\"Load the restored queue's current track at ``position_ms`` without starting.\"\"\"
        track = self.queue.current
        if track is None:
            return
        self._load(track, position=max(0, int(position_ms)), autoplay=autoplay)

    # ------------------------------------------------------------ transport"""
assert anchor in s
s = s.replace(anchor, addition, 1)
p.write_text(s, encoding="utf-8")

p = pathlib.Path("hushplayer/ui/main_window.py")
s = p.read_text(encoding="utf-8")
s = s.replace('add("Ctrl+Left", lambda: ctx().player.skip_by(-5000))', 'add("Ctrl+Left", lambda: ctx().player.skip_by(-5))')
s = s.replace('add("Ctrl+Right", lambda: ctx().player.skip_by(5000))', 'add("Ctrl+Right", lambda: ctx().player.skip_by(5))')
p.write_text(s, encoding="utf-8")
print("ok")
