import pathlib

# --- provider localization ---
p = pathlib.Path("hushplayer/ui/pages/lyrics.py")
t = p.read_text(encoding="utf-8")
old = '''        provider = result.provider or result.status
        self.provider_label.setText(f"歌词来源 · {provider}" if result.status == STATUS_OK else "")'''
new = '''        provider = PROVIDER_LABELS.get(result.provider, result.provider or result.status)
        self.provider_label.setText(f"歌词来源 · {provider}" if result.status == STATUS_OK else "")'''
assert old in t
t = t.replace(old, new, 1)
t = t.replace('MAX_COVER = 288\n', '''MAX_COVER = 288

PROVIDER_LABELS = {
    "local": "本地文件",
    "embedded": "内嵌标签",
    "lrclib": "LRCLIB",
    "manual": "手动绑定",
    "cache": "本地缓存",
    "online": "在线音源",
}
''', 1)
p.write_text(t, encoding="utf-8")

# --- vertical padding ---
p = pathlib.Path("hushplayer/ui/widgets/lyrics_view.py")
t = p.read_text(encoding="utf-8")
old = '''    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        if alignment == self._alignment:
            return
        self._alignment = alignment
        self.update()
'''
new = '''    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        if alignment == self._alignment:
            return
        self._alignment = alignment
        self.update()

    def set_vertical_padding(self, top: float, bottom: float) -> None:
        top = max(12.0, float(top))
        bottom = max(12.0, float(bottom))
        if abs(top - self._top_pad) < 1 and abs(bottom - self._bottom_pad) < 1:
            return
        self._top_pad = top
        self._bottom_pad = bottom
        self._relayout()
'''
assert old in t
t = t.replace(old, new, 1)

old = '''    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scroll_to_index(self.body.active_index, animate=False)'''
new = '''    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        height = max(200, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * 0.42, height * 0.55)
        self._scroll_to_index(self.body.active_index, animate=False)'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
