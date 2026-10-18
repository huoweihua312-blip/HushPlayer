import pathlib
p = pathlib.Path("hushplayer/audio/controller.py")
t = p.read_text(encoding="utf-8")
old = '''    @property
    def shuffle(self) -> bool:
        return self.queue.shuffle
'''
new = '''    @property
    def current(self):
        """当前播放曲目（队列中的 Track）。"""
        return self.queue.current

    @property
    def has_next(self) -> bool:
        return self.queue.current_row < self.queue.count - 1 or self.queue.repeat == "all"

    @property
    def shuffle(self) -> bool:
        return self.queue.shuffle
'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
