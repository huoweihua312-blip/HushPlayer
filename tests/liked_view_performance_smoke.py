from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-liked-view-")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui.main_window import MainWindow


class FixtureRegistry:
    def list_sources(self) -> list[dict]:
        return [
            {
                "id": "custom_source_fixture",
                "name": "本机模拟来源",
                "enabled": True,
                "sourceUrl": "https://example.invalid/fixture.js",
                "capabilities": {
                    "search": True,
                    "playback": True,
                    "download": False,
                },
            }
        ]

    def get_source(self, source_id: str) -> dict | None:
        for source in self.list_sources():
            if source["id"] == source_id:
                return dict(source)
        return None


def build_fixture(window: MainWindow, root: Path) -> None:
    local_songs: list[dict] = []
    local_paths: list[str] = []
    members: list[dict] = []
    for index in range(300):
        path = window.normalize_song_path(str(root / f"local_{index:03d}.mp3"))
        local_paths.append(path)
        local_songs.append(
            {
                "title": f"本地歌曲 {index:03d}",
                "artist": f"歌手 {index % 12:02d}",
                "album": f"专辑 {index % 8:02d}",
                "path": path,
                "added_at": index + 1,
                "demo": False,
            }
        )
        members.append(
            {
                "kind": PlaylistMembership.LOCAL,
                "id": path,
                "added_at": index + 1,
            }
        )

    remote_ids: list[str] = []
    remote_tracks: dict[str, dict] = {}
    remote_songs: list[dict] = []
    for index in range(52):
        track = {
            "sourceId": "custom_source_fixture",
            "id": f"remote-{index:03d}",
            "title": f"在线歌曲 {index:03d}",
            "artist": f"在线歌手 {index % 7:02d}",
            "album": "在线专辑",
            "duration": 180 + index,
            "raw": {"id": f"remote-{index:03d}"},
        }
        stable_id, record = RemoteTrackStore.build_record(
            track,
            "https://example.invalid/fixture.js",
        )
        remote_ids.append(stable_id)
        remote_tracks[stable_id] = record
        remote_songs.append(
            RemoteTrackStore.to_song_data(
                stable_id,
                record,
                source_available=True,
            )
        )
        members.append(
            {
                "kind": PlaylistMembership.REMOTE,
                "id": stable_id,
                "added_at": 301 + index,
            }
        )

    window.playlists = {
        "liked": {
            "name": "我喜欢",
            "songs": local_paths,
            "remoteSongs": remote_ids,
            "members": members,
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": True,
        }
    }
    window.invalidate_playlist_membership_snapshot()
    window.remote_tracks = remote_tracks
    window.source_registry_manager = FixtureRegistry()
    window.song_list.clear()
    window.song_identity_to_item = {}
    for song in [*local_songs, *remote_songs]:
        window.song_list.addItem(window.create_song_list_item(song))
    window.current_library_view = "all"
    window.library_sort_field = None
    window.library_sort_descending = False
    window.mark_library_list_dirty()
    window._fixture_newest_remote_id = remote_ids[-1]


def run_test(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    window = None
    original_normalize_function = None
    try:
        window = MainWindow()
        with tempfile.TemporaryDirectory(prefix="hushplayer_liked_perf_") as temp_dir:
            root = Path(temp_dir)
            window.playlists_file = root / "playlists.json"
            window.remote_tracks_file = root / "remote_tracks.json"
            window.remote_track_store = RemoteTrackStore(window.remote_tracks_file)
            build_fixture(window, root)

            counts = {
                "normalize": 0,
                "rebuild": 0,
                "create": 0,
                "playlist_save": 0,
                "remote_load": 0,
            }
            normalize_function = PlaylistMembership.normalize_playlist.__func__
            original_normalize_function = normalize_function
            original_rebuild = window.rebuild_song_list_from_data
            original_create = window.create_song_list_item
            original_save = window.save_playlists
            original_remote_load = window.remote_track_store.load_tracks

            def counted_normalize(cls, *args, **kwargs):
                counts["normalize"] += 1
                return normalize_function(cls, *args, **kwargs)

            PlaylistMembership.normalize_playlist = classmethod(counted_normalize)
            window.rebuild_song_list_from_data = lambda songs: (
                counts.__setitem__("rebuild", counts["rebuild"] + 1),
                original_rebuild(songs),
            )[1]
            window.create_song_list_item = lambda song: (
                counts.__setitem__("create", counts["create"] + 1),
                original_create(song),
            )[1]
            window.save_playlists = lambda: (
                counts.__setitem__("playlist_save", counts["playlist_save"] + 1),
                original_save(),
            )[1]
            window.remote_track_store.load_tracks = lambda: (
                counts.__setitem__("remote_load", counts["remote_load"] + 1),
                original_remote_load(),
            )[1]

            started = time.perf_counter()
            window.set_library_view("liked")
            first_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            window.set_library_view("liked")
            cached_ms = (time.perf_counter() - started) * 1000

            assert counts == {
                "normalize": 0,
                "rebuild": 0,
                "create": 0,
                "playlist_save": 0,
                "remote_load": 0,
            }
            assert first_ms < 1500
            assert cached_ms < 300
            assert len(window.get_visible_rows()) == 352
            assert not window.song_list.isSortingEnabled()
            first_item = window.song_list.item(0)
            first_data = first_item.data(Qt.ItemDataRole.UserRole)
            assert first_data["remoteStableId"] == window._fixture_newest_remote_id
            print(
                "liked view performance smoke: OK "
                f"first={first_ms:.1f} ms cached={cached_ms:.1f} ms calls={counts}"
            )
    finally:
        if original_normalize_function is not None:
            PlaylistMembership.normalize_playlist = classmethod(
                original_normalize_function
            )
        if window is not None:
            window.hide()
            window.deleteLater()
            app.processEvents()
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    run_test(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
