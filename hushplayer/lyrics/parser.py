"""歌词解析。

支持的格式（按优先级识别）：
* 标准 LRC（含一个时间行多个时间戳、``[offset:]`` 等元信息）
* 增强 LRC（``[00:12.34]<00:12.34>逐<00:12.60>字``）
* 网易云 klyric / yrc（``[0,1500](0,500,0)逐(500,500,0)字``）
* QQ 音乐 QRC（``[0,1500]逐(0,500)字(500,500)``）
* 纯文本歌词（无时间轴）

所有逐字/逐词时间都来自文件本身，绝不用字数估算替代。
"""

from __future__ import annotations

import re
from typing import Iterable

from ..model.lyrics import LyricDocument, LyricLine, Word

_META = re.compile(r"^\[(ti|ar|al|by|offset|length|re|ve|au|lj|language):\s*(.*?)\]\s*$", re.IGNORECASE)
_LRC_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_TAG_LOOSE = re.compile(r"\[(\d{1,3}):(\d{1,3})\]")
_WORD_TAG = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
_KLYRIC_LINE = re.compile(r"^\[(\d+),(\d+)\]")
_QRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_QRC_WORD = re.compile(r"([^\(\r\n]*?)\((\d+),(\d+)\)")
_KLYRIC_WORD = re.compile(r"([^\(\r\n]*?)\((\d+),(\d+),\d+\)")
_SEVERAL_SPACES = re.compile(r"[ \t]{2,}")

INSTRUMENTAL_HINTS = (
    "纯音乐",
    "此歌曲为没有填词的纯音乐",
    "instrumental",
    "no lyrics",
    "暂无歌词",
)


def _to_ms(minutes: str, seconds: str, fraction: str | None) -> int:
    total = int(minutes) * 60_000 + int(seconds) * 1_000
    if fraction:
        if len(fraction) == 1:
            total += int(fraction) * 100
        elif len(fraction) == 2:
            total += int(fraction) * 10
        else:
            total += int(fraction[:3])
    return total


def _looks_klyric(text: str) -> bool:
    return bool(re.search(r"^\[\d+,\d+\]\(", text, re.MULTILINE))


def _looks_qrc(text: str) -> bool:
    return bool(re.search(r"^\[\d+,\d+\][^\r\n]*\(\d+,\d+\)", text, re.MULTILINE))


def parse(
    text: str,
    *,
    source: str = "local",
    provider: str = "",
    duration_ms: int = 0,
    plain: bool = False,
    instrumental: bool = False,
) -> LyricDocument:
    """解析任意歌词文本，返回统一文档。

    ``plain`` 表示调用方已知文本没有时间轴（例如 LRCLIB 的 plainLyrics），
    此时跳过 LRC 解析直接按纯文本处理；``instrumental`` 表示来源明确声明
    该曲目为纯音乐。
    """
    if not text or not text.strip():
        if instrumental:
            return LyricDocument(
                lines=[LyricLine(0, 0, "纯音乐，请欣赏")],
                source=source,
                provider=provider,
                kind="instrumental",
            )
        return LyricDocument(source=source, provider=provider, kind="empty")

    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    if plain:
        document = plain_document(text, source=source)
    elif _looks_klyric(text):
        document = parse_klyric(text)
    elif _looks_qrc(text):
        document = parse_qrc(text)
    else:
        document = parse_lrc(text)
        if not document.lines:
            document = plain_document(text, source=source)

    document.source = source or document.source
    document.provider = provider or document.provider
    document.raw = text
    document.offset_ms = document.offset_ms or 0

    if document.lines and duration_ms:
        last = document.lines[-1]
        if last.end_ms > duration_ms + 3000:
            last.end_ms = max(last.start_ms + 1000, duration_ms)

    lower = text.lower()
    if instrumental:
        document.kind = "instrumental"
        document.synced = False
        if document.is_empty():
            document.lines = [LyricLine(0, 0, "纯音乐，请欣赏")]
    elif document.is_empty() or (
        len(document.lines) <= 2 and any(hint in lower for hint in INSTRUMENTAL_HINTS)
    ):
        document.kind = "instrumental" if any(hint in lower for hint in INSTRUMENTAL_HINTS) else "empty"
        if document.kind == "instrumental":
            document.synced = False
            document.lines = document.lines or [LyricLine(0, 0, "纯音乐，请欣赏")]
    elif document.synced:
        document.kind = "synced"
    elif document.lines:
        document.kind = "plain"

    document.has_word_timing = any(line.has_word_timing for line in document.lines)
    document.has_translation = any(line.translation.strip() for line in document.lines)
    return document


