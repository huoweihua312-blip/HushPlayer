from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMenu, QMessageBox

from app.models.media_item import MediaItem
from app.ui.track_details_panel import TrackDetailsDialog


class MediaInteractionController(QObject):
    """Shared local/online collection, details and context-menu actions."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window

    def get_local_state(self, value: dict) -> dict:
        item = MediaItem.from_mapping(value)
        path = self.window.normalize_song_path(item.local_file_path)
        current_playlist_id = ""
        if self.window.current_library_view == "liked":
            current_playlist_id = "liked"
        elif self.window.current_library_view.startswith("playlist:"):
            current_playlist_id = self.window.current_library_view.split("playlist:", 1)[1]
        return {
            "liked": self.window.is_song_liked(path),
            "inCurrentPlaylist": bool(
                current_playlist_id
                and path in self.window.get_playlist_song_paths(current_playlist_id)
            ),
        }

    def like_local(self, value: dict) -> None:
        self._set_local_liked(value, True)

    def unlike_local(self, value: dict) -> None:
        self._set_local_liked(value, False)

    def _set_local_liked(self, value: dict, liked: bool) -> None:
        item = MediaItem.from_mapping(value)
        path = self.window.normalize_song_path(item.local_file_path)
        if not path:
            return
        changed = (
            self.window.add_local_path_to_playlist(path, "liked")
            if liked
            else self.window.remove_local_path_from_playlist(path, "liked")
        )
        if not changed:
            return
        self.window.refresh_playlist_membership_views()
        self.window.search_page.set_local_results(
            self.window.search_input.text(),
            self.window.collect_local_search_results(self.window.search_input.text()),
        )

    def add_local_to_playlist(self, value: dict, playlist_id: str) -> None:
        item = MediaItem.from_mapping(value)
        path = self.window.normalize_song_path(item.local_file_path)
        if not path or playlist_id not in self.window.playlists:
            return
        if self.window.add_local_path_to_playlist(path, playlist_id):
            self.window.refresh_playlist_membership_views()

    def remove_local_from_current_playlist(self, value: dict) -> None:
        item = MediaItem.from_mapping(value)
        path = self.window.normalize_song_path(item.local_file_path)
        if self.window.current_library_view == "liked":
            playlist_id = "liked"
        elif self.window.current_library_view.startswith("playlist:"):
            playlist_id = self.window.current_library_view.split("playlist:", 1)[1]
        else:
            return
        if self.window.remove_local_path_from_playlist(path, playlist_id):
            self.window.refresh_playlist_membership_views()

    def open_local_folder(self, value: dict) -> None:
        item = MediaItem.from_mapping(value)
        path = Path(item.local_file_path)
        if not path.is_file():
            QMessageBox.information(self.window, "打开文件位置", "本地音乐文件已经不存在。")
            return
        try:
            os.startfile(str(path.parent))
        except Exception as error:
            QMessageBox.warning(self.window, "打开失败", str(error))

    def remove_local(self, value: dict) -> None:
        item = MediaItem.from_mapping(value)
        list_item = self.window.find_song_item_by_path(item.local_file_path)
        if list_item is None:
            return
        self.window.song_list.clearSelection()
        self.window.song_list.setCurrentItem(list_item)
        list_item.setSelected(True)
        self.window.remove_selected_songs_from_library()

    def show_info(self, value: dict) -> None:
        item = MediaItem.from_mapping(value)
        collection_state = (
            self.window.get_online_track_collection_state(item.to_dict())
            if item.media_type == "online"
            else self.get_local_state(item.to_dict())
        )
        stats = (
            self.window.song_stats.get(
                self.window.normalize_song_path(item.local_file_path), {}
            )
            if item.media_type == "local"
            else {}
        )
        dialog = TrackDetailsDialog(
            item,
            stats,
            self.window,
            collection_state=collection_state,
        )
        self.window.prepare_dark_dialog(dialog)
        dialog.exec()

    def show_context_menu(self, value: dict, global_position) -> None:
        item = MediaItem.from_mapping(value)
        menu = QMenu(self.window)
        playable = item.is_local_available or (
            item.can_play and item.availability == "available"
        )
        play_action = menu.addAction("播放")
        play_action.setEnabled(playable)
        play_action.triggered.connect(
            lambda checked=False, track=item.to_dict(): self.window.play_media_item(track)
        )
        next_action = menu.addAction("下一首播放")
        next_action.setEnabled(playable)
        next_action.triggered.connect(
            lambda checked=False, track=item.to_dict(): self.window.queue_media_item_next(track)
        )
        menu.addSeparator()
        if item.media_type == "online":
            state = self.window.get_online_track_collection_state(item.to_dict())
            if state.get("liked"):
                like_action = menu.addAction("取消收藏")
                like_action.triggered.connect(
                    lambda checked=False, track=item.to_dict(): self.window.unlike_online_track(track)
                )
            else:
                like_action = menu.addAction("添加到我喜欢")
                like_action.triggered.connect(
                    lambda checked=False, track=item.to_dict(): self.window.like_online_track(track)
                )
        else:
            state = self.get_local_state(item.to_dict())
            if state.get("liked"):
                like_action = menu.addAction("取消收藏")
                like_action.triggered.connect(
                    lambda checked=False, track=item.to_dict(): self.unlike_local(track)
                )
            else:
                like_action = menu.addAction("添加到我喜欢")
                like_action.triggered.connect(
                    lambda checked=False, track=item.to_dict(): self.like_local(track)
                )
        playlist_menu = menu.addMenu("添加到歌单")
        playlists = self.window.get_online_playlist_choices()
        if not playlists:
            empty = playlist_menu.addAction("暂无自定义歌单")
            empty.setEnabled(False)
        for playlist_id, name in playlists:
            action = playlist_menu.addAction(name)
            if item.media_type == "online":
                action.triggered.connect(
                    lambda checked=False, track=item.to_dict(), target=playlist_id:
                    self.window.add_online_track_to_playlist(track, target)
                )
            else:
                action.triggered.connect(
                    lambda checked=False, track=item.to_dict(), target=playlist_id:
                    self.add_local_to_playlist(track, target)
                )
        if state.get("inCurrentPlaylist"):
            remove_current = menu.addAction("从当前歌单移除")
            if item.media_type == "online":
                stable_id = str(
                    state.get("stableId")
                    or item.extra.get("remote_stable_id")
                    or ""
                )
                remove_current.triggered.connect(
                    lambda checked=False, target=stable_id:
                    self.window.remove_remote_from_current_playlist(target)
                )
            else:
                remove_current.triggered.connect(
                    lambda checked=False, track=item.to_dict():
                    self.remove_local_from_current_playlist(track)
                )
        if item.media_type == "online" and item.can_download:
            download_action = menu.addAction("下载")
            download_action.setEnabled(item.availability == "available")
            download_action.triggered.connect(
                lambda checked=False, track=item.to_dict():
                self.window.request_online_download(track)
            )
        menu.addSeparator()
        if item.media_type == "local":
            open_action = menu.addAction("打开文件位置")
            open_action.triggered.connect(
                lambda checked=False, track=item.to_dict(): self.open_local_folder(track)
            )
            remove_action = menu.addAction("从音乐库移除")
            remove_action.triggered.connect(
                lambda checked=False, track=item.to_dict(): self.remove_local(track)
            )
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(
            lambda checked=False, track=item.to_dict(): self.show_info(track)
        )
        menu.exec(global_position)
