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
    history_changed = Signal(bool, bool)
    playlists_changed = Signal(object)
    current_playlist_changed = Signal(str)

    MAIN_ITEMS = (
        NavigationItem("library", "音乐库", "library", "音乐库"),
        NavigationItem("pending_imports", "待导入", "playlist", "音乐库"),
        NavigationItem("browse", "浏览", "browse", "音乐库"),
        NavigationItem("liked", "我喜欢", "favorite", "歌单"),
        NavigationItem("recent", "最近播放", "recent", "低频"),
        NavigationItem("artists", "歌手", "artist", "低频"),
        NavigationItem("albums", "专辑", "album", "低频"),
        NavigationItem("online_search", "在线搜索", "search", "低频"),
        NavigationItem("lyrics", "歌词", "lyrics", "低频"),
        NavigationItem("settings", "设置", "settings", "其他"),
    )

    def __init__(
        self,
        playlists: PlaylistAdapter | None = None,
        parent: QObject | None = None,
        *,
        include_online: bool = True,
        include_pending: bool = False,
    ) -> None:
        super().__init__(parent)
        self._owned_playlists = playlists is None
        self.playlist_adapter = playlists or PlaylistAdapter(
            LibraryCollectionAdapter(), self
        )
        self._route = "browse"
        self._current_playlist_id = ""
        self._include_online = bool(include_online)
        self._include_pending = bool(include_pending)
        self._back_stack: list[str] = []
        self._forward_stack: list[str] = []
        self.playlist_adapter.playlists_changed.connect(self._on_playlists_changed)

    @property
    def route(self) -> str:
        return self._route

    @property
    def current_playlist_id(self) -> str:
        return self._current_playlist_id

    @property
    def can_go_back(self) -> bool:
        return bool(self._back_stack)

    @property
    def can_go_forward(self) -> bool:
        return bool(self._forward_stack)

    def items(self) -> tuple[NavigationItem, ...]:
        items = self.MAIN_ITEMS
        if not self._include_online:
            items = tuple(item for item in items if item.route_id != "online_search")
        if not self._include_pending:
            items = tuple(item for item in items if item.route_id != "pending_imports")
        return items

    def playlists(self) -> tuple[Playlist, ...]:
        return self.playlist_adapter.playlists()

    def set_route(self, route_id: str, *, record_history: bool = True) -> None:
        route = str(route_id or "library")
        playlist_id = route.removeprefix("playlist:") if route.startswith("playlist:") else ""
        if playlist_id and self.playlist_adapter.playlist_for_id(playlist_id) is None:
            route = "library"
            playlist_id = ""
        if route == self._route and playlist_id == self._current_playlist_id:
            return
        previous_route = self._route
        if record_history and self._is_history_route(previous_route) and self._is_history_route(route):
            if not self._back_stack or self._back_stack[-1] != previous_route:
                self._back_stack.append(previous_route)
            self._forward_stack.clear()
        self._route = route
        self._current_playlist_id = playlist_id
        self.route_changed.emit(route)
        if playlist_id:
            self.current_playlist_changed.emit(playlist_id)
        self._emit_history_changed()

    def go_back(self) -> None:
        if not self._back_stack:
            return
        target = self._back_stack.pop()
        current = self._route
        if self._is_history_route(current):
            self._forward_stack.append(current)
        self.set_route(target, record_history=False)

    def go_forward(self) -> None:
        if not self._forward_stack:
            return
        target = self._forward_stack.pop()
        current = self._route
        if self._is_history_route(current):
            self._back_stack.append(current)
        self.set_route(target, record_history=False)

    def create_playlist(self, name: str = "") -> Playlist | None:
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
            self.set_route("library", record_history=False)

    @staticmethod
    def _is_history_route(route: str) -> bool:
        normalized = str(route or "")
        return normalized != "settings" and not normalized.startswith("immersive")

    def _emit_history_changed(self) -> None:
        self.history_changed.emit(self.can_go_back, self.can_go_forward)
