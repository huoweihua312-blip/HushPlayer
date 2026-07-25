"""In-memory navigation and playlist state for the UI V2 shell."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.ui_v2.models.navigation_item import MockPlaylist, NavigationItem


class NavigationAdapter(QObject):
    """Owns route selection and mock playlists without persistent storage."""

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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._route = "library"
        self._current_playlist_id = ""
        self._playlists = [
            MockPlaylist("playlist-focus", "专注时刻"),
            MockPlaylist("playlist-night", "深夜电台与缓慢的城市灯光"),
            MockPlaylist("playlist-weekend", "周末收藏"),
        ]
        self._next_playlist_number = 1

    @property
    def route(self) -> str:
        return self._route

    @property
    def current_playlist_id(self) -> str:
        return self._current_playlist_id

    def items(self) -> tuple[NavigationItem, ...]:
        return self.MAIN_ITEMS

    def playlists(self) -> tuple[MockPlaylist, ...]:
        return tuple(self._playlists)

    def set_route(self, route_id: str) -> None:
        route = str(route_id or "library")
        playlist_id = route.removeprefix("playlist:") if route.startswith("playlist:") else ""
        if playlist_id and not any(item.id == playlist_id for item in self._playlists):
            route = "library"
            playlist_id = ""
        if route == self._route and playlist_id == self._current_playlist_id:
            return
        self._route = route
        self._current_playlist_id = playlist_id
        self.route_changed.emit(route)
        if playlist_id:
            self.current_playlist_changed.emit(playlist_id)

    def create_playlist(self, name: str = "") -> MockPlaylist:
        title = str(name or "").strip() or f"新建歌单 {self._next_playlist_number}"
        playlist = MockPlaylist(f"playlist-custom-{self._next_playlist_number}", title)
        self._next_playlist_number += 1
        self._playlists.append(playlist)
        self.playlists_changed.emit(self.playlists())
        return playlist

    def rename_playlist(self, playlist_id: str, name: str) -> bool:
        title = str(name or "").strip()
        if not title:
            return False
        for index, playlist in enumerate(self._playlists):
            if playlist.id == playlist_id:
                self._playlists[index] = MockPlaylist(playlist.id, title)
                self.playlists_changed.emit(self.playlists())
                return True
        return False

    def delete_playlist(self, playlist_id: str) -> bool:
        for index, playlist in enumerate(self._playlists):
            if playlist.id != playlist_id:
                continue
            del self._playlists[index]
            self.playlists_changed.emit(self.playlists())
            if self._current_playlist_id == playlist_id:
                self._current_playlist_id = ""
                self._route = "library"
                self.route_changed.emit("library")
            return True
        return False
