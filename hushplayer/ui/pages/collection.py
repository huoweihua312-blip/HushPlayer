"""Favorites, recently played and playlist pages."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMenu

from ...model.track import Track
from ..context import ctx
from ..dialogs import ask_text, confirm
from ..widgets.common import IconButton, TextButton
from .trackpage import TrackListPage
from ..widgets.menu import themed_menu


class FavoritesPage(TrackListPage):
    route = "favorites"
    title = "我喜欢"
    sortable = True

    def load_tracks(self) -> list[Track]:
        tracks = ctx().library.favorites()
        if self._sort_key:
            return _sorted(tracks, self._sort_key, self._sort_asc)
        return tracks

    def context_label(self) -> str:
        return "我喜欢"

    def empty_text(self) -> tuple[str, str]:
        return ("还没有喜欢的歌曲", "在歌曲上点击心形图标，或使用右键菜单添加")

    def _playlist_id(self) -> int | None:
        return ctx().library.favorites_playlist_id() or None

    def refresh_theme(self) -> None:
        super().refresh_theme()


class RecentPage(TrackListPage):
    route = "recent"
    title = "最近播放"

    def load_tracks(self) -> list[Track]:
        tracks = ctx().library.recent(300)
        if self._sort_key:
            return _sorted(tracks, self._sort_key, self._sort_asc)
        return tracks

    def context_label(self) -> str:
        return "最近播放"

    def empty_text(self) -> tuple[str, str]:
        return ("还没有播放记录", "开始播放歌曲后，最近播放会显示在这里")

    def _update_header(self) -> None:
        self.header.set_subtitle(f"{len(self._tracks)} 首歌曲" if self._tracks else "按最近播放时间排序")

    def build_actions(self, layout: QHBoxLayout) -> None:
        play = TextButton("全部播放", icon_name="play")
        play.clicked.connect(lambda: self._play(self._tracks, 0))
        layout.addWidget(play)
        shuffle = TextButton("随机播放", icon_name="shuffle")
        shuffle.clicked.connect(self._play_shuffled)
        layout.addWidget(shuffle)

    def _play_shuffled(self) -> None:
        if not self._tracks:
            return
        player = ctx().player
        was_shuffle = player.shuffle
        player.set_shuffle(True)
        self._play(self._tracks, 0)
        if not was_shuffle:
            pass


class PlaylistPage(TrackListPage):
    route = "playlist"
    title = "歌单"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._playlist_id_value = 0
        self._playlist_name = ""
        self.list.set_drag_reorder(True)
        self.list.reordered.connect(self._on_reorder)

    def set_playlist(self, playlist_id: int) -> None:
        self._playlist_id_value = int(playlist_id)
        playlist = ctx().library.playlist(self._playlist_id_value)
        self._playlist_name = playlist.name if playlist is not None else "歌单"
        self.header.set_title(self._playlist_name)
        self.reload()

    def on_show(self, payload: object = None) -> None:
        if isinstance(payload, int):
            self.set_playlist(payload)
        elif isinstance(payload, str) and payload.isdigit():
            self.set_playlist(int(payload))
        else:
            self.reload()

    def load_tracks(self) -> list[Track]:
        if not self._playlist_id_value:
            return []
        return ctx().library.playlist_tracks(self._playlist_id_value)

    def context_label(self) -> str:
        return self._playlist_name or "歌单"

    def _playlist_id(self) -> int | None:
        return self._playlist_id_value or None

    def empty_text(self) -> tuple[str, str]:
        return ("歌单还是空的", "从歌曲列表或搜索结果中，右键添加歌曲到这个歌单")

    def _update_header(self) -> None:
        total = sum(track.duration_ms for track in self._tracks)
        from ...model.track import format_duration

        if self._tracks:
            self.header.set_subtitle(
                f"{len(self._tracks)} 首歌曲 · {format_duration(total)}"
            )
        else:
            self.header.set_subtitle("歌单")

    def build_actions(self, layout: QHBoxLayout) -> None:
        play = TextButton("播放", icon_name="play")
        play.clicked.connect(lambda: self._play(self._tracks, 0))
        layout.addWidget(play)
        shuffle = TextButton("随机播放", icon_name="shuffle")
        shuffle.clicked.connect(self._play_random)
        layout.addWidget(shuffle)
        more = IconButton("more", size=32, icon_size=16, tooltip="更多")
        more.clicked.connect(self._more_menu)
        layout.addWidget(more)

    def _play_random(self) -> None:
        if not self._tracks:
            return
        ctx().player.set_shuffle(True)
        self._play(self._tracks, 0)

    def _more_menu(self) -> None:
        menu = themed_menu(self)
        menu.addAction("重命名歌单…", self._rename)
        menu.addAction("更改封面…", self._change_cover)
        menu.addSeparator()
        menu.addAction("删除歌单", self._delete)
        button = self.sender()
        if button is not None:
            menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _rename(self) -> None:
        name, ok = ask_text(self, "重命名歌单", "歌单名称", text=self._playlist_name)
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if ctx().library.rename_playlist(self._playlist_id_value, name):
            self._playlist_name = name
            self.header.set_title(name)
            ctx().window and ctx().window.refresh_playlists()

    def _change_cover(self) -> None:
        path, _ = __import__("PySide6.QtWidgets", fromlist=["QFileDialog"]).QFileDialog.getOpenFileName(
            self, "选择歌单封面", "", "图片 (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        try:
            from pathlib import Path

            data = Path(path).read_bytes()
            stored = ctx().library.store_cover_bytes(data, Path(path).suffix)
            repository = ctx().library.playlists
            repository.set_cover(self._playlist_id_value, stored)
            self.reload()
            ctx().window and ctx().window.refresh_playlists()
        except Exception as exc:  # noqa: BLE001
            ctx().window and ctx().window.toast(f"设置封面失败：{exc}", "error")

    def _delete(self) -> None:
        if not confirm(
            self,
            "删除歌单",
            f"确定要删除歌单「{self._playlist_name}」吗？\n歌单中的歌曲不会被删除。",
        ):
            return
        ctx().library.delete_playlist(self._playlist_id_value)
        self._playlist_id_value = 0
        if ctx().window is not None:
            ctx().window.refresh_playlists()
            ctx().window.navigate("songs")
            ctx().window.toast("歌单已删除", "info")

    def _on_reorder(self, from_row: int, to_row: int) -> None:
        if not self._playlist_id_value:
            return
        ctx().library.move_playlist_item(self._playlist_id_value, from_row, to_row)
        self.reload()


def _sorted(tracks: list[Track], key: str, ascending: bool) -> list[Track]:
    getters = {
        "title": lambda t: (t.title or "").casefold(),
        "artist": lambda t: (t.artist or "").casefold(),
        "album": lambda t: (t.album or "").casefold(),
        "duration": lambda t: t.duration_ms,
        "added": lambda t: t.added_at,
        "year": lambda t: t.year or 0,
    }
    getter = getters.get(key)
    if getter is None:
        return tracks
    return sorted(tracks, key=getter, reverse=not ascending)
