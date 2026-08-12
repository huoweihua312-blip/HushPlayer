"""One-shot online recovery matching for unavailable local tracks."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from app.services.remote_track_store import RemoteTrackStore
from app.services.unified_search_service import UnifiedSearchService
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import Track, artwork_url_from_payload


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    track: OnlineTrack
    score: int


class OnlineTrackRecoveryService(QObject):
    """Search enabled online sources without changing the visible search page."""

    status_changed = Signal(int, str)
    match_found = Signal(int, object)
    candidates_found = Signal(int, object)
    failed = Signal(int, str)

    AUTO_MIN_SCORE = 80
    AUTO_MARGIN = 15
    CANDIDATE_MIN_SCORE = 55

    def __init__(
        self,
        client=None,
        search_service: UnifiedSearchService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._search_service = search_service
        if self._search_service is None and client is not None:
            self._search_service = UnifiedSearchService(client, self, debounce_ms=300)
        if self._search_service is not None:
            self._search_service.resultsChanged.connect(self._on_results)
        self._generation = 0
        self._search_generation = 0
        self._track: Track | None = None

    @property
    def generation(self) -> int:
        return self._generation

    def request(self, track: Track) -> int:
        self.cancel()
        self._generation += 1
        generation = self._generation
        if not isinstance(track, Track) or not track.is_missing or track.is_online:
            self.failed.emit(generation, "这首歌曲当前不需要在线恢复。")
            return generation
        query = self.build_query(track)
        if not query:
            self.failed.emit(generation, "歌曲缺少可用于在线匹配的信息。")
            return generation
        if self._search_service is None:
            self.failed.emit(generation, "在线来源服务当前不可用。")
            return generation
        self._track = track
        self.status_changed.emit(generation, "正在查找在线版本…")
        self._search_generation = self._search_service.schedule_search(query)
        return generation

    def cancel(self) -> None:
        self._track = None
        self._search_generation = 0
        if self._search_service is not None and self._search_service.keyword:
            self._search_service.schedule_search("")

    def shutdown(self) -> None:
        self.cancel()
        if self._search_service is not None:
            self._search_service.shutdown()

    @staticmethod
    def build_query(track: Track) -> str:
        return " ".join(
            value
            for value in (str(track.title or "").strip(), str(track.artist or "").strip())
            if value
        )

    @classmethod
    def score_match(cls, source: Track, candidate: OnlineTrack) -> int:
        title = cls._field_score(source.title, candidate.title, 90, 60, 45)
        artist = cls._artist_score(source.artist, candidate.artist)
        album = cls._field_score(source.album, candidate.album, 10, 6, 0)
        duration = cls._duration_score(source.duration_ms, candidate.duration_ms)
        return title + artist + album + duration

    @classmethod
    def _artist_score(cls, expected: str, actual: str) -> int:
        normalized_expected = cls.normalize_text(expected)
        if not normalized_expected:
            return 0
        normalized_actual = cls.normalize_text(actual)
        if normalized_expected == normalized_actual:
            return 45
        if normalized_expected in normalized_actual or normalized_actual in normalized_expected:
            return 30
        return -25

    @classmethod
    def _field_score(
        cls,
        expected: str,
        actual: str,
        exact_score: int,
        contains_score: int,
        token_score: int,
    ) -> int:
        normalized_expected = cls.normalize_text(expected)
        normalized_actual = cls.normalize_text(actual)
        if not normalized_expected or not normalized_actual:
            return 0
        if normalized_expected == normalized_actual:
            return exact_score
        if normalized_expected in normalized_actual or normalized_actual in normalized_expected:
            return contains_score
        expected_terms = set(normalized_expected.split())
        actual_terms = set(normalized_actual.split())
        if expected_terms and expected_terms <= actual_terms:
            return token_score
        return 0

    @staticmethod
    def _duration_score(expected: int | None, actual: int | None) -> int:
        if expected is None or actual is None or expected <= 0 or actual <= 0:
            return 0
        delta = abs(int(expected) - int(actual))
        if delta <= 8_000:
            return 8
        if delta <= 20_000:
            return 4
        return 0

    @staticmethod
    def normalize_text(value: str | None) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        cleaned = "".join(" " if unicodedata.category(char).startswith("P") else char for char in text)
        return " ".join(cleaned.split())

    def _on_results(self, search_generation: int, keyword: str, results: list, summary: dict) -> None:
        if self._track is None or int(search_generation) != self._search_generation:
            return
        if str(keyword or "").strip() != self.build_query(self._track):
            return
        final = bool(summary.get("final")) if isinstance(summary, dict) else False
        if not final:
            self.status_changed.emit(self._generation, "正在等待在线来源返回结果…")
            return
        track = self._track
        candidates = self._rank_candidates(track, results)
        self._track = None
        if not candidates:
            self.failed.emit(self._generation, "没有找到可靠的在线版本。")
            return
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0
        if (
            top.score >= self.AUTO_MIN_SCORE
            and (len(candidates) == 1 or top.score - second_score >= self.AUTO_MARGIN)
        ):
            self.match_found.emit(self._generation, top.track)
            return
        self.candidates_found.emit(
            self._generation,
            tuple(item.track for item in candidates[:8]),
        )

    def _rank_candidates(self, source: Track, results: list) -> tuple[RecoveryCandidate, ...]:
        ranked: list[RecoveryCandidate] = []
        for rank, raw in enumerate(results if isinstance(results, list) else []):
            candidate = self._map_candidate(raw, rank)
            if candidate is None:
                continue
            score = self.score_match(source, candidate)
            if score >= self.CANDIDATE_MIN_SCORE:
                ranked.append(RecoveryCandidate(candidate, score))
        ranked.sort(key=lambda item: (-item.score, item.track.result_rank, item.track.id))
        return tuple(ranked)

    @classmethod
    def _map_candidate(cls, raw: dict, rank: int) -> OnlineTrack | None:
        if not isinstance(raw, dict):
            return None
        capabilities = raw.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        if capabilities.get("playback") is not True:
            return None
        source_id = str(raw.get("sourceId") or raw.get("source_id") or "").strip()
        if not source_id:
            return None
        remote_id = str(
            raw.get("remote_id")
            or raw.get("remoteId")
            or raw.get("id")
            or raw.get("songmid")
            or ""
        ).strip()
        identity_payload = dict(raw)
        identity_payload["source_id"] = source_id
        identity_payload["remote_id"] = remote_id
        stable_id = RemoteTrackStore.stable_id_for_track(identity_payload)
        duration_ms = cls._duration_ms(raw.get("durationMs") if "durationMs" in raw else raw.get("duration"))
        title = str(raw.get("title") or "未知歌曲").strip()
        artist = str(raw.get("artist") or "未知艺术家").strip()
        album = str(raw.get("album") or "未知专辑").strip()
        artwork_url = artwork_url_from_payload(raw)
        payload = dict(raw)
        payload.update({"source_id": source_id, "sourceId": source_id, "remote_id": remote_id})
        return OnlineTrack(
            id=stable_id,
            source_id=source_id,
            source_name=str(raw.get("sourceName") or source_id).strip(),
            title=title,
            artist=artist,
            album=album,
            duration_ms=duration_ms,
            artwork_key=str(raw.get("artworkKey") or stable_id),
            quality=str(raw.get("quality") or raw.get("bitrate") or "标准"),
            stable_identity=stable_id,
            is_favorite=False,
            is_downloaded=False,
            is_cached=False,
            availability="not_resolved",
            explicit=bool(raw.get("explicit") or raw.get("explicitContent")),
            result_rank=rank,
            artwork_url=artwork_url,
            remote_id=remote_id,
            raw=payload,
        )

    @staticmethod
    def _duration_ms(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            duration = max(0, int(float(value)))
        except (TypeError, ValueError):
            return None
        return duration * 1000 if duration < 10_000 else duration
