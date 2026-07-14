from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app.models.media_item import MediaItem
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui.main_window import MainWindow
from app.ui.track_details_panel import TrackDetailsPanel


class FixtureRegistry:
    SOURCE = {
        "id": "custom_source_fixture",
        "name": "本机模拟来源",
        "enabled": True,
        "sourceUrl": "https://example.invalid/open-source.js",
        "capabilities": {"search": True, "playback": True, "download": False},
    }

    def get_source(self, source_id: str) -> dict | None:
        return dict(self.SOURCE) if source_id == self.SOURCE["id"] else None

    def list_sources(self) -> list[dict]:
        return [dict(self.SOURCE)]


def normalize_fixture_path(value: str) -> str:
    return str(Path(value).resolve()) if value else ""


def test_membership_migration() -> None:
    legacy = {
        "name": "旧歌单",
        "songs": ["C:/fixtures/one.mp3", "C:/fixtures/two.mp3"],
        "remoteSongs": ["remote_fixture"],
        "fixed": False,
        "unknownField": {"preserved": True},
    }
    assert PlaylistMembership.normalize_playlist(
        legacy,
        normalize_fixture_path,
        anchor_ms=1_700_000_000_000,
    )
    members = legacy["members"]
    assert [member["kind"] for member in members] == ["local", "local", "remote"]
    assert [member["added_at"] for member in members] == [
        1_700_000_000_000,
        1_699_999_999_999,
        1_699_999_999_998,
    ]
    assert legacy["unknownField"] == {"preserved": True}
    snapshot = json.loads(json.dumps(legacy))
    assert not PlaylistMembership.normalize_playlist(
        legacy,
        normalize_fixture_path,
        anchor_ms=1_800_000_000_000,
    )
    assert legacy == snapshot

    first_time = PlaylistMembership.added_at(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
    )
    assert not PlaylistMembership.add_member(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
        added_at=1_900_000_000_000,
    )
    assert PlaylistMembership.added_at(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
    ) == first_time
    assert PlaylistMembership.remove_member(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
    )
    assert PlaylistMembership.add_member(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
        added_at=1_900_000_000_000,
    )
    assert PlaylistMembership.added_at(
        legacy,
        "local",
        "C:/fixtures/one.mp3",
        normalize_fixture_path,
    ) > first_time


def visible_titles(window: MainWindow) -> list[str]:
    titles: list[str] = []
    for row in range(window.song_list.count()):
        item = window.song_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if item is not None and not item.isHidden() and isinstance(data, dict):
            titles.append(str(data.get("title") or ""))
    return titles


def visible_values(window: MainWindow, field: str) -> list[str]:
    values: list[str] = []
    for row in range(window.song_list.count()):
        item = window.song_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if item is not None and not item.isHidden() and isinstance(data, dict):
            values.append(str(data.get(field) or "").strip().casefold())
    return values


def local_song(title: str, artist: str, path: str) -> dict:
    return {
        "title": title,
        "artist": artist,
        "album": "测试专辑",
        "path": path,
        "added_at": 1,
        "demo": False,
    }


