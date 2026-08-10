"""One owned bundle of services for the V2 online discovery surface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject

from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository
from app.services.lyrics_cache import LyricsCache
from app.models.media_item import MediaItem
from app.services.online_artwork_service import OnlineArtworkService
from app.services.online_audio_cache import OnlineAudioCacheService
from app.services.online_lyrics_service import OnlineLyricsService
from app.services.online_media_resolver import OnlineMediaResolver
from app.services.online_source_importer import OnlineSourceImporter
from app.services.online_source_client import OnlineSourceClient
from app.services.online_discovery_bridge import OnlineDiscoveryBridge
from app.services.remote_track_store import RemoteTrackStore
from app.services.source_registry import SourceRegistryManager
from app.services.unified_search_service import UnifiedSearchService


class OnlineDiscoveryRuntime(QObject):
    """Own the formal online discovery services for one V2 main window."""

    def __init__(
        self,
        paths: AppPaths,
        repository: LibraryRepository,
        remote_tracks: RemoteTrackStore,
        parent: QObject | None = None,
        *,
        client: OnlineSourceClient | None = None,
        search_service: UnifiedSearchService | None = None,
        artwork_service: OnlineArtworkService | None = None,
        bridge: OnlineDiscoveryBridge | None = None,
    ) -> None:
        super().__init__(parent)
        self.paths = paths
        self.repository = repository
        self.remote_tracks = remote_tracks
        self.client = client or OnlineSourceClient(
            paths.bundled_resource_dir,
            self,
            runtime_dir=paths.bundled_source_runtime_dir,
            registry_path=paths.source_registry_file,
            user_sources_dir=paths.user_sources_dir,
            bundled_node_executable=paths.bundled_node_executable,
            runtime_dependencies_dir=paths.source_runtime_dependencies_dir,
            frozen=paths.frozen,
        )
        if self.client.parent() is None:
            self.client.setParent(self)
        self.search_service = search_service or UnifiedSearchService(self.client, self)
        if self.search_service.parent() is None:
            self.search_service.setParent(self)
        # Browse recommendations use the same source client and runner but a
        # separate generation coordinator, so they cannot overwrite the
        # user's active Online Search query.
        self.recommendation_search_service = UnifiedSearchService(self.client, self)
        self.playback_resolver = OnlineMediaResolver(
            self.client,
            self,
            source_catalog_provider=lambda: self.search_service.source_catalog,
            source_catalog_loaded=lambda: self.search_service.source_catalog_loaded,
        )
        self.lyrics_service = OnlineLyricsService(
            self.client,
            LyricsCache(Path(paths.cache_dir) / "lyrics" / "online_lyrics.json"),
            self,
        )
        self.artwork_service = artwork_service or OnlineArtworkService(
            Path(paths.cache_dir) / "covers",
            self,
        )
        if self.artwork_service.parent() is None:
            self.artwork_service.setParent(self)
        self.source_registry = SourceRegistryManager(
            paths.bundled_resource_dir,
            runtime_dir=paths.source_runtime_data_dir,
            user_sources_dir=paths.user_sources_dir,
            bundled_runtime_dir=paths.bundled_source_runtime_dir,
        )
        self.online_audio_cache = OnlineAudioCacheService(
            Path(paths.cache_dir) / "audio",
            self,
        )
        self.source_importer = OnlineSourceImporter(
            self.source_registry,
            self.client,
            self,
        )
        self.bridge = bridge or OnlineDiscoveryBridge(repository, remote_tracks, self)
        if self.bridge.parent() is None:
            self.bridge.setParent(self)
        self._closed = False

    def online_source_allows_audio_cache(self, media_item: MediaItem) -> bool:
        """Keep cache downloads behind the same source policy as the legacy app."""

        if not isinstance(media_item, MediaItem) or media_item.media_type != "online":
            return False
        try:
            source = self.source_registry.get_source(media_item.source_id) or {}
        except Exception:
            return False
        policy = str(source.get("contentPolicy") or "unknown").strip().casefold()
        capabilities = source.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        return bool(
            source.get("enabled") is not False
            and policy in {"open", "user_owned"}
            and (
                capabilities.get("playback") is True
                or capabilities.get("download") is True
            )
        )

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.lyrics_service.cancel()
        self.source_importer.shutdown()
        self.playback_resolver.shutdown()
        self.recommendation_search_service.shutdown()
        self.search_service.shutdown()
        self.artwork_service.cancel()
        self.online_audio_cache.shutdown()
        self.client.stop()
