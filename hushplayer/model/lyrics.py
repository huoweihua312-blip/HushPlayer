"""歌词数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    text: str
    start_ms: int
    end_ms: int

    @property
    def duration(self) -> int:
        return max(1, self.end_ms - self.start_ms)


@dataclass
class LyricLine:
    start_ms: int
    end_ms: int
    text: str
    words: list[Word] = field(default_factory=list)
    translation: str = ""
    romanization: str = ""
    # 逐行模式下用于平滑扫过高亮的相对进度（0..1）
    progress: float = 0.0

    @property
    def is_blank(self) -> bool:
        return not self.text.strip() and not self.translation.strip()

    @property
    def duration(self) -> int:
        return max(1, self.end_ms - self.start_ms)

    @property
    def has_word_timing(self) -> bool:
        return len(self.words) > 1 or (len(self.words) == 1 and self.words[0].text.strip() != self.text.strip())


@dataclass
class LyricDocument:
    lines: list[LyricLine] = field(default_factory=list)
    synced: bool = False
    source: str = ""  # local / online / manual / none
    provider: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    by: str = ""
    offset_ms: int = 0
    kind: str = "empty"  # synced | plain | instrumental | empty
    raw: str = ""
    has_word_timing: bool = False
    has_translation: bool = False

    # ------------------------------------------------------------------ 查询
    def index_at(self, position_ms: int) -> int:
        """返回给定播放位置对应的歌词行下标；早于第一行返回 -1。

        ``offset_ms`` 为正表示歌词整体延后出现（用户校准「歌词延迟」）。
        """
        if not self.lines:
            return -1
        target = position_ms - self.offset_ms
        low, high = 0, len(self.lines) - 1
        result = -1
        while low <= high:
            mid = (low + high) // 2
            if self.lines[mid].start_ms <= target:
                result = mid
                low = mid + 1
            else:
                high = mid - 1
        return result

    def line_at(self, position_ms: int) -> LyricLine | None:
        index = self.index_at(position_ms)
        return self.lines[index] if index >= 0 else None

    def line_progress(self, index: int, position_ms: int) -> float:
        if index < 0 or index >= len(self.lines):
            return 0.0
        line = self.lines[index]
        target = position_ms - self.offset_ms
        if target <= line.start_ms:
            return 0.0
        if target >= line.end_ms:
            return 1.0
        return (target - line.start_ms) / max(1, line.end_ms - line.start_ms)

    def word_progress(self, index: int, position_ms: int) -> tuple[int, float]:
        """返回 (当前词下标, 该词内部进度)。没有逐字数据时返回 (-1, 行进度)。"""
        if index < 0 or index >= len(self.lines):
            return (-1, 0.0)
        line = self.lines[index]
        if not line.words:
            return (-1, self.line_progress(index, position_ms))
        target = position_ms - self.offset_ms
        for word_index, word in enumerate(line.words):
            if target < word.end_ms:
                span = max(1, word.end_ms - word.start_ms)
                return (word_index, max(0.0, min(1.0, (target - word.start_ms) / span)))
        return (len(line.words) - 1, 1.0)

    def total_duration(self) -> int:
        return self.lines[-1].end_ms if self.lines else 0

    def is_empty(self) -> bool:
        return not self.lines or all(line.is_blank for line in self.lines)

    def plain_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


EMPTY_DOCUMENT = LyricDocument()
