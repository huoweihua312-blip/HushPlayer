"""Online discovery state adapter with deterministic mock and formal modes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from app.services.online_discovery_runtime import OnlineDiscoveryRuntime
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_search_state import OnlineSearchState
from app.ui_v2.models.online_source import OnlineSource
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.search_history_item import SearchHistoryItem
from app.ui_v2.models.track import Track, artwork_url_from_payload
from app.ui_v2.widgets.track_display import present_track_identity_values


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
    track_updated = Signal(object)
    playing_track_changed = Signal(str)
    state_changed = Signal(object)
    playback_unavailable = Signal(str, str)
    track_info_changed = Signal(object)
    notification_changed = Signal(str)
    remote_collection_changed = Signal()

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        parent: QObject | None = None,
        *,
        timer_enabled: bool = True,
        discovery: OnlineDiscoveryRuntime | None = None,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self.playlists = playlists
        self._query = ""
        self._scenario = "success"
        self._results: tuple[OnlineTrack, ...] = ()
        self._recommendation_results: dict[str, OnlineTrack] = {}
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
        self.discovery = discovery
        self._formal_generation = 0
        self._formal_catalog: list[dict] = []
        self._formal_selected_source_ids: list[str] = []
        self._metadata_requests: dict[int, tuple[int, str, str]] = {}
        self._artwork_generation = 0
        self._closed = False
        collection.favorite_changed.connect(self._sync_collection_favorite)
        collection.tracks_changed.connect(self._sync_result_availability)
        if self.discovery is not None:
            self._connect_formal_services()

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
    def is_formal(self) -> bool:
        return self.discovery is not None

    @property
    def can_mutate_remote(self) -> bool:
        return self.discovery is not None and self.discovery.bridge is not None

    @property
    def playing_track_id(self) -> str:
        return self._playing_track_id

    def results(self) -> tuple[OnlineTrack, ...]:
        return self._results

    def register_recommendation_tracks(self, tracks) -> None:
        """Keep temporary Browse results available for existing actions."""

        for track in tracks if isinstance(tracks, (tuple, list)) else ():
            if isinstance(track, OnlineTrack):
                self._recommendation_results[track.id] = track

    def clear_recommendation_tracks(self) -> None:
        self._recommendation_results.clear()

    def map_recommendation_track(self, raw: dict, rank: int) -> OnlineTrack | None:
        """Map a background result without changing the Online Search page."""

        if not self.is_formal or not isinstance(raw, dict):
            return None
        return self._map_formal_track(dict(raw), int(rank))

    def ensure_actionable_track(self, track: Track) -> OnlineTrack | None:
        """Expose one persisted remote track through the existing action path."""

        if not isinstance(track, Track) or not track.is_online:
            return None
        existing = self._track_for_id(track.id)
        if existing is not None:
            return existing
        remote = OnlineTrack(
            id=track.id,
            source_id=track.source_id,
            source_name=track.source_name,
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_ms=track.duration_ms,
            artwork_key=track.artwork_key or track.stable_id,
            quality="标准",
            stable_identity=track.stable_id,
            is_favorite=track.is_favorite,
            is_downloaded=bool(track.local_path),
            is_cached=False,
            availability=track.availability,
            explicit=False,
            result_rank=0,
            artwork_url=track.artwork_url,
            remote_id=track.remote_track_id,
            raw=dict(track.remote_payload),
            artwork_data=bytes(track.artwork_data),
            availability_detail=track.availability_detail,
        )
        self.register_recommendation_tracks((remote,))
        return remote

    def sources(self) -> tuple[OnlineSource, ...]:
        return tuple(self._sources)

    def history(self) -> tuple[SearchHistoryItem, ...]:
        return tuple(self._history)

    def set_query(self, text: str) -> None:
        if self._closed:
            return
        query = str(text or "").strip()
        if query == self._query:
            return
        self._query = query
        self.query_changed.emit(query)
        if self.is_formal:
            self._formal_generation = self._schedule_formal_search(query)

    def search(self) -> bool:
        if self._closed:
            return False
        if self.is_formal:
            if not self._query:
                return False
            self._formal_generation = self._schedule_formal_search(self._query)
            return True
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
        if self.is_formal:
            self.discovery.search_service.schedule_search("")
            self._set_state("idle", "搜索已取消。")
            return
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

    def refresh_sources(self) -> None:
        if self.is_formal:
            self.discovery.search_service.refresh_source_catalog()

    def complete_for_test(self, generation: int | None = None) -> None:
        self._complete_search(self._generation if generation is None else generation)

    def advance_for_test(self) -> None:
        self._advance_search()

    def set_enabled_sources(self, source_ids) -> None:
        if self.is_formal:
            selected = [str(source_id or "").strip() for source_id in source_ids]
            self._formal_selected_source_ids = [value for value in selected if value]
            self.discovery.search_service.set_selected_source_ids(
                self._formal_selected_source_ids,
                restart=True,
            )
            self._sync_formal_sources()
            return
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
        if self.is_formal:
            selected = set(self._formal_selected_source_ids)
            if enabled:
                selected.add(str(source_id or "").strip())
            else:
                selected.discard(str(source_id or "").strip())
            self.set_enabled_sources(selected)
            return
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
        if self.is_formal:
            self.discovery.search_service.schedule_search("")
            self._results = ()
            self.search_results_changed.emit(self._results)
            self._set_state("idle", "")
            return
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
        if self.is_formal:
            track = self._track_for_id(track_id)
            if track is None:
                return False
            if not self._can_request_play(track):
                message = (
                    str(track.availability_detail or "").strip()
                    or "当前在线来源暂不支持播放这首歌曲。"
                )
                self.playback_unavailable.emit(track.id, message)
                self.notification_changed.emit(message)
                return False
            track = replace(track, availability="resolving", availability_detail="")
            self._replace_result(track)
            unified = track.as_track()
            self.collection.upsert_track(unified)
            self.set_playing_track(track.id)
            self.play_requested.emit(unified)
            return True
        if self.collection.read_only:
            return False
        track = self._track_for_id(track_id)
        if track is None or not self._can_request_play(track):
            if track is not None:
                message = "在线歌曲暂不可直接播放，请先使用本地文件。"
                self.playback_unavailable.emit(track.id, message)
                self.notification_changed.emit(message)
            return False
        track = replace(track, availability="resolving", availability_detail="")
        self._replace_result(track)
        unified = self.collection.upsert_track(track.as_track())
        self.set_playing_track(track.id)
        self.play_requested.emit(unified)
        return True

    def toggle_favorite(self, track_id: str) -> None:
        if self.is_formal:
            track = self._track_for_id(track_id)
            if track is None:
                return
            desired = not track.is_favorite
            if not self.discovery.bridge.set_favorite(self._payload_for_track(track), desired):
                return
            self._replace_result(replace(track, is_favorite=desired))
            self.favorite_changed.emit(track.id, desired)
            self.remote_collection_changed.emit()
            self.notification_changed.emit(
                "已收藏到‘我喜欢’。" if desired else "已取消收藏该在线歌曲。"
            )
            return
        if self.collection.read_only:
            return
        track = self._track_for_id(track_id)
        if track is None:
            return
        desired = not track.is_favorite
        unified = self.collection.upsert_track(track.as_track())
        self.collection.set_favorite(unified.id, desired)

    def request_download(self, track_id: str) -> bool:
        if self.is_formal:
            self.notification_changed.emit("在线下载不属于 Q5A 范围。")
            return False
        if self.collection.read_only:
            return False
        track = self._track_for_id(track_id)
        source = self._source_for_id(track.source_id) if track else None
        if track is None or source is None or not source.supports_download:
            return False
        self._replace_result(replace(track, is_downloaded=True, is_cached=True))
        self.download_requested.emit(track.id)
        return True

    def request_add_to_playlist(self, track_id: str, playlist_id: str) -> bool:
        if self.is_formal:
            track = self._track_for_id(track_id)
            if track is None:
                return False
            if not self.discovery.bridge.add_to_playlist(
                self._payload_for_track(track), playlist_id
            ):
                return False
            self.add_to_playlist_requested.emit(track.id, playlist_id)
            self.remote_collection_changed.emit()
            self.notification_changed.emit("在线歌曲已加入歌单。")
            return True
        if self.collection.read_only:
            return False
        track = self._track_for_id(track_id)
        if track is None or self.playlists.playlist_for_id(playlist_id) is None:
            return False
        unified = self.collection.upsert_track(track.as_track())
        if not self.playlists.add_tracks(playlist_id, (unified.id,)):
            return False
        self.add_to_playlist_requested.emit(track_id, playlist_id)
        return True

    def replace_track_memberships(self, old_track: Track, replacement: OnlineTrack) -> str:
        """Replace an old playlist/favorite member with one online track."""

        if not self.is_formal or not isinstance(old_track, Track) or not isinstance(
            replacement, OnlineTrack
        ):
            return "not_found"
        old_identifier = str(
            old_track.remote_identity
            or old_track.remote_track_id
            or old_track.stable_identity
            or old_track.id
        ).strip() if old_track.is_online else str(old_track.local_path or old_track.id).strip()
        old_kind = "remote" if old_track.is_online else "local"
        if not old_identifier:
            return "failed"
        result = self.discovery.bridge.replace_track_memberships(
            (old_kind, old_identifier),
            self._payload_for_track(replacement),
        )
        if result == "replaced":
            self.remote_collection_changed.emit()
        return result

    def set_playback_source(self, old_track: Track, replacement: OnlineTrack) -> str:
        """Persist a source override without changing playlist membership."""

        if not self.is_formal or not isinstance(old_track, Track) or not isinstance(
            replacement, OnlineTrack
        ):
            return "not_found"
        if not old_track.is_online:
            # Missing local-file recovery remains playable for the current
            # session, but there is no remote record to attach a source to.
            return "not_found"
        old_identifier = str(
            old_track.remote_identity
            or old_track.stable_identity
            or old_track.remote_track_id
            or old_track.id
        ).strip()
        if not old_identifier:
            return "failed"
        result = self.discovery.bridge.set_playback_source(
            ("remote", old_identifier),
            self._payload_for_track(replacement),
        )
        if result == "source_updated":
            self.remote_collection_changed.emit()
        return result

    def build_playback_source_track(
        self,
        old_track: Track,
        replacement: OnlineTrack,
    ) -> Track | None:
        """Keep the old Track identity while routing its queue item to a source."""

        if not isinstance(old_track, Track) or not isinstance(replacement, OnlineTrack):
            return None
        if not self._can_request_play(replacement):
            return None
        self.register_recommendation_tracks((replacement,))
        payload = dict(old_track.remote_payload)
        payload["playback_source"] = self._payload_for_track(replacement)
        return replace(
            old_track,
            source_type="online",
            is_missing=False,
            local_path="",
            availability="playable",
            availability_detail="",
            remote_payload=payload,
        )

    def load_mock_scenario(self, name: str) -> None:
        if self.is_formal:
            return
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

    def apply_remote_state(
        self,
        stable_identity: str,
        state: str | None = None,
        detail: str = "",
        payload: dict | None = None,
        duration_ms: int | None = None,
    ) -> Track | None:
        """Apply runtime state and enrichment to one stable remote identity."""

        identity = str(stable_identity or "").strip()
        if self._closed or not identity:
            return None
        online = self._online_result_for_identity(identity)
        if online is not None:
            updated = self._enrich_online_track(
                online,
                state=state,
                detail=detail,
                payload=payload,
                duration_ms=duration_ms,
            )
            self._replace_result(updated)
            return updated.as_track()

        current = self._collection_track_for_identity(identity)
        if current is None or not current.is_online:
            return None
        updated = self._enrich_track(
            current,
            state=state,
            detail=detail,
            payload=payload,
            duration_ms=duration_ms,
        )
        self.collection.update_runtime_track(updated)
        self.track_updated.emit(updated)
        return updated

    def update_remote_duration(self, stable_identity: str, duration_ms: int | None) -> Track | None:
        """Merge a media-layer duration without changing availability state."""

        return self.apply_remote_state(
            stable_identity,
            duration_ms=duration_ms,
        )

    def _enrich_online_track(
        self,
        track: OnlineTrack,
        *,
        state: str | None,
        detail: str,
        payload: dict | None,
        duration_ms: int | None,
    ) -> OnlineTrack:
        payload = payload if isinstance(payload, dict) else {}
        duration = self._enriched_duration(payload, duration_ms, track.duration_ms)
        artwork_url = artwork_url_from_payload(payload) or track.artwork_url
        artwork_key = self._payload_text(payload, "artworkKey", "artwork_key", "artwork") or track.artwork_key
        return replace(
            track,
            title=self._payload_text(payload, "title", "name") or track.title,
            artist=self._payload_text(payload, "artist", "singer") or track.artist,
            album=self._payload_text(payload, "album", "albumName") or track.album,
            duration_ms=duration,
            artwork_url=artwork_url,
            artwork_key=artwork_key,
            availability=str(state or track.availability).strip() or track.availability,
            availability_detail=str(detail or track.availability_detail or "").strip(),
        )

    def _enrich_track(
        self,
        track: Track,
        *,
        state: str | None,
        detail: str,
        payload: dict | None,
        duration_ms: int | None,
    ) -> Track:
        payload = payload if isinstance(payload, dict) else {}
        duration = self._enriched_duration(payload, duration_ms, track.duration_ms)
        availability = str(state or track.availability).strip() or track.availability
        identity = present_track_identity_values(
            track.title,
            track.artist,
            track.album,
            is_online=True,
            availability=availability,
            playback_detail=detail,
        )
        remote_payload = dict(track.remote_payload) if isinstance(track.remote_payload, dict) else {}
        for key, value in (
            ("title", self._payload_text(payload, "title", "name")),
            ("artist", self._payload_text(payload, "artist", "singer")),
            ("album", self._payload_text(payload, "album", "albumName")),
            ("artwork", self._payload_text(payload, "artwork", "artworkKey", "cover")),
        ):
            if value:
                remote_payload[key] = value
        if duration is not None:
            remote_payload["duration"] = duration
        artwork_url = artwork_url_from_payload(payload) or track.artwork_url
        if artwork_url:
            remote_payload["artwork"] = artwork_url
            remote_payload["artworkUrl"] = artwork_url
            remote_payload["artwork_url"] = artwork_url
        return replace(
            track,
            title=self._payload_text(payload, "title", "name") or track.title,
            artist=self._payload_text(payload, "artist", "singer") or track.artist,
            album=self._payload_text(payload, "album", "albumName") or track.album,
            duration_ms=duration,
            artwork_key=self._payload_text(payload, "artwork", "artworkKey", "cover") or track.artwork_key,
            artwork_url=artwork_url,
            availability=availability,
            availability_detail=str(detail or track.availability_detail or "").strip(),
            is_missing=identity.availability.is_confirmed_error,
            is_loading=identity.availability.is_resolving,
            remote_payload=remote_payload,
        )

    def _publish_track(self, track: Track) -> None:
        if self.collection.track_for_id(track.id) is not None:
            self.collection.update_runtime_track(track)
        self.track_updated.emit(track)

    def _online_result_for_identity(self, identity: str) -> OnlineTrack | None:
        return next(
            (
                track
                for track in (*self._results, *self._recommendation_results.values())
                if identity in {track.id, track.stable_identity, track.remote_id}
            ),
            None,
        )

    def _collection_track_for_identity(self, identity: str) -> Track | None:
        return next(
            (
                track
                for track in self.collection.tracks()
                if track.is_online
                and identity in {track.id, track.stable_identity, track.remote_identity}
            ),
            None,
        )

    @staticmethod
    def _payload_text(payload: dict, *keys: str) -> str:
        candidates = [payload]
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            candidates.insert(0, metadata)
        for candidate in candidates:
            for key in keys:
                value = candidate.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return ""

    def _enriched_duration(
        self,
        payload: dict,
        duration_ms: int | None,
        current: int | None,
    ) -> int | None:
        if duration_ms is not None:
            try:
                value = int(duration_ms)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
        raw = payload.get("durationMs") if "durationMs" in payload else payload.get("duration")
        if raw not in (None, ""):
            parsed = self._duration_ms(raw, None)
            return parsed if parsed and parsed > 0 else current
        return current

    @staticmethod
    def _can_request_play(track: OnlineTrack) -> bool:
        identity = present_track_identity_values(
            track.title,
            track.artist,
            track.album,
            is_online=True,
            availability=track.availability,
        )
        return (
            identity.availability.is_retryable
            or not identity.availability.is_confirmed_error
        )

    def request_metadata(self, track_id: str) -> bool:
        track = self._track_for_id(track_id)
        if track is None:
            return False
        if not self.is_formal:
            self.track_info_changed.emit(track)
            self.notification_changed.emit("在线歌曲信息已更新。")
            return True
        request_id = self.discovery.client.get_metadata(
            track.source_id,
            self._payload_for_track(track),
        )
        self._metadata_requests[request_id] = (
            self._formal_generation,
            track.id,
            track.source_id,
        )
        self.notification_changed.emit("正在读取在线歌曲信息…")
        return True

    def shutdown(self) -> None:
        self._closed = True
        self._recommendation_results.clear()
        if self.discovery is not None:
            self._metadata_requests.clear()

    def _connect_formal_services(self) -> None:
        search = self.discovery.search_service
        search.resultsChanged.connect(self._on_formal_results)
        search.sourceCatalogChanged.connect(self._on_formal_catalog)
        search.statusChanged.connect(self._on_formal_status)
        client = self.discovery.client
        client.metadataFinished.connect(self._on_metadata_finished)
        client.requestFailed.connect(self._on_formal_request_failed)
        artwork = self.discovery.artwork_service
        artwork.imageReady.connect(self._on_artwork_ready)
        artwork.failed.connect(self._on_artwork_failed)
        search.ensure_source_catalog()

    def _schedule_formal_search(self, query: str) -> int:
        service = self.discovery.search_service
        expected = int(getattr(service, "generation", self._formal_generation) or 0) + 1
        self._formal_generation = expected
        generation = service.schedule_search(query)
        self._formal_generation = int(generation or expected)
        return self._formal_generation

    def _on_formal_catalog(self, catalog, selected) -> None:
        if self._closed:
            return
        self._formal_catalog = [dict(item) for item in catalog if isinstance(item, dict)]
        self._formal_selected_source_ids = [str(item or "") for item in selected if item]
        self._sync_formal_sources()

    def _on_formal_status(self, message: str) -> None:
        if self._closed:
            return
        text = str(message or "")
        if self._state.phase == "idle" and not self._query:
            self._set_state("idle", text)
            return
        if any(
            marker in text
            for marker in (
                "没有已启用",
                "没有可搜索",
                "请至少选择",
                "读取自定义来源失败",
                "来源列表格式无效",
            )
        ):
            self._set_state("failed", text, self._state.progress)
            return
        if self._state.phase != "results":
            self._set_state("searching", text, self._state.progress)

    def _on_formal_results(self, generation: int, keyword: str, results: list, summary: dict) -> None:
        if self._closed:
            return
        if generation != self._formal_generation or str(keyword or "").strip() != self._query:
            return
        mapped = tuple(
            self._map_formal_track(dict(item), index)
            for index, item in enumerate(results if isinstance(results, list) else [])
            if isinstance(item, dict)
        )
        self._results = mapped
        self.search_results_changed.emit(self._results)
        self._sync_summary_sources(summary)
        final = bool(summary.get("final"))
        pending = int(summary.get("pendingCount") or 0)
        if not final or pending:
            self._set_state("searching", self._state.message, 50)
        elif mapped:
            self._add_history(self._query)
            errors = summary.get("errors") if isinstance(summary, dict) else {}
            warning = "部分来源未返回结果。" if errors else ""
            self._set_state("results", warning, 100)
            self._request_artwork(mapped)
            self.search_completed.emit(self._results)
        else:
            errors = summary.get("errors") if isinstance(summary, dict) else {}
            sources = summary.get("sources") if isinstance(summary, dict) else []
            source_states = [
                dict(item)
                for item in sources
                if isinstance(item, dict)
            ]
            unavailable = bool(errors) or bool(source_states) and all(
                str(item.get("status") or "").casefold()
                in {"failed", "error", "unavailable"}
                for item in source_states
            )
            phase = "failed" if unavailable else "empty"
            message = (
                "已启用来源均不可用，请管理来源后重试。"
                if unavailable
                else "在线搜索没有返回可展示的结果。"
            )
            self._set_state(phase, message, 100)
            self.search_completed.emit(self._results)

    def _on_formal_request_failed(self, request_id: int, action: str, message: str) -> None:
        pending = self._metadata_requests.pop(request_id, None)
        if pending is not None and action == "getMetadata":
            generation, _track_id, _source_id = pending
            if generation == self._formal_generation:
                self.notification_changed.emit(str(message or "在线歌曲信息读取失败。"))

    def _on_metadata_finished(self, request_id: int, source_id: str, metadata: dict) -> None:
        if self._closed:
            return
        pending = self._metadata_requests.pop(request_id, None)
        if pending is None:
            return
        generation, track_id, expected_source = pending
        if generation != self._formal_generation or str(source_id or "") != expected_source:
            return
        track = self._track_for_id(track_id)
        if track is None:
            return
        merged = dict(track.raw)
        if isinstance(metadata, dict):
            merged.update(metadata)
        updated = self._map_formal_track(merged, track.result_rank, existing=track)
        self._replace_result(updated)
        self.track_info_changed.emit(updated)
        self.notification_changed.emit("在线歌曲信息已更新。")

    def _request_artwork(self, tracks: tuple[OnlineTrack, ...]) -> None:
        requests = [
            (track.id, track.artwork_url)
            for track in tracks
            if track.artwork_url
        ][:32]
        if not requests:
            return
        self._artwork_generation = self.discovery.artwork_service.request_many(requests)

    def _on_artwork_ready(self, generation: int, track_key: str, data: bytes) -> None:
        if self._closed:
            return
        if generation != self._artwork_generation:
            return
        track = self._track_for_id(track_key)
        if track is None:
            return
        self._replace_result(replace(track, artwork_data=bytes(data), artwork_key=track.id))

    def _on_artwork_failed(self, generation: int, track_key: str, _message: str) -> None:
        if self._closed:
            return
        if generation != self._artwork_generation:
            return
        if self._track_for_id(track_key) is not None:
            self.notification_changed.emit("部分在线封面暂不可用。")

    def _sync_summary_sources(self, summary: dict) -> None:
        states = summary.get("sources") if isinstance(summary, dict) else []
        by_id = {
            str(item.get("sourceId") or ""): dict(item)
            for item in states
            if isinstance(item, dict)
        }
        self._sources = [
            replace(
                source,
                status=str(by_id.get(source.id, {}).get("status") or source.status),
                result_count=int(by_id.get(source.id, {}).get("resultCount") or source.result_count),
                last_error=str(by_id.get(source.id, {}).get("message") or source.last_error),
            )
            for source in self._sources
        ]
        self._sync_result_availability()
        self.source_state_changed.emit(self.sources())

    def _sync_formal_sources(self) -> None:
        selected = set(self._formal_selected_source_ids)
        values: list[OnlineSource] = []
        for item in self._formal_catalog:
            source_id = str(item.get("id") or "").strip()
            if not source_id:
                continue
            capabilities = item.get("capabilities") if isinstance(item.get("capabilities"), dict) else {}
            values.append(
                OnlineSource(
                    source_id,
                    str(item.get("name") or source_id),
                    source_id in selected,
                    "ready" if item.get("selectable") else "disabled",
                    0,
                    0,
                    str(item.get("reason") or ""),
                    bool(capabilities.get("playback")),
                    bool(capabilities.get("download")),
                    bool(capabilities.get("lyrics")),
                    "registered",
                )
            )
        self._sources = values
        self._sync_result_availability()
        self.source_state_changed.emit(self.sources())

    def _map_formal_track(
        self,
        raw: dict,
        rank: int,
        *,
        existing: OnlineTrack | None = None,
    ) -> OnlineTrack:
        existing = existing or self._existing_formal_result(raw)
        source_id = str(
            existing.source_id
            if existing is not None and existing.source_id
            else raw.get("sourceId")
            or raw.get("source_id")
            or ""
        ).strip()
        remote_id = str(
            existing.remote_id
            if existing is not None and existing.remote_id
            else raw.get("remote_id")
            or raw.get("remoteId")
            or raw.get("id")
            or raw.get("songmid")
            or ""
        ).strip()
        identity_payload = dict(raw)
        identity_payload["source_id"] = source_id
        identity_payload["remote_id"] = remote_id
        stable_id = (
            existing.stable_identity
            if existing is not None and existing.stable_identity
            else RemoteTrackStore.stable_id_for_track(identity_payload)
        )
        track_id = existing.id if existing is not None else stable_id
        source = self._source_for_id(source_id)
        current = self._track_for_id(track_id) or self._track_for_id(stable_id)
        collection_current = self._collection_track_for_identity(stable_id)
        artwork_source = existing or current or collection_current
        if existing is not None:
            availability = existing.availability
        else:
            explicit_state = str(
                raw.get("runtimeAvailability")
                or raw.get("runtime_availability")
                or ""
            ).strip()
            availability = explicit_state or (
                "not_resolved"
                if source is not None and source.enabled and source.supports_playback
                else "source_unavailable"
            )
        artwork_payload = dict(raw)
        artwork_url = artwork_url_from_payload(raw) or (
            str(getattr(artwork_source, "artwork_url", "") or "")
        )
        if artwork_url:
            artwork_payload.setdefault("artwork", artwork_url)
            artwork_payload.setdefault("artworkUrl", artwork_url)
            artwork_payload.setdefault("artwork_url", artwork_url)
        return OnlineTrack(
            id=track_id,
            source_id=source_id,
            source_name=str(raw.get("sourceName") or (source.name if source else source_id)),
            title=str(raw.get("title") or (existing.title if existing else "未知歌曲")),
            artist=str(raw.get("artist") or (existing.artist if existing else "未知艺术家")),
            album=str(raw.get("album") or (existing.album if existing else "未知专辑")),
            duration_ms=self._duration_ms(raw.get("duration") or raw.get("durationMs"), existing),
            artwork_key=str(
                raw.get("artwork")
                or raw.get("artworkKey")
                or getattr(artwork_source, "artwork_key", "")
                or stable_id
            ),
            quality=str(raw.get("quality") or raw.get("bitrate") or (existing.quality if existing else "标准")),
            stable_identity=stable_id,
            is_favorite=current.is_favorite if current is not None else (existing.is_favorite if existing else False),
            is_downloaded=bool(raw.get("downloaded") or (existing.is_downloaded if existing else False)),
            is_cached=bool(raw.get("cached") or (existing.is_cached if existing else False)),
            availability=availability,
            explicit=bool(raw.get("explicit") or raw.get("explicitContent")),
            result_rank=rank,
            artwork_url=artwork_url,
            remote_id=remote_id,
            raw=artwork_payload,
            artwork_data=bytes(
                getattr(artwork_source, "artwork_data", b"") or b""
            ),
            availability_detail=(
                str(raw.get("availabilityDetail") or raw.get("availability_detail") or "").strip()
                or (existing.availability_detail if existing is not None else "")
            ),
        )

    def _existing_formal_result(self, raw: dict) -> OnlineTrack | None:
        """Keep runtime state when an incremental source result is remapped."""

        if not isinstance(raw, dict):
            return None
        source_id = str(raw.get("sourceId") or raw.get("source_id") or "").strip()
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
        identities = {value for value in (remote_id, stable_id) if value}
        for track in self._results:
            if source_id and track.source_id != source_id:
                continue
            if identities & {track.id, track.stable_identity, track.remote_id}:
                return track
        return None

    @staticmethod
    def _duration_ms(value, existing: OnlineTrack | None = None) -> int | None:
        if value in (None, ""):
            return existing.duration_ms if existing is not None else None
        try:
            duration = max(0, int(float(value)))
        except (TypeError, ValueError):
            return existing.duration_ms if existing is not None else None
        return duration * 1000 if duration < 10000 else duration

    def _payload_for_track(self, track: OnlineTrack) -> dict:
        payload = dict(track.raw)
        payload.update(
            {
                "id": track.remote_id,
                "remote_id": track.remote_id,
                "source_id": track.source_id,
                "sourceId": track.source_id,
                "source_url": payload.get("source_url") or payload.get("sourceUrl") or "",
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "duration": track.duration_ms or 0,
                "artwork": track.artwork_url or payload.get("artwork") or "",
                "artworkUrl": track.artwork_url or payload.get("artworkUrl") or "",
                "artwork_url": track.artwork_url or payload.get("artwork_url") or "",
                "raw": dict(track.raw),
            }
        )
        return payload

    def _advance_search(self) -> None:
        generation = self._generation
        if self._state.phase != "searching":
            return
        self._search_step += 1
        if self._scenario == "slow" and self._search_step < 3:
            self._set_state("searching", "正在等待较慢的在线来源。", self._search_step * 30)
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
                        last_error="在线来源暂不可用" if source.enabled else "",
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
                    source, status="failed", result_count=0, last_error="在线来源响应超时"
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
        self._set_state("empty", "没有找到匹配的在线歌曲。", progress=100)
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
        albums = ("在线试听集", "Night Signals", "Source Archive", "A Long Online Album Title")
        values: list[OnlineTrack] = []
        for rank in range(16):
            raw_id = f"{source.id}-{rank:03d}"
            if self._scenario == "duplicate_results" and rank == 15:
                raw_id = f"{source.id}-000"
            title = titles[rank % len(titles)]
            if self._scenario == "long_text" and rank == 1:
                title = f"{title} - 这一段很长的在线搜索标题用于验证所有宽度下的省略行为"
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
                    availability="not_resolved" if source.supports_playback else "source_unavailable",
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
            if not ({track.id, track.stable_identity} & {updated.id, updated.stable_identity}):
                continue
            values = list(self._results)
            values[index] = updated
            self._results = tuple(values)
            self.result_updated.emit(updated)
            self._publish_track(updated.as_track())
            return
        for key, track in tuple(self._recommendation_results.items()):
            if not ({track.id, track.stable_identity, track.remote_id} & {
                updated.id,
                updated.stable_identity,
                updated.remote_id,
            }):
                continue
            self._recommendation_results.pop(key, None)
            self._recommendation_results[updated.id] = updated
            self.result_updated.emit(updated)
            self._publish_track(updated.as_track())
            return

    def _sync_result_availability(self) -> None:
        for track in (*self._results, *self._recommendation_results.values()):
            source = self._source_for_id(track.source_id)
            source_blocked = self._source_is_blocked(source)
            if source_blocked and track.availability not in {
                "resolve_failed",
                "resolve-failed",
                "permission_denied",
                "permission-denied",
                "playback_error",
                "playback-error",
            }:
                self._replace_result(
                    replace(
                        track,
                        availability="source_unavailable",
                        availability_detail=(
                            source.last_error
                            if source is not None and source.last_error
                            else "当前在线来源不可用。"
                        ),
                    )
                )
            elif not source_blocked and track.availability in {
                "source_unavailable",
                "source-unavailable",
            }:
                self._replace_result(
                    replace(track, availability="not_resolved", availability_detail="")
                )
        for track in self.collection.tracks():
            if not track.is_online:
                continue
            source = self._source_for_id(self._playback_source_id(track))
            if self._source_is_blocked(source) and track.availability not in {
                "resolve_failed",
                "resolve-failed",
                "permission_denied",
                "permission-denied",
                "playback_error",
                "playback-error",
            }:
                self.collection.update_runtime_track(
                    replace(
                        track,
                        availability="source_unavailable",
                        availability_detail=(
                            source.last_error
                            if source is not None and source.last_error
                            else "当前在线来源不可用。"
                        ),
                        is_missing=True,
                    )
                )
            elif not self._source_is_blocked(source) and track.availability in {
                "source_unavailable",
                "source-unavailable",
            }:
                self.collection.update_runtime_track(
                    replace(
                        track,
                        availability="not_resolved",
                        availability_detail="",
                        is_missing=False,
                    )
                )

    @staticmethod
    def _source_is_blocked(source: OnlineSource | None) -> bool:
        # A missing catalog entry is not proof of a capability denial. Keep
        # that track unresolved until the source registry reports a real state.
        return bool(
            source is not None
            and (
                not source.enabled
                or not source.supports_playback
                or source.status in {"failed", "disabled"}
            )
        )

    @staticmethod
    def _playback_source_id(track: Track) -> str:
        payload = track.remote_payload if isinstance(track.remote_payload, dict) else {}
        override = payload.get("playback_source")
        if isinstance(override, dict):
            return str(
                override.get("source_id")
                or override.get("sourceId")
                or track.source_id
            ).strip()
        return str(track.source_id or "").strip()

    def _track_for_id(self, track_id: str) -> OnlineTrack | None:
        normalized = str(track_id or "")
        return next(
            (
                track
                for track in (*self._results, *self._recommendation_results.values())
                if normalized in {track.id, track.stable_identity, track.remote_id}
            ),
            None,
        )

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
            generation=self._formal_generation if self.is_formal else self._generation,
        )
        self.state_changed.emit(self._state)
        self.search_progress_changed.emit(self._state.progress)

    @staticmethod
    def _default_sources() -> list[OnlineSource]:
        return [
            OnlineSource("catalog", "North Catalog", True, "ready", 82, 0, "", True, True, True, "catalog"),
            OnlineSource("archive", "Archive Index", True, "ready", 126, 0, "", True, False, True, "archive"),
            OnlineSource("radio", "Radio Public", True, "ready", 178, 0, "", True, True, False, "radio"),
            OnlineSource("indie", "Indie Shelf", True, "ready", 94, 0, "", True, True, True, "catalog"),
            OnlineSource("community", "Community Index", True, "ready", 214, 0, "", False, False, False, "index"),
            OnlineSource("public", "Public Collection", True, "ready", 156, 0, "", True, True, True, "archive"),
        ]