def parse_lrc(text: str) -> LyricDocument:
    document = LyricDocument(synced=False)
    pending: list[tuple[int, str, list[Word]]] = []
    meta: dict[str, str] = {}
    offset = 0

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        meta_match = _META.match(line)
        if meta_match:
            key = meta_match.group(1).lower()
            value = meta_match.group(2).strip()
            meta[key] = value
            if key == "offset":
                try:
                    offset = int(float(value))
                except ValueError:
                    pass
            continue
        tags = list(_LRC_TAG.finditer(line))
        if not tags:
            loose = list(_LRC_TAG_LOOSE.finditer(line))
            if not loose:
                continue
            tags = loose
            content_start = loose[-1].end()
            starts = [_to_ms(m.group(1), m.group(2), None) for m in loose]
        else:
            content_start = tags[-1].end()
            starts = [_to_ms(m.group(1), m.group(2), m.group(3)) for m in tags]
        content = line[content_start:]
        words = _split_enhanced(content)
        plain = _SEVERAL_SPACES.sub(" ", _WORD_TAG.sub("", content)).strip()
        for start in starts:
            pending.append((start, plain, [Word(w.text, w.start_ms, w.end_ms) for w in words]))

    pending.sort(key=lambda item: item[0])
    merged: list[tuple[int, str, list[Word]]] = []
    for item in pending:
        if merged and item[0] == merged[-1][0] and item[1] == merged[-1][1]:
            continue
        merged.append(item)

    lines: list[LyricLine] = []
    for index, (start, content, words) in enumerate(merged):
        end = merged[index + 1][0] if index + 1 < len(merged) else start + 5000
        if end <= start:
            end = start + 1200
        line = LyricLine(start_ms=start, end_ms=end, text=content, words=words)
        if words:
            _fill_word_ends(line)
        lines.append(line)

    document.lines = lines
    document.synced = bool(lines)
    document.offset_ms = offset
    document.title = meta.get("ti", "")
    document.artist = meta.get("ar", "")
    document.album = meta.get("al", "")
    document.by = meta.get("by", "")
    return document


def _split_enhanced(content: str) -> list[Word]:
    """把 ``<mm:ss.xx>词`` 拆成带相对时间的词列表（相对行首）。"""
    matches = list(_WORD_TAG.finditer(content))
    if not matches:
        return []
    if matches[0].start() > 0:
        prefix = content[: matches[0].start()]
        if prefix.strip():
            return []  # 形如 "[00:01.00]普通文本<00:02.00>后续"，按普通行处理
    words: list[Word] = []
    for index, match in enumerate(matches):
        start = _to_ms(match.group(1), match.group(2), match.group(3))
        end = (
            _to_ms(matches[index + 1].group(1), matches[index + 1].group(2), matches[index + 1].group(3))
            if index + 1 < len(matches)
            else start + 600
        )
        piece = content[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(content)]
        piece = piece.strip()
        if not piece:
            continue
        words.append(Word(text=piece, start_ms=start, end_ms=max(start + 60, end)))
    return words


def _copy_words(words: Iterable[Word], delta: int = 0) -> list[Word]:
    return [Word(word.text, word.start_ms + delta, word.end_ms + delta) for word in words]


def _fill_word_ends(line: LyricLine) -> None:
    for index, word in enumerate(line.words):
        if index + 1 < len(line.words):
            word.end_ms = max(word.start_ms + 40, min(word.end_ms, line.words[index + 1].start_ms))
        else:
            word.end_ms = max(word.start_ms + 120, line.end_ms)


_TAG_FIRST = re.compile(r"\((\d+),(\d+)(?:,\d+)?\)([^\(]*)")
_TEXT_FIRST = re.compile(r"([^\(]*)\((\d+),(\d+)(?:,\d+)?\)")
_LINE_RANGE = re.compile(r"^\[(\d+),(\d+)\](.*)$")


def _split_timed_words(remainder: str) -> list[tuple[int, int, str]]:
    """把逐字歌词拆成 [(相对偏移, 时长, 文本)]。

    兼容两种常见写法：
    * 标签在前：``(0,500,0)逐(500,500,0)字``
    * 文本在前：``逐(0,500)字(500,500)``
    """
    if not remainder:
        return []
    tag_first = bool(re.match(r"\s*\(\d+,\d+(?:,\d+)?\)", remainder))
    segments: list[tuple[int, int, str]] = []
    if tag_first:
        for match in _TAG_FIRST.finditer(remainder):
            text = match.group(3)
            if not text.strip():
                continue
            segments.append((int(match.group(1)), int(match.group(2)), text))
    else:
        for match in _TEXT_FIRST.finditer(remainder):
            text = match.group(1)
            if not text.strip():
                continue
            segments.append((int(match.group(2)), int(match.group(3)), text))
    return segments


