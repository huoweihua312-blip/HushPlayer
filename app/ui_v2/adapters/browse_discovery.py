"""Shared Browse projections and playlist-aware online recommendations."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import Track

if TYPE_CHECKING:
    from app.ui_v2.adapters.online_adapter import OnlineAdapter


@dataclass(frozen=True, slots=True)
class BrowseDiscoverySnapshot:
    """One consistent data snapshot for all Browse sections."""

    recent_added: tuple[Track, ...]
    recommended: tuple[Track, ...]
    recent_played: tuple[Track, ...]
    recommendation_reason: str = ""
    online_status: str = ""


class BrowseDiscoveryAdapter(QObject):
    """Project saved library state and optional online recommendations.

    This adapter never persists a recommendation by itself.  Online actions
    continue through ``OnlineAdapter`` and the existing discovery bridge.
    """

    snapshot_changed = Signal(object)
    status_changed = Signal(str)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        playlists: PlaylistAdapter,
        online: OnlineAdapter | None = None,
        *,
        search_service=None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self.playlists = playlists
        self.online = online
        discovery = getattr(online, "discovery", None)
        self._search_service = search_service or getattr(
            discovery, "recommendation_search_service", None
        )
        self._maximum = 5
        self._closed = False
        self._generation = 0
        self._search_generation = 0
        self._search_keyword = ""
        self._online_results: tuple[OnlineTrack, ...] = ()
        self._online_status = ""
        self._last_snapshot = BrowseDiscoverySnapshot((), (), ())
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(lambda: self.refresh())

        collection.tracks_changed.connect(self.schedule_refresh)
        collection.recent_changed.connect(self.schedule_refresh)
        playlists.playlists_changed.connect(lambda _items: self.schedule_refresh())
        playlists.playlist_changed.connect(lambda _playlist_id: self.schedule_refresh())
        if online is not None:
            online.remote_collection_changed.connect(self.schedule_refresh)
            online.track_updated.connect(lambda _track: self.schedule_refresh())
        if self._search_service is not None:
            self._search_service.resultsChanged.connect(self._on_online_results)
        self.refresh()

    @property
    def snapshot(self) -> BrowseDiscoverySnapshot:
        return self._last_snapshot

    @property
    def recommendation_reason(self) -> str:
        return self._last_snapshot.recommendation_reason

    @property
    def online_status(self) -> str:
        return self._online_status

    def set_maximum(self, maximum: int) -> None:
        value = max(1, int(maximum))
        if value == self._maximum:
            return
        self._maximum = value
        self.refresh(force_online=False)

    def schedule_refresh(self) -> None:
        if self._closed:
            return
        self._refresh_timer.start()

    def refresh(self, force_online: bool = False) -> None:
        if self._closed:
            return
        self._refresh_timer.stop()
        self._generation += 1
        tracks = self._visible_tracks()
        recent_added = self._take_distinct(
            sorted(tracks, key=lambda track: track.added_at, reverse=True),
            self._maximum,
        )
        recent_played = self._recent_tracks(tracks)
        saved_recommendations, reason, query = self._saved_recommendations(tracks)

        if self._search_service is None:
            if self.online is not None and not getattr(self.online, "is_formal", False):
                self._online_results = tuple(self.online.results())
            self._online_status = "在线歌曲可从在线搜索中收藏或加入歌单。"
        elif query:
            self._start_online_search(query, force=force_online)
        else:
            self._online_results = ()
            self._online_status = "先播放或加入歌曲后，推荐会更准确。"

        recommended = self._merge_recommendations(
            saved_recommendations,
            self._online_results,
        )
        self._publish(
            BrowseDiscoverySnapshot(
                recent_added=recent_added,
                recommended=recommended,
                recent_played=recent_played,
                recommendation_reason=reason,
                online_status=self._online_status,
            )
        )

    def refresh_online(self) -> None:
        """Force a fresh recommendation request for the current user seeds."""

        self.refresh(force_online=True)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._search_generation += 1
        self._refresh_timer.stop()
        if self._search_service is not None:
            self._search_service.schedule_search("")

    def _visible_tracks(self) -> tuple[Track, ...]:
        return tuple(
            track
            for track in self.collection.tracks()
            if not track.is_loading and (not track.is_missing or track.is_online)
        )

    def _saved_recommendations(
        self, tracks: tuple[Track, ...]
    ) -> tuple[tuple[Track, ...], str, str]:
        seed_tracks: list[Track] = []
        reason = "根据最近添加"
        first_playlist_name = ""
        for playlist in self.playlists.playlists():
            members = self.playlists.tracks_for_playlist(playlist.id)
            if not members:
                continue
            seed_tracks.extend(members[:8])
            if not first_playlist_name:
                first_playlist_name = str(playlist.name or "").strip()
        if first_playlist_name:
            reason = f"来自歌单：{first_playlist_name}"

        recent_ids = {
            entry.track_id: index
            for index, entry in enumerate(self.collection.recent_entries())
        }
        seed_tracks.extend(
            self.collection.track_for_id(track_id)
            for track_id in recent_ids
            if self.collection.track_for_id(track_id) is not None
        )
        seed_tracks.extend(track for track in tracks if track.is_favorite)
        seed_tracks = [track for track in seed_tracks if track is not None]

        artist_counts = Counter(
            self._normalize(track.artist) for track in seed_tracks if self._normalize(track.artist)
        )
        album_counts = Counter(
            self._normalize(track.album) for track in seed_tracks if self._normalize(track.album)
        )
        seed_ids = {track.stable_id for track in seed_tracks}
        visible_by_stable = {track.stable_id: track for track in tracks}
        recent_rank = {
            visible_by_stable[track.stable_id].stable_id: index
            for index, track in enumerate(
                track for track in tracks if track.id in recent_ids
            )
        }

        def score(track: Track) -> tuple[int, int, bytes, str]:
            artist = artist_counts.get(self._normalize(track.artist), 0)
            album = album_counts.get(self._normalize(track.album), 0)
            recent = max(0, 6 - recent_rank.get(track.stable_id, 99))
            favorite = 3 if track.is_favorite else 0
            seed_penalty = -2 if track.stable_id in seed_ids else 0
            value = artist * 6 + album * 3 + recent + favorite + seed_penalty
            added = datetime.max - track.added_at
            tie = hashlib.sha256(f"browse:{track.stable_id}".encode("utf-8")).digest()
            return (-value, added, tie, track.stable_id)

        ranked = tuple(sorted(tracks, key=score))
        query = self._recommendation_query(seed_tracks or list(tracks))
        if not query:
            query = self._recent_online_query()
        return self._take_distinct(ranked, self._maximum), reason, query

    def _recent_tracks(self, tracks: tuple[Track, ...]) -> tuple[Track, ...]:
        by_id = {track.id: track for track in tracks}
        recent = tuple(
            by_id[entry.track_id]
            for entry in self.collection.recent_entries()
            if entry.track_id in by_id
        )
        if recent:
            return self._take_distinct(recent, self._maximum)
        fallback = sorted(
            tracks,
            key=lambda track: (
                hashlib.sha256(f"browse:recent:{track.stable_id}".encode("utf-8")).digest(),
                track.id,
            ),
        )
        return self._take_distinct(fallback, self._maximum)

    def _start_online_search(self, query: str, *, force: bool) -> None:
        if (
            not force
            and self._search_keyword == query
            and self._online_results
        ):
            self._online_status = "在线推荐已缓存。"
            return
        primary = getattr(getattr(self.online, "discovery", None), "search_service", None)
        if primary is not None:
            selected = primary.selected_source_ids
            if primary.source_catalog_loaded or selected:
                self._search_service.set_selected_source_ids(selected, restart=False)
        self._search_keyword = query
        self._online_results = ()
        self._online_status = "正在从已启用在线来源查找推荐…"
        expected_generation = int(getattr(self._search_service, "generation", 0) or 0) + 1
        self._search_generation = expected_generation
        actual_generation = self._search_service.schedule_search(query)
        self._search_generation = int(actual_generation or expected_generation)
        if self.online is not None:
            self.online.clear_recommendation_tracks()

    def _on_online_results(
        self,
        generation: int,
        keyword: str,
        results: list,
        summary: dict,
    ) -> None:
        if self._closed:
            return
        if int(generation) != self._search_generation or str(keyword or "").strip() != self._search_keyword:
            return
        mapped: list[OnlineTrack] = []
        if self.online is not None:
            for index, raw in enumerate(results if isinstance(results, list) else []):
                if not isinstance(raw, dict):
                    continue
                track = self.online.map_recommendation_track(raw, index)
                if track is not None:
                    mapped.append(track)
            self.online.register_recommendation_tracks(mapped)
        self._online_results = self._dedupe_online(mapped)
        final = bool(summary.get("final")) if isinstance(summary, dict) else False
        if final:
            errors = summary.get("errors") if isinstance(summary, dict) else {}
            if self._online_results and errors:
                self._online_status = "在线推荐已更新，部分来源未返回结果。"
            elif self._online_results:
                self._online_status = "在线推荐已更新。"
            else:
                self._online_status = "暂时没有匹配的在线推荐。"
        else:
            self._online_status = "正在从已启用在线来源查找推荐…"
        self._publish_current()

    def _publish_current(self) -> None:
        tracks = self._visible_tracks()
        recent_added = self._take_distinct(
            sorted(tracks, key=lambda track: track.added_at, reverse=True),
            self._maximum,
        )
        recent_played = self._recent_tracks(tracks)
        saved, reason, _query = self._saved_recommendations(tracks)
        recommended = self._merge_recommendations(saved, self._online_results)
        self._publish(
            BrowseDiscoverySnapshot(
                recent_added,
                recommended,
                recent_played,
                reason,
                self._online_status,
            )
        )

    def _publish(self, snapshot: BrowseDiscoverySnapshot) -> None:
        self._last_snapshot = snapshot
        self.status_changed.emit(snapshot.online_status)
        self.snapshot_changed.emit(snapshot)

    def _merge_recommendations(
        self,
        saved: tuple[Track, ...],
        online: tuple[OnlineTrack, ...],
    ) -> tuple[Track, ...]:
        """Keep visible room for discovery beyond already-saved tracks."""

        saved_tracks = self._take_distinct(saved, self._maximum)
        online_tracks = self._take_distinct(
            (item.as_track() for item in online),
            self._maximum,
        )
        if not online_tracks:
            return saved_tracks

        online_slots = min(
            len(online_tracks),
            max(1, (self._maximum + 1) // 2),
        )
        saved_slots = max(0, self._maximum - online_slots)
        return self._take_distinct(
            (
                *saved_tracks[:saved_slots],
                *online_tracks[:online_slots],
                *saved_tracks[saved_slots:],
                *online_tracks[online_slots:],
            ),
            self._maximum,
        )

    def _recent_online_query(self) -> str:
        """Reuse the user's online intent when no local seed exists."""

        if self.online is None:
            return ""
        current_query = str(getattr(self.online, "query", "") or "").strip()
        if len(current_query) >= 2:
            return current_query
        try:
            history = self.online.history()
        except Exception:
            history = ()
        for item in history if isinstance(history, (tuple, list)) else ():
            query = str(getattr(item, "query", "") or "").strip()
            if len(query) >= 2:
                return query
        return ""

    @staticmethod
    def _recommendation_query(tracks: list[Track]) -> str:
        artists = [BrowseDiscoveryAdapter._normalize(track.artist) for track in tracks]
        for artist in artists:
            if len(artist) >= 2:
                return artist
        for track in tracks:
            title = str(track.title or "").strip()
            if len(title) >= 2:
                return title
        return ""

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value or "").casefold().split())

    @staticmethod
    def _take_distinct(tracks, maximum: int) -> tuple[Track, ...]:
        selected: list[Track] = []
        stable_ids: set[str] = set()
        for track in tracks:
            if track is None or track.stable_id in stable_ids:
                continue
            selected.append(track)
            stable_ids.add(track.stable_id)
            if len(selected) >= maximum:
                break
        return tuple(selected)

    @staticmethod
    def _dedupe_online(tracks: list[OnlineTrack]) -> tuple[OnlineTrack, ...]:
        values: list[OnlineTrack] = []
        identities: set[str] = set()
        for track in tracks:
            identity = track.stable_identity or track.id
            if identity in identities:
                continue
            identities.add(identity)
            values.append(track)
        return tuple(values)
