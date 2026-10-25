"""在线歌曲「替换来源」：在其它音源里重新找同一首歌。

场景：某首歌来自酷我，但那个源解析失败/音质太差；用户在右键菜单里选择
「替换歌曲来源」，程序用歌名 + 歌手在**所有可播源**里重新搜索，列出候选项，
用户挑一条后只把这条记录的来源字段换掉（`tracks.id` 不变，所以收藏、歌单、
播放历史都不会丢）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QTimer

from ..core.logging_setup import get_logger, log_exception
from ..model.track import Track
from ..online import models as online_models
from ..online.matching import normalize_text, score_match

log = get_logger(__name__)

MAX_PER_SOURCE = 12
SEARCH_TIMEOUT_MS = 12_000
MIN_SCORE = 40


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


class SourceReplaceSearch:
    """一次「替换来源」搜索；结果通过 ``on_finished`` 回主线程。"""

    def __init__(
        self,
        client,
        track: Track,
        sources: Sequence[online_models.SourceInfo],
        on_finished: Callable[[list[SourceCandidate], list[str]], None],
        *,
        timeout_ms: int = SEARCH_TIMEOUT_MS,
    ) -> None:
        self._client = client
        self._track = track
        self._sources = [
            source
            for source in sources
            if source.enabled and source.searchable and source.id != track.source_id
        ]
        self._on_finished = on_finished
        self._timeout_ms = timeout_ms
        self._pending: set[str] = set()
        self._dispatching = False
        self._candidates: list[SourceCandidate] = []
        self._errors: list[str] = []
        self._finished = False

    # -- public ---------------------------------------------------------
    def start(self) -> None:
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
        QTimer.singleShot(self._timeout_ms + 2_000, self._on_deadline)
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
            if candidate is not None and candidate.score >= MIN_SCORE:
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

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._candidates.sort(key=lambda c: (-c.score, c.source_name, c.title))
        # 同一个远端 id 只保留一次
        seen: set[tuple[str, str]] = set()
        unique: list[SourceCandidate] = []
        for candidate in self._candidates:
            key = (candidate.source_id, candidate.remote_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        log.info(
            "替换来源：%s - %s，%d 个源返回 %d 条候选",
            self._track.title,
            self._track.artist,
            len(self._sources),
            len(unique),
        )
        try:
            self._on_finished(unique, self._errors)
        except Exception as exc:  # pragma: no cover - defensive
            log_exception("替换来源：结果回调失败", exc)
