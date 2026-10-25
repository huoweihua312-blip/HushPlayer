"""在线歌曲「替换来源」：在其它音源里重新找同一首歌。

场景：某首歌来自酷我，但那个源解析失败/音质太差；用户在右键菜单里选择
「替换歌曲来源」，程序用歌名 + 歌手在**所有可播源**里重新搜索，列出候选项，
用户挑一条后只把这条记录的来源字段换掉（`tracks.id` 不变，所以收藏、歌单、
播放历史都不会丢）。

这里负责三件事：
1. 搜得**快**：各音源并行发请求，先回来的先展示（``on_update``），并且把
   最近一次的结果缓存在内存里，重复打开不用再等；
2. 筛得**准**：除了匹配分，还硬性检查标题/歌手/时长，明显不是同一首的
   （翻唱、伴奏、30 秒试听片段、时长差太多的）不展示；
3. 结果可解释：每个候选带一个 ``note``（比如「时长 0:30，可能为试听片段」）。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from PySide6.QtCore import QTimer

from ..core.logging_setup import get_logger, log_exception
from ..model.track import Track
from ..online import models as online_models
from ..online.matching import normalize_text, score_match

log = get_logger(__name__)

MAX_PER_SOURCE = 12
SEARCH_TIMEOUT_MS = 8_000
MIN_SCORE = 55
CACHE_TTL_S = 600.0

# 这些词出现在候选标题里、而原曲标题没有 → 基本可以确定不是同一版本。
# 「翻唱」故意不在此列：用户明确说过要在候选里保留翻唱版本（不同歌手也保留）。
_VARIANT_WORDS = (
    "伴奏",
    "纯音乐",
    "消音",
    "铃声",
    "片段",
    "试听",
    "demo",
    "remix",
    "dj版",
    "弹鼓",
    "降调",
    "加速",
    "慢速",
    "女声版",
    "男声版",
)

_TOKEN_SPLIT = re.compile(r"[\s/,&、·．.\-]+")

# key -> (查询时间, 候选, 失败信息)
_CACHE: dict[str, tuple[float, list["SourceCandidate"], list[str]]] = {}


@dataclass
class SourceCandidate:
    """一条候选：来自哪个源、远端 id、展示字段、匹配分。"""

    source_id: str
    source_name: str
    remote_id: str
    title: str
    artist: str
    album: str
    duration_ms: int
    artwork_url: str
    score: int
    raw: dict
    note: str = ""

    @property
    def label(self) -> str:
        bits = [self.title or "(未知标题)"]
        if self.artist:
            bits.append(self.artist)
        return " — ".join(bits)

    @property
    def detail(self) -> str:
        bits = [self.source_name or self.source_id]
        if self.album:
            bits.append(self.album)
        if self.duration_ms:
            bits.append(f"{self.duration_ms // 60000}:{self.duration_ms // 1000 % 60:02d}")
        return " · ".join(bits)


def _search_key(track: Track) -> str:
    return f"{normalize_text(track.title)}|{normalize_text(track.artist)}"


def clear_cache() -> None:
    _CACHE.clear()


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_SPLIT.split(text) if token}


def _base_title(text: str) -> str:
    """去掉「(Live)」「（伴奏）」「- 现场版」这类括号/后缀，便于比较主标题。"""
    for marker in ("(", "（", "[", "【"):
        index = text.find(marker)
        if index > 0:
            text = text[:index]
    for marker in (" - ", " — "):
        index = text.find(marker)
        if index > 0:
            text = text[:index]
    return text.strip()


def _titles_compatible(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return False
    # 括号被 normalize_text 抹掉后「家书（翻唱）」会变成「家书 翻唱」；先去掉
    # 原曲没有的「翻唱/cover」标记，翻唱版本才能继续参与比较。
    for soft in ("翻唱版", "翻唱", "cover"):
        if soft in actual and soft not in expected:
            actual = actual.replace(soft, " ").strip()
    expected = " ".join(expected.split())
    actual = " ".join(actual.split())
    if not actual:
        return False
    if expected == actual:
        return True
    # 「晴天 (Live)」正规化后是「晴天 live」：去掉原曲里没有的纯英文/数字尾巴再比。
    pruned = " ".join(
        word for word in actual.split() if word in expected or not word.isascii()
    )
    if pruned and pruned == expected:
        return True
    if _base_title(expected) and _base_title(expected) == _base_title(actual):
        return True
    if expected in actual or actual in expected:
        shorter, longer = sorted((len(expected), len(actual)))
        return shorter / longer >= 0.6
    # 允许「(Live)」「- 现场版」这类尾巴差异：取前 8 个字比较
    return expected[:8] == actual[:8] and min(len(expected), len(actual)) >= 4


def _artists_compatible(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return True
    if expected in actual or actual in expected:
        return True
    return bool(_tokens(expected) & _tokens(actual))


def _duration_problem(expected_ms: int, actual_ms: int) -> str:
    """返回空串表示时长没问题，否则返回给用户看的提示。"""
    if not expected_ms or not actual_ms:
        return ""
    if actual_ms < 60_000 and expected_ms >= 90_000:
        return "只有不到 1 分钟，可能是试听片段"
    diff = abs(expected_ms - actual_ms)
    longest = max(expected_ms, actual_ms)
    if diff > max(35_000, longest * 0.35):
        return f"时长差 {diff // 1000} 秒，可能不是同一版本"
    return ""


def plausible(track: Track, candidate: SourceCandidate) -> bool:
    """明显不是同一首的候选直接丢掉（用户抱怨过搜索结果里全是无关项）。"""
    if candidate.score < MIN_SCORE:
        return False
    expected_title = normalize_text(track.title)
    actual_title = normalize_text(candidate.title)
    if not _titles_compatible(expected_title, actual_title):
        return False
    # 歌手不同不再直接丢弃：翻唱/合作版常常是用户真正想找的那一条。标题与
    # 时长已经足够筛掉无关结果，歌手差异只作为提示展示（见 `_note_for`）。
    for word in _VARIANT_WORDS:
        if word in actual_title and word not in expected_title:
            return False
    if _duration_problem(track.duration_ms, candidate.duration_ms):
        return False
    return True


def _note_for(track: Track, candidate: SourceCandidate) -> str:
    problem = _duration_problem(track.duration_ms, candidate.duration_ms)
    if problem:
        return problem
    notes: list[str] = []
    if track.artist and candidate.artist and not _artists_compatible(
        normalize_text(track.artist), normalize_text(candidate.artist)
    ):
        notes.append(f"歌手不同（{candidate.artist}），可能是翻唱")
    if track.duration_ms and candidate.duration_ms:
        diff = abs(track.duration_ms - candidate.duration_ms)
        if diff >= 15_000:
            notes.append(f"时长与原曲差 {diff // 1000} 秒，请确认版本")
    return "；".join(notes)


def _candidate_for(
    track: Track,
    item: dict,
    source: online_models.SourceInfo,
) -> SourceCandidate | None:
    remote_id = str(item.get("id") or item.get("songmid") or "").strip()
    title = str(item.get("title") or item.get("name") or "").strip()
    if not remote_id or not title:
        return None
    artist = str(item.get("artist") or "").strip()
    album = str(item.get("album") or "").strip()
    try:
        duration = int(item.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    # `track_from_item` 已经处理过秒/毫秒，这里复用它，避免两套换算。
    probe = online_models.track_from_item(item, source=source)
    score = score_match(track, probe)
    return SourceCandidate(
        source_id=source.id,
        source_name=source.label,
        remote_id=remote_id,
        title=probe.title,
        artist=probe.artist,
        album=probe.album,
        duration_ms=probe.duration_ms,
        artwork_url=probe.artwork_url,
        score=score,
        raw=dict(item),
    )


def _dedupe(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    ordered = sorted(candidates, key=lambda c: (-c.score, c.source_name, c.title))
    seen: set[tuple[str, str]] = set()
    unique: list[SourceCandidate] = []
    for candidate in ordered:
        key = (candidate.source_id, candidate.remote_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


class SourceReplaceSearch:
    """一次「替换来源」搜索；结果通过回调回主线程。"""

    def __init__(
        self,
        client,
        track: Track,
        sources: Sequence[online_models.SourceInfo],
        on_finished: Callable[[list[SourceCandidate], list[str]], None],
        *,
        timeout_ms: int = SEARCH_TIMEOUT_MS,
        on_update: Callable[[list[SourceCandidate], list[str], int, int], None] | None = None,
        use_cache: bool = True,
    ) -> None:
        self._client = client
        self._track = track
        self._sources = [
            source
            for source in sources
            if source.enabled and source.searchable and source.id != track.source_id
        ]
        self._on_finished = on_finished
        self._on_update = on_update
        self._timeout_ms = timeout_ms
        self._use_cache = use_cache
        self._pending: set[str] = set()
        self._dispatching = False
        self._candidates: list[SourceCandidate] = []
        self._errors: list[str] = []
        self._finished = False
        self._total = len(self._sources)

    # -- public ---------------------------------------------------------
    def start(self) -> None:
        key = _search_key(self._track)
        if self._use_cache:
            hit = _CACHE.get(key)
            if hit is not None and (time.monotonic() - hit[0]) <= CACHE_TTL_S:
                log.info("替换来源：命中缓存 %s（%d 条）", key, len(hit[1]))
                self._emit(hit[1], hit[2], finished=True)
                return
        if not self._sources:
            self._finish()
            return
        # The JSONL runtime may not be running yet (the user may never have
        # opened online search this session).  Without this the requests sit in
        # the client's outbound queue and the dialog waits forever.
        try:
            if not getattr(self._client, "running", False):
                starter = getattr(self._client, "ensure_started", None)
                if callable(starter):
                    starter()
        except Exception as exc:  # pragma: no cover - defensive
            log_exception("替换来源：启动在线运行时失败", exc)
        QTimer.singleShot(self._timeout_ms + 1_500, self._on_deadline)
        keyword = " ".join(part for part in (self._track.title, self._track.artist) if part)
        self._dispatching = True
        for source in self._sources:
            self._pending.add(source.id)
            try:
                self._client.search(
                    source.id,
                    keyword,
                    1,
                    lambda response, sid=source.id: self._on_response(sid, response),
                    timeout=self._timeout_ms,
                    kind="music",
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._pending.discard(source.id)
                self._errors.append(f"{source.label}：{exc}")
                log_exception("替换来源：发起搜索失败", exc)
        self._dispatching = False
        if not self._pending:
            self._finish()

    # -- internals ------------------------------------------------------
    def _on_response(self, source_id: str, response: dict | None) -> None:
        source = next((item for item in self._sources if item.id == source_id), None)
        if source is None:
            return
        self._pending.discard(source_id)
        try:
            self._collect(source_id, source, response)
        except Exception as exc:  # pragma: no cover - defensive
            self._errors.append(f"{source.label}：结果解析失败（{exc}）")
            log_exception("替换来源：解析搜索结果失败", exc)
        if not self._pending and not self._dispatching:
            self._finish()
        else:
            # 先回显已到达的结果，别等最慢的那个音源。
            self._emit(list(self._candidates), list(self._errors), finished=False)

    def _collect(self, source_id: str, source, response: dict | None) -> None:
        if not response or not response.get("ok"):
            error = (response or {}).get("error") or "未知错误"
            self._errors.append(f"{source.label}：{error}")
            return
        raw = response.get("data")
        if isinstance(raw, dict):
            items = raw.get("data") or raw.get("songs") or raw.get("list") or []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        if not isinstance(items, list):
            items = []
        for item in items[:MAX_PER_SOURCE]:
            if not isinstance(item, dict):
                continue
            try:
                candidate = _candidate_for(self._track, item, source)
            except Exception as exc:  # pragma: no cover - defensive
                log_exception("替换来源：候选解析失败", exc)
                continue
            if candidate is None:
                continue
            if not plausible(self._track, candidate):
                continue
            candidate.note = _note_for(self._track, candidate)
            self._candidates.append(candidate)

    def _on_deadline(self) -> None:
        if self._finished:
            return
        missing = sorted(self._pending)
        if missing:
            self._errors.append(f"{len(missing)} 个音源在 {self._timeout_ms // 1000} 秒内没有响应")
            log.warning("替换来源：超时未返回的音源 %s", ", ".join(missing))
        self._pending.clear()
        self._finish()

    def _emit(self, candidates: list[SourceCandidate], errors: list[str], *, finished: bool) -> None:
        unique = _dedupe(candidates)
        if finished:
            _CACHE[_search_key(self._track)] = (time.monotonic(), unique, list(errors))
        if finished and self._on_finished is not None:
            try:
                self._on_finished(unique, errors)
            except Exception as exc:  # pragma: no cover - defensive
                log_exception("替换来源：结果回调失败", exc)
            return
        if not finished and self._on_update is not None:
            try:
                self._on_update(unique, errors, len(self._sources) - len(self._pending), self._total)
            except Exception as exc:  # pragma: no cover - defensive
                log_exception("替换来源：增量回调失败", exc)

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        log.info(
            "替换来源：%s - %s，%d 个源返回 %d 条候选",
            self._track.title,
            self._track.artist,
            len(self._sources),
            len(self._candidates),
        )
        self._emit(list(self._candidates), list(self._errors), finished=True)