def _document_from_timed_lines(
    text: str, *, provider: str = ""
) -> LyricDocument:
    lines: list[LyricLine] = []
    meta: dict[str, str] = {}
    offset = 0
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        meta_match = _META.match(line)
        if meta_match:
            key, value = meta_match.group(1).lower(), meta_match.group(2).strip()
            meta[key] = value
            if key == "offset":
                try:
                    offset = int(float(value))
                except ValueError:
                    offset = 0
            continue
        line_match = _LINE_RANGE.match(line)
        if not line_match:
            continue
        start = int(line_match.group(1))
        duration = int(line_match.group(2))
        remainder = line_match.group(3)
        segments = _split_timed_words(remainder)
        if segments:
            words: list[Word] = []
            parts: list[str] = []
            for word_offset, word_duration, piece in segments:
                word_start = start + word_offset
                words.append(Word(piece.strip(), word_start, word_start + max(40, word_duration)))
                parts.append(piece)
            content = "".join(parts).strip()
            end = start + max(400, duration or 1500)
            lines.append(LyricLine(start, end, content, words))
        else:
            plain = remainder.strip()
            if plain:
                lines.append(LyricLine(start, start + max(400, duration or 1500), plain))

    lines.sort(key=lambda item: item.start_ms)
    for index, line in enumerate(lines):
        if index + 1 < len(lines):
            next_start = lines[index + 1].start_ms
            if line.end_ms > next_start or line.end_ms <= line.start_ms:
                line.end_ms = max(line.start_ms + 200, next_start)
        elif line.end_ms <= line.start_ms:
            line.end_ms = line.start_ms + 5000
        if line.words:
            _fill_word_ends(line)

    document = LyricDocument(
        lines=lines,
        synced=bool(lines),
        offset_ms=offset,
        provider=provider,
        kind="synced" if lines else "empty",
        raw=text,
    )
    document.has_word_timing = any(line.has_word_timing for line in lines)
    document.title = meta.get("ti", "")
    document.artist = meta.get("ar", "")
    document.album = meta.get("al", "")
    return document


def parse_klyric(text: str) -> LyricDocument:
    """网易云 klyric / yrc：``[start,dur](wOffset,wDur,0)词``。"""
    return _document_from_timed_lines(text)


def parse_qrc(text: str) -> LyricDocument:
    """QQ 音乐 QRC：``[start,dur]词(offset,dur)``。"""
    return _document_from_timed_lines(text)

def attach_translation(document: LyricDocument, translation_text: str) -> LyricDocument:
    """把翻译歌词按时间对齐到主歌词行。"""
    if not translation_text or not translation_text.strip() or not document.lines:
        return document
    translated = parse_lrc(translation_text)
    if not translated.lines:
        # 没有时间轴的翻译文件：按行号对齐（常见于同目录 *.trans.lrc 手工文件）
        rows = [row.strip() for row in translation_text.split("\n") if row.strip()]
        if not rows:
            return document
        for line, row in zip(document.lines, rows):
            line.translation = row
        document.has_translation = any(line.translation.strip() for line in document.lines)
        return document

    if len(translated.lines) == len(document.lines):
        close = all(
            abs(a.start_ms - b.start_ms) < 600 for a, b in zip(document.lines, translated.lines)
        )
        if close:
            for line, twin in zip(document.lines, translated.lines):
                line.translation = twin.text
            document.has_translation = True
            return document

    index = 0
    for line in document.lines:
        best: LyricLine | None = None
        best_delta = 1200
        for candidate in translated.lines[index:]:
            delta = candidate.start_ms - line.start_ms
            if abs(delta) > best_delta:
                if delta > best_delta:
                    break
                continue
            best, best_delta = candidate, abs(delta)
        if best is not None:
            line.translation = best.text
            index = max(index, translated.lines.index(best))
    document.has_translation = any(line.translation.strip() for line in document.lines)
    return document


def attach_romanization(document: LyricDocument, text: str) -> LyricDocument:
    temp = parse_lrc(text)
    if not temp.lines:
        return document
    for line in document.lines:
        nearest = min(temp.lines, key=lambda item: abs(item.start_ms - line.start_ms))
        if abs(nearest.start_ms - line.start_ms) < 800:
            line.romanization = nearest.text
    return document


def plain_document(text: str, *, source: str = "local") -> LyricDocument:
    lines = [LyricLine(0, 0, line.strip()) for line in text.split("\n")]
    lines = [line for line in lines if line.text]
    for index, line in enumerate(lines):
        line.start_ms = index * 4000
        line.end_ms = (index + 1) * 4000
    return LyricDocument(lines=lines, synced=False, source=source, kind="plain" if lines else "empty", raw=text)
