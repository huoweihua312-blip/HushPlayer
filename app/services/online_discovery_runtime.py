"""One owned bundle of services for the V2 online discovery surface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject

from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository
from app.services.online_artwork_service import OnlineArtworkService
from app.services.online_source_client import OnlineSourceClient
from app.services.online_discovery_bridge import OnlineDiscoveryBridge
from app.services.remote_track_store import RemoteTrackStore
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
            frozen=paths.frozen,
        )
        if self.client.parent() is None:
            self.client.setParent(self)
        self.search_service = search_service or UnifiedSearchService(self.client, self)
        if self.search_service.parent() is None:
            self.search_service.setParent(self)
        self.artwork_service = artwork_service or OnlineArtworkService(
            Path(paths.cache_dir) / "covers",
            self,
        )
        if self.artwork_service.parent() is None:
            self.artwork_service.setParent(self)
        self.bridge = bridge or OnlineDiscoveryBridge(repository, remote_tracks, self)
        if self.bridge.parent() is None:
            self.bridge.setParent(self)
        self._closed = False

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.search_service.shutdown()
        self.artwork_service.cancel()
        self.client.stop()
