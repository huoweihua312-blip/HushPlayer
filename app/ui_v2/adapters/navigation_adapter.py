"""Route selection backed by the shared mock PlaylistAdapter source."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.navigation_item import NavigationItem
from app.ui_v2.models.playlist import Playlist


class NavigationAdapter(QObject):
    """Owns only route state; playlists are supplied by PlaylistAdapter."""

    route_changed = Signal(str)
    playlists_changed = Signal(object)
    current_playlist_changed = Signal(str)

    MAIN_ITEMS = (
        NavigationItem("library", "全部歌曲", "library", "主要导航"),
        NavigationItem("liked", "我喜欢", "favorite", "主要导航"),
        NavigationItem("recent", "最近播放", "recent", "主要导航"),
        NavigationItem("artists", "歌手", "artist", "音乐库"),
        NavigationItem("albums", "专辑", "album", "音乐库"),
        NavigationItem("online_search", "在线搜索", "search", "在线"),
        NavigationItem("lyrics", "歌词", "lyrics", "其他"),
        NavigationItem("settings", "设置", "settings", "其他"),
    )

    def __init__(
        self,
        playlists: PlaylistAdapter | None = None,
        parent: QObject | None = None,
        *,
        include_online: bool = True,
    ) -> None:
        super().__init__(parent)
        self._owned_playlists = playlists is None
        self.playlist_adapter = playlists or PlaylistAdapter(
            LibraryCollectionAdapter(), self
        )
        self._route = "library"
        self._current_playlist_id = ""
        self._include_online = bool(include_online)
        self.playlist_adapter.playlists_changed.connect(self._on_playlists_changed)

    @property
    def route(self) -> str:
        return self._route

    @property
    def current_playlist_id(self) -> str:
        return self._current_playlist_id

    def items(self) -> tuple[NavigationItem, ...]:
        if self._include_online:
            return self.MAIN_ITEMS
        return tuple(item for item in self.MAIN_ITEMS if item.route_id != "online_search")

    def playlists(self) -> tuple[Playlist, ...]:
        return self.playlist_adapter.playlists()

    def set_route(self, route_id: str) -> None:
        route = str(route_id or "library")
        playlist_id = route.removeprefix("playlist:") if route.startswith("playlist:") else ""
        if playlist_id and self.playlist_adapter.playlist_for_id(playlist_id) is None:
            route = "library"
            playlist_id = ""
        if route == self._route and playlist_id == self._current_playlist_id:
            return
        self._route = route
        self._current_playlist_id = playlist_id
        self.route_changed.emit(route)
        if playlist_id:
            self.current_playlist_changed.emit(playlist_id)

    def create_playlist(self, name: str = "") -> Playlist:
        return self.playlist_adapter.create_playlist(name)

    def rename_playlist(self, playlist_id: str, name: str) -> bool:
        return self.playlist_adapter.rename_playlist(playlist_id, name)

    def delete_playlist(self, playlist_id: str) -> bool:
        return self.playlist_adapter.delete_playlist(playlist_id)

    def _on_playlists_changed(self, playlists: object) -> None:
        self.playlists_changed.emit(playlists)
        if self._current_playlist_id and self.playlist_adapter.playlist_for_id(
            self._current_playlist_id
        ) is None:
            self._current_playlist_id = ""
            self._route = "library"
            self.route_changed.emit("library")
