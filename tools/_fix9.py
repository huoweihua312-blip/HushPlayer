import pathlib
p = pathlib.Path("hushplayer/lyrics/service.py")
t = p.read_text(encoding="utf-8")
anchor = '''    return ""


def embedded_lyrics(path: str) -> str:'''
new = '''    return ""


def find_translation_sidecar(path: str) -> str:
    """查找与音频同名的翻译歌词文件（如 ``歌名.trans.lrc`` / ``歌名.zh.lrc``）。"""
    if not path:
        return ""
    stem = os.path.splitext(path)[0]
    suffixes = (".trans.lrc", ".translation.lrc", ".zh.lrc", ".trans.txt", ".translation.txt")
    for suffix in suffixes:
        candidate = stem + suffix
        if os.path.isfile(candidate):
            return candidate
    folder = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0]
    for name in ("Lyrics", "lyrics", "歌词"):
        candidate_dir = os.path.join(folder, name)
        if not os.path.isdir(candidate_dir):
            continue
        for suffix in suffixes:
            candidate = os.path.join(candidate_dir, base + suffix)
            if os.path.isfile(candidate):
                return candidate
    return ""


def embedded_lyrics(path: str) -> str:'''
assert anchor in t
t = t.replace(anchor, new, 1)
old = '''                if text.strip():
                    result = self._finish(track, text, provider="local", source="local")
                    self.resolved.emit(result)
                    return result'''
new = '''                if text.strip():
                    result = self._finish(track, text, provider="local", source="local")
                    translation_path = find_translation_sidecar(track.path)
                    if translation_path and result.document is not None and result.document.lines:
                        translated = _read_text(translation_path)
                        if translated.strip():
                            lyric_parser.attach_translation(result.document, translated)
                            self._cache[track.id] = result
                    self.resolved.emit(result)
                    return result'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