def test_window_membership_and_sorting(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        window = MainWindow()
        window.show()
        app.processEvents()
        with tempfile.TemporaryDirectory(prefix="hushplayer_playlist_membership_") as temp_dir:
            root = Path(temp_dir)
            window.playlists_file = root / "playlists.json"
            window.remote_tracks_file = root / "remote_tracks.json"
            window.remote_track_store = RemoteTrackStore(window.remote_tracks_file)
            window.remote_tracks = {}
            window.remote_tracks_error = ""
            window.source_registry_manager = FixtureRegistry()
            window.playlists_file.write_text(
                json.dumps(
                    {
                        "liked": {
                            "name": "我喜欢",
                            "songs": [str(root / "legacy.mp3")],
                            "remoteSongs": [],
                            "fixed": True,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            window.playlists = window.load_playlists()
            assert window.playlists_migration_pending
            migration_writes = 0
            original_save_playlists = window.save_playlists

            def counted_migration_save():
                nonlocal migration_writes
                migration_writes += 1
                return original_save_playlists()

            window.save_playlists = counted_migration_save
            window.persist_pending_playlist_migration()
            window.persist_pending_playlist_migration()
            window.save_playlists = original_save_playlists
            assert migration_writes == 1
            migrated = json.loads(
                window.playlists_file.read_text(encoding="utf-8")
            )
            assert migrated["liked"]["members"][0]["added_at"] > 0
            window.playlists = {
                "liked": {
                    "name": "我喜欢",
                    "songs": [],
                    "remoteSongs": [],
                    "members": [],
                    "membershipVersion": PlaylistMembership.VERSION,
                    "fixed": True,
                },
                "custom": {
                    "name": "测试歌单",
                    "songs": [],
                    "remoteSongs": [],
                    "members": [],
                    "membershipVersion": PlaylistMembership.VERSION,
                    "fixed": False,
                },
            }
            window.playlists_load_error = ""
            window.song_list.clear()

            paths = [
                str(root / "one.mp3"),
                str(root / "two.mp3"),
                str(root / "three.mp3"),
            ]
            songs = [
                local_song("本地一", "Charlie", paths[0]),
                local_song("本地二", "Alpha", paths[1]),
                local_song("本地三", "Bravo", paths[2]),
            ]
            for song in songs:
                window.song_list.addItem(window.create_song_list_item(song))
                assert window.add_local_path_to_playlist(song["path"], "liked")
            assert window.add_local_path_to_playlist(paths[0], "custom")

            remote_track = {
                "sourceId": "custom_source_fixture",
                "sourceName": "本机模拟来源",
                "sourceUrl": "https://example.invalid/open-source.js",
                "id": "remote-1",
                "title": "在线歌曲",
                "artist": "Delta",
                "album": "在线专辑",
                "capabilities": {"playback": True, "download": False},
                "availability": "available",
                "raw": {"id": "remote-1"},
            }

            # Search-result signal, context menus and the bottom button all
            # converge on the same online favorite methods.
            remote_save_calls = 0
            original_remote_save = window.remote_track_store.save_tracks

            def counted_remote_save(tracks):
                nonlocal remote_save_calls
                remote_save_calls += 1
                return original_remote_save(tracks)

            window.remote_track_store.save_tracks = counted_remote_save
            window.unified_search_panel.likeRequested.emit(dict(remote_track))
            app.processEvents()
            stable_id = RemoteTrackStore.stable_id_for_track(remote_track)
            assert stable_id in window.get_playlist_remote_ids("liked")
            assert remote_save_calls == 1
            first_remote_added_at = window.get_playlist_member_added_at(
                "liked", "remote", stable_id
            )
            window.like_online_track(remote_track)
            assert remote_save_calls == 1
            assert window.get_playlist_member_added_at(
                "liked", "remote", stable_id
            ) == first_remote_added_at

            window.set_library_view("liked")
            app.processEvents()
            assert visible_titles(window) == ["在线歌曲", "本地三", "本地二", "本地一"]

            playing_track = dict(remote_track)
            playing_track["remoteStableId"] = stable_id
            window.current_media_item = MediaItem.from_online(playing_track)
            window.current_online_track = dict(playing_track)
            window.current_track_kind = "online"
            order_before_play = visible_titles(window)
            refresh_calls = 0
            original_refresh = window.refresh_song_item_display

            def counted_refresh(item, song_data, update_viewport=True):
                nonlocal refresh_calls
                refresh_calls += 1
                return original_refresh(item, song_data, update_viewport)

            window.refresh_song_item_display = counted_refresh
            window.refresh_playing_song_indicators()
            window.refresh_song_item_display = original_refresh
            remote_item = window.find_song_item_by_identity(
                window.current_track_identity()
            )
            assert remote_item is not None
            remote_data = remote_item.data(Qt.ItemDataRole.UserRole)
            assert window.get_song_item_display_text(remote_data).startswith("▶")
            assert refresh_calls == 1
            assert visible_titles(window) == order_before_play

            assert window.refresh_remote_song_item(stable_id, resolving=True)
            assert window.refresh_remote_song_item(stable_id, resolving=False)
            assert visible_titles(window) == order_before_play
            assert window.get_playlist_member_added_at(
                "liked", "remote", stable_id
            ) == first_remote_added_at

            sync_calls = 0
            playback_requests = []
            original_sync = window.sync_remote_song_items
            original_request = window.request_online_playback

            def counted_sync():
                nonlocal sync_calls
                sync_calls += 1

            window.sync_remote_song_items = counted_sync
            window.request_online_playback = (
                lambda track, **_kwargs: playback_requests.append(track)
            )
            window.play_remote_song_data(remote_data)
            window.sync_remote_song_items = original_sync
            window.request_online_playback = original_request
            assert playback_requests
            assert sync_calls == 0
            assert visible_titles(window) == order_before_play

            window.toggle_like_current_song()
            assert stable_id not in window.get_playlist_remote_ids("liked")
            window.playlists = window.load_playlists()
            assert stable_id not in window.get_playlist_remote_ids("liked")
            window.toggle_like_current_song()
            assert stable_id in window.get_playlist_remote_ids("liked")

            saved = json.loads(window.playlists_file.read_text(encoding="utf-8"))
            assert saved["liked"]["remoteSongs"] == [stable_id]
            assert saved["liked"]["members"]
            assert saved["custom"]["members"][0]["id"] == normalize_fixture_path(paths[0])
            liked_first_time = window.get_playlist_member_added_at(
                "liked", "local", paths[0]
            )
            custom_first_time = window.get_playlist_member_added_at(
                "custom", "local", paths[0]
            )
            assert liked_first_time > 0 and custom_first_time > 0
            assert window.remove_local_path_from_playlist(paths[0], "custom")
            assert paths[0] in window.get_playlist_song_paths("liked")
            assert window.add_local_path_to_playlist(paths[0], "custom")
            assert window.get_playlist_member_added_at(
                "custom", "local", paths[0]
            ) > custom_first_time
            assert window.get_playlist_member_added_at(
                "liked", "local", paths[0]
            ) == liked_first_time

            window.set_library_view("liked")
            default_order = ["在线歌曲", "本地三", "本地二", "本地一"]
            for field, label in (
                ("title", "歌曲标题"),
                ("artist", "歌手"),
                ("album", "专辑"),
            ):
                window.sort_library_by_column(field)
                assert window.library_sort_field == field
                assert not window.library_sort_descending
                assert visible_values(window, field) == sorted(
                    visible_values(window, field)
                )
                assert window.library_sort_headers[field].text().endswith("↑")

                window.sort_library_by_column(field)
                assert window.library_sort_descending
                assert visible_values(window, field) == sorted(
                    visible_values(window, field), reverse=True
                )
                assert window.library_sort_headers[field].text().endswith("↓")

                window.sort_library_by_column(field)
                assert window.library_sort_field is None
                assert visible_titles(window) == default_order
                assert window.library_sort_headers[field].text() == label

            fourth_path = str(root / "four.mp3")
            fourth = local_song("本地四", "Aardvark", fourth_path)
            window.song_list.addItem(window.create_song_list_item(fourth))
            window.sort_library_by_column("artist")
            assert window.add_local_path_to_playlist(fourth_path, "liked")
            window.refresh_playlist_membership_views()
            assert visible_titles(window)[0] == "本地四"
            assert window.remove_local_path_from_playlist(fourth_path, "liked")
            window.refresh_playlist_membership_views()
            assert "本地四" not in visible_titles(window)

            window.set_library_view("playlist:custom")
            assert window.library_sort_field is None
            assert visible_titles(window) == ["本地一"]

            details = TrackDetailsPanel(
                MediaItem.from_online(remote_track),
                collection_state={"liked": True},
            )
            assert "已收藏" in [label.text() for label in details.findChildren(QLabel)]
            details.deleteLater()

        window.hide()
        window.deleteLater()
        app.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_membership_migration()
    test_window_membership_and_sorting(app)
    print("playlist membership smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
