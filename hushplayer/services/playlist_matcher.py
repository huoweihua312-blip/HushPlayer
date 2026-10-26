"""Cross-source playlist matching (import step 3 of 3).

Local library first, then the enabled online sources, scored with the *same*
matcher the player uses for cross-source playback fallback
(:mod:`hushplayer.online.matching`). High-confidence hits are matched
automatically, ambiguous ones are surfaced for review, and nothing is silently
dropped: every source entry ends up in one of five states.

Network work runs through Qt's event loop (the online client is already async),
so the UI thread only does scoring; concurrency is capped and every stage is
cancellable.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.logging_setup import get_logger, log_exception

log = get_logger(__name__)

from ..model.track import Track
from ..online.matching import (
    AUTO_MARGIN,
    AUTO_MIN_SCORE,
    CANDIDATE_MIN_SCORE,
    MatchCandidate,
    normalize_text,
    rank_candidates,
    score_match,
)
from ..online.models import build_sources, track_from_item
from .playlist_import import PlaylistEntry

__all__ = [
    "STATUS",
    "MatchRow",
    "PlaylistMatcher",
    "ImportOutcome",
    "apply_import",
    "find_playlist",
]

STATUS = {
    "local": "本地",
    "online": "在线已匹配",
    "unverified": "在线未验证",
    "review": "待确认",
    "unmatched": "未匹配",
    "skipped": "已跳过",
}

_MAX_ROWS_IN_FLIGHT = 2
_MAX_SOURCES = 6
_MAX_CANDIDATES = 18
_SEARCH_TIMEOUT_MS = 8_000
_VERIFY_TIMEOUT_MS = 8_000
MATCH_STRENGTHS = {
    "strict": (80, 15),
    "balanced": (75, 8),
    "loose": (60, 0),
}
STRENGTH_LABELS = {"strict": "严格", "balanced": "平衡", "loose": "宽松"}

_VERSION_TOKENS = (
    "live",
    "现场",
    "演唱会",
    "remix",
    "混音",
    "dj",
    "伴奏",
    "instrumental",
    "纯音乐",
    "cover",
    "翻唱",
    "acoustic",
    "demo",
    "karaoke",
    "ktv",
)


def _version_tokens(text: str) -> set[str]:
    lowered = normalize_text(text)
    return {token for token in _VERSION_TOKENS if token in lowered}


def _adjusted_score(expected: Track, candidate: Track) -> int:
    """Score like the player, but punish version mismatches (Live vs studio)."""
    score = score_match(expected, candidate)
    if score <= 0:
        return 0
    wanted = _version_tokens(f"{expected.title} {expected.album}")
    found = _version_tokens(f"{candidate.title} {candidate.album}")
    score += 6 * len(wanted & found)
    score -= 30 * len(found - wanted)
    return max(0, score)


def _dedupe_candidates(items: list[MatchCandidate]) -> list[MatchCandidate]:
    """Drop duplicates of the same remote song, keeping the best score."""
    seen: set[tuple[str, str]] = set()
    result: list[MatchCandidate] = []
    for item in items:
        track = item.track
        key = (track.source_id, track.remote_id or track.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _wanted_track(entry: PlaylistEntry) -> Track:
    return Track(
        id="import:wanted",
        title=entry.title,
        artist=entry.artist,
        album=entry.album,
        duration_ms=entry.duration_ms,
        kind="local",
    )


@dataclass
class MatchRow:
    entry: PlaylistEntry
    status: str = "unmatched"
    track: Track | None = None
    score: int = 0
    candidates: list[MatchCandidate] = field(default_factory=list)
    note: str = ""
    verified: bool | None = None
    skipped: bool = False

    @property
    def display_title(self) -> str:
        return self.entry.title or self.entry.path

    @property
    def display_artist(self) -> str:
        return self.entry.artist

    @property
    def status_label(self) -> str:
        return STATUS.get(self.status, self.status)

    @property
    def source_name(self) -> str:
        if self.track is None:
            return ""
        return self.track.source_name or ("本地" if self.track.kind == "local" else "")


@dataclass
class ImportOutcome:
    playlist_id: int = 0
    playlist_name: str = ""
    added: int = 0
    duplicates: int = 0
    skipped: int = 0
    unmatched: int = 0
    pending: int = 0
    failed: int = 0
    mode: str = "new"


def _bind_import_choices(library, rows: Iterable[MatchRow]) -> None:
    """把本次导入选中的在线歌曲写成一等公民绑定（auto/pending）。

    写的是 ``tracks`` + ``track_source_binding_state``，不是 JSON 缓存；
    ``import_choice`` 会拒绝覆盖 manual 和已经验证过的 auto 绑定，重复导入
    因此是安全的。新歌保持 pending，等第一次真正播出声后再验证。
    """

    bindings = getattr(library, "source_bindings", None)
    if bindings is None:
        return
    from .binding import BindingChoice

    for row in rows:
        track = row.track
        if track is None or row.skipped or track.kind != "online":
            continue
        if not (track.source_id and track.remote_id):
            # 不要静默跳过：插件返回的 id/songmid 提取不完整时必须能在日志里
            # 定位到是哪一首、缺了哪个字段，否则这首歌永远不会被绑定。
            log.warning(
                "导入绑定跳过《%s》：歌曲 ID 不完整（source_id=%r, remote_id=%r, raw keys=%s）",
                track.display_title,
                track.source_id,
                track.remote_id,
                sorted(track.raw)[:8] if isinstance(track.raw, dict) else type(track.raw),
            )
            continue
        if library.tracks.get(track.id) is None:
            log.warning("导入绑定跳过《%s》：曲目不在数据库里", track.display_title)
            continue
        entry = row.entry
        origin = (entry.origin_platform, entry.origin_remote_id) if entry.origin_platform else None
        try:
            bindings.import_choice(
                track.id, BindingChoice.from_track(track), origin=origin
            )
        except Exception:  # noqa: BLE001 - 单曲绑定失败不应中断整个导入
            log.warning("write binding failed for %s", track.id, exc_info=True)


def find_playlist(library, name: str):
    wanted = (name or "").strip().casefold()
    for playlist in library.playlists_all():
        if playlist.system:
            continue
        if playlist.name.strip().casefold() == wanted:
            return playlist
    return None


def _query_variants(entry: PlaylistEntry) -> list[str]:
    """Alternative queries, cheapest first, for rows the first pass missed."""
    title = (entry.title or "").strip()
    artist = (entry.artist or "").strip()
    cleaned = re.sub(r"[\(\[（【].*?[\)\]）】]", " ", title)
    cleaned = re.sub(r"\b(feat|ft|featuring)\b.*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    variants: list[str] = []
    if title and artist:
        variants.append(f"{title} {artist}")
    if title:
        variants.append(title)
    if cleaned and cleaned != title:
        variants.append(f"{cleaned} {artist}".strip())
        variants.append(cleaned)
    if artist and entry.album:
        variants.append(f"{artist} {entry.album}")
    return list(dict.fromkeys(variants))


def apply_import(
    library,
    name: str,
    rows: list[MatchRow],
    *,
    mode: str = "new",
    playlist_id: int | None = None,
) -> ImportOutcome:
    """Persist confirmed rows, preserving order and never duplicating a track.

    ``mode``: ``new`` (always create), ``merge`` (append into an existing one) or
    ``replace`` (clear the existing playlist first).
    """
    name = (name or "").strip() or "导入的歌单"
    outcome = ImportOutcome(playlist_name=name, mode=mode)

    existing = library.playlist(playlist_id) if playlist_id else find_playlist(library, name)
    if mode == "new" or existing is None:
        outcome.playlist_id = library.create_playlist(name)
    else:
        outcome.playlist_id = existing.id
        if mode == "replace":
            ids = [track.id for track in library.playlist_tracks(existing.id)]
            if ids:
                library.remove_from_playlist(existing.id, ids)

    ordered: list[Track] = []
    seen: set[str] = set()
    for row in rows:
        if row.skipped or row.status == "skipped":
            outcome.skipped += 1
            continue
        if row.status in ("review", "pending"):
            outcome.pending += 1
            continue
        if row.status == "unmatched" or row.track is None:
            outcome.unmatched += 1
            continue
        track = row.track
        if track.id in seen:
            outcome.duplicates += 1
            continue
        seen.add(track.id)
        ordered.append(track)

    unique: list[Track] = []
    for track in ordered:
        try:
            if track.kind == "online" and not track.album_id:
                library._ensure_online_album(track)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the import
            log_exception(f"导入歌单：补全在线专辑失败（{track.display_title}）", exc)
        if track.id not in {item.id for item in unique}:
            unique.append(track)

    if unique:
        try:
            library.add_to_playlist(outcome.playlist_id, unique)
        except Exception as exc:  # noqa: BLE001
            log_exception("导入歌单：写入播放列表失败", exc)
            outcome.failed = len(unique)
            unique = []
    outcome.added = len(unique)
    _bind_import_choices(library, rows)
    log.info(
        "导入歌单「%s」：新增 %s，重复 %s，跳过 %s，未匹配 %s，待确认 %s，失败 %s",
        name,
        outcome.added,
        outcome.duplicates,
        outcome.skipped,
        outcome.unmatched,
        outcome.pending,
        outcome.failed,
    )
    return outcome


class PlaylistMatcher(QObject):
    """Async matcher: local pass first, then capped online searches."""

    row_changed = Signal(int)
    progress = Signal(int, int)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, client, library, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._library = library
        self.rows: list[MatchRow] = []
        self._cache: dict[tuple[str, str], MatchRow] = {}
        self._queue: list[int] = []
        self._in_flight: set[int] = set()
        self._index = 0
        self._variant_pass = False
        self._variant_queue = []
        self._cancelled = False
        self._started = False
        self._online = True
        self._sources: list = []
        self._verify = True
        self._strength = "balanced"
        self._variant_pass = False
        self._variant_queue: list[int] = []

    # ------------------------------------------------------------------ control
    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def done(self) -> int:
        return sum(1 for row in self.rows if row.status != "pending")

    def counts(self) -> dict[str, int]:
        result = {"local": 0, "online": 0, "unverified": 0, "review": 0, "unmatched": 0, "skipped": 0}
        for row in self.rows:
            if row.status in result:
                result[row.status] += 1
        return result

    def _thresholds(self) -> tuple[int, int]:
        return MATCH_STRENGTHS.get(self._strength, MATCH_STRENGTHS["balanced"])

    def start(
        self,
        entries: list[PlaylistEntry],
        *,
        online: bool = True,
        verify: bool = True,
        strength: str = "balanced",
        auto_adopt: bool = True,
    ) -> None:
        # Mutate in place: the dialog's table model keeps this list by reference.
        self.rows[:] = [MatchRow(entry=entry, status="pending") for entry in entries]
        self._queue = []
        self._in_flight.clear()
        self._cache.clear()
        self._index = 0
        self._cancelled = False
        self._started = True
        self._online = online
        self._verify = verify
        self._strength = strength if strength in MATCH_STRENGTHS else "balanced"
        self._auto = bool(auto_adopt)
        self._sources = self._pick_sources()
        self.progress.emit(0, len(self.rows))
        QTimer.singleShot(0, self._local_pass)

    def cancel(self) -> None:
        self._cancelled = True
        self._queue.clear()
        self._in_flight.clear()

    # ------------------------------------------------------------------ local
    def _local_pass(self) -> None:
        if self._cancelled:
            return
        total = len(self.rows)
        for index, row in enumerate(self.rows):
            if index < self._index:
                continue
            self._index = index + 1
            self._match_local(row)
            if index % 25 == 0:
                self.progress.emit(self.done, total)
                QTimer.singleShot(0, lambda i=index + 1: self._continue_local(i))
                return
        self._index = total
        self.progress.emit(self.done, total)
        self._start_online()

    def _continue_local(self, start: int) -> None:
        if self._cancelled:
            return
        total = len(self.rows)
        for index in range(start, total):
            row = self.rows[index]
            self._index = index + 1
            self._match_local(row)
            if index % 25 == 0:
                self.progress.emit(self.done, total)
                QTimer.singleShot(0, lambda i=index + 1: self._continue_local(i))
                return
        self._index = total
        self.progress.emit(self.done, total)
        self._start_online()

    def _match_local(self, row: MatchRow) -> None:
        entry = row.entry
        if not entry.title:
            row.status = "unmatched"
            row.note = "没有曲名"
            self.row_changed.emit(self.rows.index(row))
            return
        try:
            candidates = [
                track
                for track in self._library.tracks.search_local(entry.title, limit=30)
                if track.kind == "local"
            ]
        except Exception:  # noqa: BLE001 - a broken library must not abort an import
            candidates = []
        wanted = _wanted_track(entry)
        scored = sorted(
            ((candidate, _adjusted_score(wanted, candidate)) for candidate in candidates),
            key=lambda item: item[1],
            reverse=True,
        )
        auto_min, _margin = self._thresholds()
        best = scored[0] if scored else None
        if best and best[1] >= auto_min:
            row.track = best[0]
            row.score = best[1]
            row.status = "local"
            row.verified = True
            self._emit(row)
            return
        if best and best[1] >= CANDIDATE_MIN_SCORE:
            row.candidates = [MatchCandidate(track=track, score=score) for track, score in scored[:_MAX_CANDIDATES] if score >= CANDIDATE_MIN_SCORE]
            if self._auto and self._online and self._sources:
                # 自动模式且在线可用：先记下本地候选，交给在线搜索比分数，
                # 避免本地模糊命中压过在线精确命中。
                row.status = "pending"
                row.note = ""
                self._queue.append(self.rows.index(row))
                return
            if self._auto:
                # 自动模式：本地已有可用候选就直接采用，不再要求逐条确认。
                row.track = best[0]
                row.score = best[1]
                row.status = "local"
                row.verified = True
                row.note = ""
                self._remember(row)
                self._emit(row)
                return
            row.status = "review"
            row.note = "本地有相近结果"
            self._emit(row)
            return
        if self._online and self._sources:
            self._queue.append(self.rows.index(row))
            return
        row.status = "unmatched"
        row.note = "本地库没有这首歌"
        self._emit(row)

    # ----------------------------------------------------------------- online
    def _pick_sources(self) -> list:
        if not self._online:
            return []
        try:
            sources = [
                source
                for source in build_sources(getattr(self._client, "sources", []) or [])
                if source.searchable and source.can_play
            ]
        except Exception:  # noqa: BLE001
            sources = []
        return sources[:_MAX_SOURCES]

    def _start_online(self) -> None:
        if self._cancelled:
            return
        if not self._queue:
            self._start_variants()
            return
        self._pump()

    def _pump(self) -> None:
        if self._cancelled:
            return
        while self._queue and len(self._in_flight) < _MAX_ROWS_IN_FLIGHT:
            index = self._queue.pop(0)
            row = self.rows[index]
            key = (normalize_text(row.entry.title), normalize_text(row.entry.artist))
            cached = self._cache.get(key)
            if cached is not None:
                row.status = cached.status
                row.track = cached.track
                row.score = cached.score
                row.candidates = list(cached.candidates)
                row.note = cached.note
                row.verified = cached.verified
                self._emit(row)
                continue
            self._in_flight.add(index)
            self._search_row(index, row)
        if not self._in_flight and not self._queue:
            self._start_variants()

    def search(self, index: int, query: str) -> None:
        """Manual search: re-query the online sources with the user's words."""
        row = self.rows[index]
        row.status = "pending"
        row.candidates = []
        row.note = "正在搜索…"
        self._emit(row)
        if not self._sources:
            row.status = "unmatched"
            row.note = "没有可用的在线音源"
            self._emit(row)
            return
        self._in_flight.add(index)
        self._search_row(index, row, query=query.strip() or row.entry.title)

    def _search_row(self, index: int, row: MatchRow, *, query: str | None = None) -> None:
        if query is None:
            query = " ".join(part for part in (row.entry.title, row.entry.artist) if part).strip()
        else:
            query = query.strip()
        expected = _wanted_track(row.entry)
        collected: list[Track] = []
        pending = {"left": len(self._sources)}

        def finish() -> None:
            if self._cancelled or index not in self._in_flight:
                return
            self._in_flight.discard(index)
            ranked = sorted(
                (
                    MatchCandidate(track=track, score=_adjusted_score(expected, track))
                    for track in collected
                ),
                key=lambda item: item.score,
                reverse=True,
            )
            ranked = [item for item in ranked if item.score >= CANDIDATE_MIN_SCORE]
            row.candidates = _dedupe_candidates(ranked)[:_MAX_CANDIDATES]
            auto_min, auto_margin = self._thresholds()
            if ranked and ranked[0].score >= auto_min and (
                len(ranked) == 1 or ranked[0].score - ranked[1].score >= auto_margin
            ):
                row.track = ranked[0].track
                row.score = ranked[0].score
                row.status = "online"
                row.note = ""
                self._verify_row(index, row)
            elif ranked:
                row.status = "review"
                row.score = ranked[0].score
                row.note = "在线有相近结果"
                self._emit(row)
            else:
                row.status = "unmatched"
                row.note = "在线音源也没有找到"
                self._emit(row)
            self._remember(row)
            self.progress.emit(self.done, len(self.rows))
            QTimer.singleShot(0, self._pump)

        for source in self._sources:
            def callback(response: dict, source=source) -> None:
                try:
                    if response.get("ok"):
                        for item in response.get("data") or []:
                            try:
                                collected.append(track_from_item(item, source=source))
                            except Exception:  # noqa: BLE001
                                continue
                finally:
                    pending["left"] -= 1
                    if pending["left"] <= 0:
                        finish()

            try:
                self._client.search(
                    source.id,
                    query,
                    1,
                    callback,
                    timeout=_SEARCH_TIMEOUT_MS,
                    kind="music",
                )
            except Exception:  # noqa: BLE001
                pending["left"] -= 1
        if pending["left"] <= 0:
            finish()

    def _verify_row(self, index: int, row: MatchRow) -> None:
        if not self._verify or row.track is None or row.track.kind != "online":
            row.verified = None if row.track is None or row.track.kind == "online" else True
            self._emit(row)
            return
        from ..online import models as online_models

        def callback(response: dict) -> None:
            if self._cancelled:
                return
            if response.get("ok"):
                row.verified = True
                row.note = ""
            else:
                row.verified = False
                row.status = "unverified"
                row.note = "找到歌曲，但当前无法解析播放地址"
            self._emit(row)
            self.progress.emit(self.done, len(self.rows))

        try:
            self._client.resolve_playback(
                row.track.source_id,
                online_models.runtime_track(row.track),
                callback,
                timeout=_VERIFY_TIMEOUT_MS,
            )
        except Exception:  # noqa: BLE001
            row.verified = None
            self._emit(row)

    # ------------------------------------------------------------------ manual
    def choose(self, index: int, track: Track | None) -> None:
        row = self.rows[index]
        if track is None:
            row.track = None
            row.status = "unmatched"
            row.note = "已清空匹配"
            row.verified = None
        else:
            row.track = track
            row.status = "local" if track.kind == "local" else "online"
            row.verified = True if track.kind == "local" else None
            row.note = "手动选择"
            row.skipped = False
        self._remember(row)
        self._emit(row)
        self.progress.emit(self.done, len(self.rows))

    def skip(self, index: int) -> None:
        row = self.rows[index]
        row.skipped = True
        row.status = "skipped"
        row.note = "已跳过"
        self._emit(row)
        self.progress.emit(self.done, len(self.rows))

    def unskip(self, index: int) -> None:
        row = self.rows[index]
        row.skipped = False
        if row.track is None:
            row.status = "unmatched"
        else:
            row.status = "local" if row.track.kind == "local" else "online"
        self._emit(row)

    def rematch(self, index: int) -> None:
        row = self.rows[index]
        row.status = "pending"
        row.track = None
        row.candidates = []
        row.note = ""
        row.verified = None
        self._emit(row)
        if self._online and self._sources and row.entry.title:
            self._queue.append(index)
            self._pump()
        else:
            self._match_local(row)

    # ------------------------------------------------------------------ helpers
    # ------------------------------------------------------------- second pass
    def _start_variants(self) -> None:
        if self._cancelled:
            return
        if self._variant_pass or not self._online or not self._sources:
            self.progress.emit(self.done, len(self.rows))
            self._finished()
            return
        self._variant_pass = True
        self._variant_queue = [
            index for index, row in enumerate(self.rows)
            if row.status in ("unmatched", "review")
        ]
        if not self._variant_queue:
            self.progress.emit(self.done, len(self.rows))
            self._finished()
            return
        self._pump_variants()

    def _pump_variants(self) -> None:
        if self._cancelled:
            return
        while self._variant_queue and len(self._in_flight) < _MAX_ROWS_IN_FLIGHT:
            index = self._variant_queue.pop(0)
            self._in_flight.add(index)
            self._variant_row(index)
        if not self._in_flight and not self._variant_queue:
            self.progress.emit(self.done, len(self.rows))
            self._finished()

    def _variant_row(self, index: int) -> None:
        row = self.rows[index]
        variants = _query_variants(row.entry)
        if not variants:
            self._in_flight.discard(index)
            QTimer.singleShot(0, self._pump_variants)
            return
        expected = _wanted_track(row.entry)
        collected: list[Track] = []
        queries = list(variants)

        def next_query() -> None:
            if self._cancelled or index not in self._in_flight:
                return
            if not queries:
                self._finish_variants(index, row, expected, collected)
                return
            query = queries.pop(0)
            pending = {"left": len(self._sources)}

            def finish() -> None:
                pending["left"] -= 1
                if pending["left"] > 0:
                    return
                auto_min, auto_margin = self._thresholds()
                ranked = _dedupe_candidates(
                    sorted(
                        (
                            MatchCandidate(track=track, score=_adjusted_score(expected, track))
                            for track in collected
                        ),
                        key=lambda item: item.score,
                        reverse=True,
                    )
                )
                ranked = [item for item in ranked if item.score >= CANDIDATE_MIN_SCORE]
                confident = bool(ranked) and ranked[0].score >= auto_min and (
                    len(ranked) == 1 or ranked[0].score - ranked[1].score >= auto_margin
                )
                if self._auto and row.candidates:
                    local_best = row.candidates[0]
                    if not ranked or local_best.score >= ranked[0].score:
                        row.track = local_best.track
                        row.score = local_best.score
                        row.status = "local"
                        row.verified = True
                        row.note = ""
                        self._in_flight.discard(index)
                        self._remember(row)
                        self.progress.emit(self.done, len(self.rows))
                        self._emit(row)
                        QTimer.singleShot(0, self._pump)
                        return
                if ranked and (self._auto or confident):
                    row.candidates = ranked[:_MAX_CANDIDATES]
                    row.track = ranked[0].track
                    row.score = ranked[0].score
                    row.status = "online"
                    row.note = ""
                    self._in_flight.discard(index)
                    self._remember(row)
                    self.progress.emit(self.done, len(self.rows))
                    if self._verify:
                        self._verify_row(index, row)
                    else:
                        self._emit(row)
                        QTimer.singleShot(0, self._pump_variants)
                    return
                QTimer.singleShot(0, next_query)

            for source in self._sources:
                def callback(response: dict, source=source) -> None:
                    try:
                        if response.get("ok"):
                            for item in response.get("data") or []:
                                try:
                                    collected.append(track_from_item(item, source=source))
                                except Exception:  # noqa: BLE001
                                    continue
                    finally:
                        finish()

                self._client.search(
                    source.id,
                    query,
                    1,
                    callback,
                    timeout=_SEARCH_TIMEOUT_MS,
                    kind="music",
                )

        next_query()

    def _finish_variants(self, index: int, row: MatchRow, expected: Track, collected: list[Track]) -> None:
        self._in_flight.discard(index)
        ranked = _dedupe_candidates(
            sorted(
                (
                    MatchCandidate(track=track, score=_adjusted_score(expected, track))
                    for track in collected
                ),
                key=lambda item: item.score,
                reverse=True,
            )
        )
        ranked = [item for item in ranked if item.score >= CANDIDATE_MIN_SCORE]
        row.candidates = ranked[:_MAX_CANDIDATES]
        if ranked and self._auto:
            row.track = ranked[0].track
            row.status = "online"
            row.score = ranked[0].score
            row.note = ""
            self._remember(row)
            self.progress.emit(self.done, len(self.rows))
            if self._verify:
                self._verify_row(index, row)
            else:
                self._emit(row)
                QTimer.singleShot(0, self._pump_variants)
            return
        if ranked:
            row.status = "review"
            row.score = ranked[0].score
            row.note = "补充搜索后有相近结果，请确认"
        else:
            row.status = "unmatched"
            row.note = "换了搜索词也没有找到"
        self._remember(row)
        self._emit(row)
        self.progress.emit(self.done, len(self.rows))
        QTimer.singleShot(0, self._pump_variants)

    def _remember(self, row: MatchRow) -> None:
        key = (normalize_text(row.entry.title), normalize_text(row.entry.artist))
        self._cache[key] = MatchRow(
            entry=row.entry,
            status=row.status,
            track=row.track,
            score=row.score,
            candidates=list(row.candidates),
            note=row.note,
            verified=row.verified,
            skipped=row.skipped,
        )

    def _emit(self, row: MatchRow) -> None:
        try:
            self.row_changed.emit(self.rows.index(row))
        except ValueError:
            pass

    def _finished(self) -> None:
        if self._cancelled:
            return
        if self._auto:
            # 兜底：仍停在 review/pending 且有候选的行采用最佳候选，但不伪造
            # “已验证”——能否真正播放由首次播放后的绑定确认决定。
            for row in self.rows:
                if row.status in ("review", "pending") and row.candidates:
                    best = row.candidates[0]
                    row.track = best.track
                    row.score = best.score
                    row.status = "online" if best.track.kind == "online" else "local"
                    row.verified = None
                    row.note = "自动采用最佳候选，首次播放后验证"
        self._started = False
        self.finished.emit()
