"""Timer-driven mock online search with deterministic source scenarios only."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_search_state import OnlineSearchState
from app.ui_v2.models.online_source import OnlineSource
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.search_history_item import SearchHistoryItem


class OnlineAdapter(QObject):
    """Owns all prototype online-search state without contacting any service."""

    query_changed = Signal(str)
    search_started = Signal()
    search_progress_changed = Signal(int)
    search_results_changed = Signal(object)
    search_completed = Signal(object)
    search_failed = Signal(str)
    source_state_changed = Signal(object)
    history_changed = Signal(object)
    favorite_changed = Signal(str, bool)
    download_requested = Signal(str)
    play_requested = Signal(object)
    add_to_playlist_requested = Signal(str, str)
    result_updated = Signal(object)
    playing_track_changed = Signal(str)
    state_changed = Signal(object)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        parent: QObject | None = None,
        *,
        timer_enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self.playlists = playlists
        self._query = ""
        self._scenario = "success"
        self._results: tuple[OnlineTrack, ...] = ()
        self._sources = self._default_sources()
        self._history: list[SearchHistoryItem] = []
        self._state = OnlineSearchState("idle", "")
        self._generation = 0
        self._search_step = 0
        self._timer_enabled = timer_enabled
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._advance_search)
        self._playing_track_id = ""
        self._clock = datetime(2026, 3, 1, 10, 0)
        collection.favorite_changed.connect(self._sync_collection_favorite)

    @property
    def query(self) -> str:
        return self._query

    @property
    def state(self) -> OnlineSearchState:
        return self._state

    @property
    def scenario(self) -> str:
        return self._scenario

    @property
    def playing_track_id(self) -> str:
        return self._playing_track_id

    def results(self) -> tuple[OnlineTrack, ...]:
        return self._results

    def sources(self) -> tuple[OnlineSource, ...]:
        return tuple(self._sources)

    def history(self) -> tuple[SearchHistoryItem, ...]:
        return tuple(self._history)

    def set_query(self, text: str) -> None:
        query = str(text or "").strip()
        if query == self._query:
            return
        self._query = query
        self.query_changed.emit(query)

    def search(self) -> bool:
        if not self._query:
            return False
        self._generation += 1
        self._search_step = 0
        self._timer.stop()
        enabled = [source for source in self._sources if source.enabled]
        if not enabled:
            self._set_state("failed", "请先启用至少一个来源。")
            self.search_failed.emit("没有可用来源")
            return False
        self._results = ()
        self.search_results_changed.emit(self._results)
        self._set_sources(
            tuple(
                replace(source, status="searching", result_count=0, last_error="")
                if source.enabled
                else replace(source, status="disabled", result_count=0)
                for source in self._sources
            )
        )
        self._set_state("searching", "正在查询已启用来源。", progress=0)
        self.search_started.emit()
        if self._timer_enabled:
            self._timer.start()
        return True

    def cancel_search(self) -> None:
        if self._state.phase != "searching":
            return
        self._generation += 1
        self._timer.stop()
        self._set_sources(
            tuple(
                replace(source, status="ready" if source.enabled else "disabled")
                for source in self._sources
            )
        )
        self._set_state("idle", "搜索已取消。")

    def retry(self) -> bool:
        return self.search()

    def complete_for_test(self, generation: int | None = None) -> None:
        self._complete_search(self._generation if generation is None else generation)

    def advance_for_test(self) -> None:
        self._advance_search()

    def set_enabled_sources(self, source_ids) -> None:
        if self._state.phase == "searching":
            return
        selected = set(source_ids)
        self._set_sources(
            tuple(
                replace(
                    source,
                    enabled=source.id in selected,
                    status="ready" if source.id in selected else "disabled",
                    result_count=0 if source.id not in selected else source.result_count,
                    last_error="" if source.id not in selected else source.last_error,
                )
                for source in self._sources
            )
        )
        self._sync_result_availability()

    def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        if self._state.phase == "searching":
            return
        self._set_sources(
            tuple(
                replace(source, enabled=bool(enabled), status="ready" if enabled else "disabled")
                if source.id == source_id
                else source
                for source in self._sources
            )
        )
        self._sync_result_availability()

    def clear_results(self) -> None:
        self._results = ()
        self.search_results_changed.emit(self._results)
        self._set_state("idle", "")

    def clear_history(self) -> None:
        if not self._history:
            return
        self._history.clear()
        self.history_changed.emit(self.history())

    def remove_history_item(self, query: str) -> None:
        normalized = str(query or "").casefold()
        updated = [item for item in self._history if item.query.casefold() != normalized]
        if len(updated) == len(self._history):
            return
        self._history = updated
        self.history_changed.emit(self.history())

    def request_play(self, track_id: str) -> bool:
        track = self._track_for_id(track_id)
        if track is None or track.availability != "available":
            return False
        unified = self.collection.upsert_track(track.as_track())
        self.set_playing_track(track.id)
        self.play_requested.emit(unified)
        return True

    def toggle_favorite(self, track_id: str) -> None:
        track = self._track_for_id(track_id)
        if track is None:
            return
        desired = not track.is_favorite
        unified = self.collection.upsert_track(track.as_track())
        self.collection.set_favorite(unified.id, desired)

    def request_download(self, track_id: str) -> bool:
        track = self._track_for_id(track_id)
        source = self._source_for_id(track.source_id) if track else None
        if track is None or source is None or not source.supports_download:
            return False
        self._replace_result(replace(track, is_downloaded=True, is_cached=True))
        self.download_requested.emit(track.id)
        return True

    def request_add_to_playlist(self, track_id: str, playlist_id: str) -> bool:
        track = self._track_for_id(track_id)
        if track is None or self.playlists.playlist_for_id(playlist_id) is None:
            return False
        unified = self.collection.upsert_track(track.as_track())
        if not self.playlists.add_tracks(playlist_id, (unified.id,)):
            return False
        self.add_to_playlist_requested.emit(track_id, playlist_id)
        return True

    def load_mock_scenario(self, name: str) -> None:
        allowed = {
            "success",
            "empty",
            "partial_failure",
            "total_failure",
            "slow",
            "mixed_sources",
            "duplicate_results",
            "long_text",
            "explicit_content",
        }
        self._scenario = name if name in allowed else "success"

    def set_playing_track(self, track_id: str) -> None:
        normalized = str(track_id or "")
        if normalized == self._playing_track_id:
            return
        self._playing_track_id = normalized
        self.playing_track_changed.emit(normalized)

    def _advance_search(self) -> None:
        generation = self._generation
        if self._state.phase != "searching":
            return
        self._search_step += 1
        if self._scenario == "slow" and self._search_step < 3:
            self._set_state("searching", "正在等待较慢的 mock 来源。", self._search_step * 30)
            return
        self._complete_search(generation)

    def _complete_search(self, generation: int) -> None:
        if generation != self._generation or self._state.phase != "searching":
            return
        self._timer.stop()
        if self._scenario == "total_failure":
            self._set_sources(
                tuple(
                    replace(
                        source,
                        status="failed" if source.enabled else "disabled",
                        result_count=0,
                        last_error="Mock 来源暂不可用" if source.enabled else "",
                    )
                    for source in self._sources
                )
            )
            self._set_state("failed", "所有已启用来源均不可用。")
            self.search_failed.emit("所有来源失败")
            return
        sources = list(self._sources)
        results: list[OnlineTrack] = []
        for index, source in enumerate(sources):
            if not source.enabled:
                sources[index] = replace(source, status="disabled", result_count=0)
                continue
            if self._scenario == "partial_failure" and index == 0:
                sources[index] = replace(
                    source, status="failed", result_count=0, last_error="Mock 响应超时"
                )
                continue
            generated = () if self._scenario == "empty" else self._generate_source_results(source, index)
            results.extend(generated)
            status = "warning" if index == 1 and self._scenario == "mixed_sources" else "success"
            sources[index] = replace(
                source,
                status=status,
                result_count=len({item.id for item in generated}),
                last_error="部分元数据不可用" if status == "warning" else "",
            )
        self._set_sources(tuple(sources))
        self._results = self._dedupe_results(results)
        self.search_results_changed.emit(self._results)
        self._add_history(self._query)
        if self._results:
            failed = [source for source in self._sources if source.status == "failed"]
            message = "部分来源未返回结果。" if failed else ""
            self._set_state("results", message, progress=100)
            self.search_completed.emit(self._results)
            return
        self._set_state("empty", "没有找到匹配的 mock 在线歌曲。", progress=100)
        self.search_completed.emit(self._results)

    def _generate_source_results(self, source: OnlineSource, source_index: int) -> tuple[OnlineTrack, ...]:
        titles = (
            "雾中的海岸",
            "After the Rain",
            "夜航 Night Flight",
            "Paper Moon 纸月亮",
            "Signal From Home",
            "Slowly Closer",
            "Glass Cities",
            "长标题用于在线搜索结果省略验证以及工具提示覆盖",
        )
        artists = ("林澈", "North Window", "陈默与 The Quiet Hours", "A Long Online Artist Name")
        albums = ("在线试听集", "Night Signals", "Mock Source Archive", "A Long Online Album Title")
        values: list[OnlineTrack] = []
        for rank in range(16):
            raw_id = f"{source.id}-{rank:03d}"
            if self._scenario == "duplicate_results" and rank == 15:
                raw_id = f"{source.id}-000"
            title = titles[rank % len(titles)]
            if self._scenario == "long_text" and rank == 1:
                title = f"{title} - 这一段很长的 mock 搜索标题用于验证所有宽度下的省略行为"
            explicit = self._scenario == "explicit_content" and rank % 3 == 0
            duration = None if rank == 7 else 3_721_000 if rank == 8 else 170_000 + rank * 13_700
            track_id = f"online:{source.id}:{raw_id}"
            current = self.collection.track_for_id(track_id)
            values.append(
                OnlineTrack(
                    id=track_id,
                    source_id=source.id,
                    source_name=source.name,
                    title=title,
                    artist=artists[(rank + source_index) % len(artists)],
                    album=albums[(rank * 2 + source_index) % len(albums)],
                    duration_ms=duration,
                    artwork_key=f"{source.id}:{rank % 5}",
                    quality=("Hi-Res" if rank % 5 == 0 else "320k" if rank % 2 else "标准"),
                    stable_identity=f"{source.id}:{raw_id}",
                    is_favorite=current.is_favorite if current is not None else False,
                    is_downloaded=False,
                    is_cached=False,
                    availability="available" if source.supports_playback else "unavailable",
                    explicit=explicit,
                    result_rank=source_index * 16 + rank,
                )
            )
        return tuple(values)

    def _dedupe_results(self, results) -> tuple[OnlineTrack, ...]:
        by_id: dict[str, OnlineTrack] = {}
        for result in results:
            by_id.setdefault(result.id, result)
        return tuple(sorted(by_id.values(), key=lambda item: item.result_rank))

    def _add_history(self, query: str) -> None:
        normalized = query.casefold()
        self._history = [item for item in self._history if item.query.casefold() != normalized]
        self._clock += timedelta(minutes=1)
        self._history.insert(0, SearchHistoryItem(query, self._clock))
        del self._history[20:]
        self.history_changed.emit(self.history())

    def _sync_collection_favorite(self, track_id: str, favorite: bool) -> None:
        track = self._track_for_id(track_id)
        if track is not None and track.is_favorite != favorite:
            self._replace_result(replace(track, is_favorite=favorite))
        self.favorite_changed.emit(track_id, favorite)

    def _replace_result(self, updated: OnlineTrack) -> None:
        for index, track in enumerate(self._results):
            if track.id != updated.id:
                continue
            values = list(self._results)
            values[index] = updated
            self._results = tuple(values)
            self.result_updated.emit(updated)
            return

    def _sync_result_availability(self) -> None:
        for track in self._results:
            source = self._source_for_id(track.source_id)
            availability = (
                "available"
                if source is not None and source.enabled and source.supports_playback
                else "unavailable"
            )
            if availability != track.availability:
                self._replace_result(replace(track, availability=availability))

    def _track_for_id(self, track_id: str) -> OnlineTrack | None:
        return next((track for track in self._results if track.id == track_id), None)

    def _source_for_id(self, source_id: str) -> OnlineSource | None:
        return next((source for source in self._sources if source.id == source_id), None)

    def _set_sources(self, sources: tuple[OnlineSource, ...]) -> None:
        self._sources = list(sources)
        self.source_state_changed.emit(self.sources())

    def _set_state(self, phase: str, message: str, progress: int = 0) -> None:
        self._state = OnlineSearchState(
            phase=phase,
            query=self._query,
            progress=max(0, min(100, progress)),
            message=message,
            generation=self._generation,
        )
        self.state_changed.emit(self._state)
        self.search_progress_changed.emit(self._state.progress)

    @staticmethod
    def _default_sources() -> list[OnlineSource]:
        return [
            OnlineSource("catalog", "Mock Catalog", True, "ready", 82, 0, "", True, True, True, "catalog"),
            OnlineSource("archive", "Mock Archive", True, "ready", 126, 0, "", True, False, True, "archive"),
            OnlineSource("radio", "Mock Radio", True, "ready", 178, 0, "", True, True, False, "radio"),
            OnlineSource("indie", "Indie Shelf", True, "ready", 94, 0, "", True, True, True, "catalog"),
            OnlineSource("community", "Community Index", True, "ready", 214, 0, "", False, False, False, "index"),
            OnlineSource("public", "Public Collection", True, "ready", 156, 0, "", True, True, True, "archive"),
        ]
