import pathlib
p = pathlib.Path("hushplayer/ui/main_window.py")
t = p.read_text(encoding="utf-8")
old = '''            window = getattr(self, "_immersive", None)
            if window is None:
                window = ImmersiveWindow()
                self._immersive = window
            window.show()
            window.raise_()
            window.activateWindow()'''
new = '''            window = getattr(self, "_immersive", None)
            if window is None:
                window = ImmersiveWindow()
                window.closed.connect(self._on_immersive_closed)
                self._immersive = window
            ctx().immersive = window
            window.open_immersive()'''
assert old in t
t = t.replace(old, new, 1)
old = '''    # ---------------------------------------------------------------- library'''
new = '''    def _on_immersive_closed(self) -> None:
        ctx().immersive = None

    # ---------------------------------------------------------------- library'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
