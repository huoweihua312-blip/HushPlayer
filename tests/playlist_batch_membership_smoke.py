from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RUNTIME = tempfile.TemporaryDirectory(prefix="hushplayer_playlist_batch_")
RUNTIME_ROOT = Path(RUNTIME.name)
os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(RUNTIME_ROOT / "appdata")
os.environ["HUSHPLAYER_CACHE_DIR"] = str(RUNTIME_ROOT / "cache")
os.environ["HUSHPLAYER_LOG_DIR"] = str(RUNTIME_ROOT / "logs")
ISOLATED_DATA_DIR = RUNTIME_ROOT / "appdata" / "data"
ISOLATED_DATA_DIR.mkdir(parents=True, exist_ok=True)
for filename, payload in {
    "library.json": [],
    "settings.json": {},
    "playlists.json": {
        "liked": {
            "name": "我喜欢",
            "songs": [],
            "remoteSongs": [],
            "members": [],
            "membershipVersion": 1,
            "fixed": True,
        }
    },
    "stats.json": {},
    "lyrics_bindings.json": {},
    "playback_session.json": {},
    "play_queue.json": [],
    "metadata_cache.json": {},
    "pending_imports.json": [],
    "ignored_imports.json": [],
    "remote_tracks.json": {},
}.items():
    (ISOLATED_DATA_DIR / filename).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.models.media_item import MediaItem
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui.main_window import MainWindow


FIXED_TIME_SECONDS = 1_700_000_000.0


class FixtureRegistry:
    SOURCE = {
        "id": "playlist_batch_fixture",
        "name": "批量歌单测试来源",
        "enabled": True,
        "sourceUrl": "https://example.invalid/playlist-batch.js",
        "capabilities": {"search": True, "playback": True, "download": False},
    }

    def get_source(self, source_id: str) -> dict | None:
        return dict(self.SOURCE) if source_id == self.SOURCE["id"] else None

    def list_sources(self) -> list[dict]:
        return [dict(self.SOURCE)]


def normalize_path(value: str) -> str:
    return str(Path(value).resolve()) if value else ""


def normalized_playlist(local_paths: list[str], remote_ids: list[str]) -> dict:
    members = [
        {
            "kind": PlaylistMembership.LOCAL,
            "id": normalize_path(path),
            "added_at": 100 + index,
        }
        for index, path in enumerate(local_paths)
    ]
    members.extend(
        {
            "kind": PlaylistMembership.REMOTE,
            "id": stable_id,
            "added_at": 200 + index,
        }
        for index, stable_id in enumerate(remote_ids)
    )
    return {
        "name": "测试歌单",
        "songs": [normalize_path(path) for path in local_paths],
        "remoteSongs": list(remote_ids),
        "members": members,
        "membershipVersion": PlaylistMembership.VERSION,
        "fixed": False,
    }


def legacy_add(playlist: dict, inputs: list) -> int:
    changed = 0
    for value in inputs:
        if isinstance(value, dict):
            kind = value.get("kind")
            identifier = value.get("id")
            added_at = value.get("added_at")
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            kind = value[0]
            identifier = value[1]
            added_at = value[2] if len(value) >= 3 else None
        else:
            continue
        changed += int(
            PlaylistMembership.add_member(
                playlist,
                kind,
                identifier,
                normalize_path,
                added_at=added_at,
            )
        )
    if changed:
        # Existing UI persistence normalizes the complete document once more.
        PlaylistMembership.normalize_playlist(playlist, normalize_path)
    return changed


def legacy_remove(playlist: dict, inputs: list) -> int:
    changed = 0
    for value in inputs:
        if not isinstance(value, (tuple, list)) or len(value) < 2:
            continue
        changed += int(
            PlaylistMembership.remove_member(
                playlist,
                value[0],
                value[1],
                normalize_path,
            )
        )
    return changed


def test_service_batch_equivalence(root: Path) -> None:
    first = str(root / "first.mp3")
    second = str(root / "folder" / ".." / "second.mp3")
    third = str(root / "third.mp3")
    base = normalized_playlist([first, second], ["remote-existing"])
    add_inputs = [
        (PlaylistMembership.LOCAL, third),
        (PlaylistMembership.LOCAL, third),
        (PlaylistMembership.LOCAL, first),
        (PlaylistMembership.REMOTE, "remote-new"),
        (PlaylistMembership.REMOTE, "remote-new"),
        (PlaylistMembership.REMOTE, "remote-existing"),
        ("invalid-kind", "invalid"),
        (PlaylistMembership.LOCAL, ""),
    ]
    legacy = deepcopy(base)
    optimized = deepcopy(base)
    stable_calls = 0

    def counted_normalizer(value: str) -> str:
        nonlocal stable_calls
        stable_calls += 1
        return normalize_path(value)

    with patch("app.services.playlist_membership.time.time", return_value=FIXED_TIME_SECONDS):
        legacy_count = legacy_add(legacy, add_inputs)
        result = PlaylistMembership.add_members(
            optimized,
            add_inputs,
            counted_normalizer,
        )
    assert optimized == legacy
    assert legacy_count == result["added"] == 2
    assert result["skipped"] == 4
    assert result["skipped_existing"] == 2
    assert result["skipped_duplicate"] == 2
    assert result["invalid"] == 2
    assert result["changed"]
    assert stable_calls <= 4

    remove_inputs = [
        (PlaylistMembership.LOCAL, first),
        (PlaylistMembership.LOCAL, first),
        (PlaylistMembership.LOCAL, str(root / "missing.mp3")),
        (PlaylistMembership.REMOTE, "remote-existing"),
        (PlaylistMembership.REMOTE, "remote-existing"),
        (PlaylistMembership.REMOTE, "remote-missing"),
        ("invalid-kind", "invalid"),
        (PlaylistMembership.LOCAL, ""),
    ]
    legacy_removed = deepcopy(legacy)
    optimized_removed = deepcopy(optimized)
    legacy_count = legacy_remove(legacy_removed, remove_inputs)
    result = PlaylistMembership.remove_members(
        optimized_removed,
        remove_inputs,
        normalize_path,
    )
    assert optimized_removed == legacy_removed
    assert legacy_count == result["removed"] == 2
    assert result["skipped"] == 4
    assert result["skipped_missing"] == 2
    assert result["skipped_duplicate"] == 2
    assert result["invalid"] == 2

    unchanged = deepcopy(optimized_removed)
    assert PlaylistMembership.add_members(unchanged, [], normalize_path) == {
        "input_count": 0,
        "added": 0,
        "removed": 0,
        "skipped": 0,
        "skipped_existing": 0,
        "skipped_missing": 0,
        "skipped_duplicate": 0,
        "invalid": 0,
        "failed": 0,
        "changed": False,
        "normalized_changed": False,
    }
    assert unchanged == optimized_removed
    missing_result = PlaylistMembership.remove_members(
        unchanged,
        [(PlaylistMembership.REMOTE, "not-present")],
        normalize_path,
    )
    assert not missing_result["changed"]
    assert missing_result["skipped_missing"] == 1
    assert unchanged == optimized_removed

    legacy_format = {
        "name": "旧格式",
        "songs": [first, second],
        "remoteSongs": ["remote-existing"],
        "fixed": False,
    }
    old_legacy = deepcopy(legacy_format)
    old_optimized = deepcopy(legacy_format)
    with patch("app.services.playlist_membership.time.time", return_value=FIXED_TIME_SECONDS):
        legacy_add(old_legacy, [(PlaylistMembership.LOCAL, third)])
        PlaylistMembership.add_members(
            old_optimized,
            [(PlaylistMembership.LOCAL, third)],
            normalize_path,
        )
    assert old_optimized == old_legacy


def local_song(title: str, path: str) -> dict:
    return {
        "title": title,
        "artist": "批量测试歌手",
        "album": "批量测试专辑",
        "path": path,
        "added_at": 1,
        "demo": False,
    }


def remote_track(track_id: str, title: str) -> dict:
    return {
        "sourceId": FixtureRegistry.SOURCE["id"],
        "sourceName": FixtureRegistry.SOURCE["name"],
        "sourceUrl": FixtureRegistry.SOURCE["sourceUrl"],
        "id": track_id,
        "title": title,
        "artist": "在线测试歌手",
        "album": "在线测试专辑",
        "capabilities": {"playback": True, "download": False},
        "availability": "available",
        "raw": {"id": track_id},
    }


def item_by_title(window: MainWindow, title: str):
    for row in range(window.song_list.count()):
        item = window.song_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(data, dict) and data.get("title") == title:
            return item
    return None


@contextmanager
def counted_ui_calls(window: MainWindow):
    method_names = (
        "save_playlists",
        "mark_library_list_dirty",
        "sort_song_list_for_current_view",
        "filter_song_list",
        "refresh_playlist_membership_views",
        "refresh_playlist_view_buttons",
        "rebuild_song_list_from_data",
    )
    originals = {name: getattr(window, name) for name in method_names}
    counts = {name: 0 for name in method_names}

    for name, original in originals.items():
        def counted(*args, _name=name, _original=original, **kwargs):
            counts[_name] += 1
            return _original(*args, **kwargs)

        setattr(window, name, counted)
    try:
        yield counts
    finally:
        for name, original in originals.items():
            setattr(window, name, original)


def assert_one_transaction(counts: dict, refresh_method: str | None = None) -> None:
    assert counts["save_playlists"] == 1, counts
    assert counts["mark_library_list_dirty"] == 1, counts
    if refresh_method is not None:
        assert counts[refresh_method] == 1, counts
    assert counts["refresh_playlist_view_buttons"] == 0, counts
    assert counts["rebuild_song_list_from_data"] == 0, counts


def test_ui_batch_paths(app: QApplication, root: Path) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    window = None
    try:
        window = MainWindow()
        window.show()
        app.processEvents()
        case_root = root / "ui"
        case_root.mkdir(parents=True, exist_ok=True)
        window.playlists_file = case_root / "playlists.json"
        window.remote_tracks_file = case_root / "remote_tracks.json"
        window.remote_track_store = RemoteTrackStore(window.remote_tracks_file)
        window.remote_tracks = {}
        window.remote_tracks_error = ""
        window.source_registry_manager = FixtureRegistry()
        window.playlists_load_error = ""

        paths = [str(case_root / f"local-{index}.mp3") for index in range(1, 6)]
        for path in paths:
            Path(path).write_bytes(b"")
        songs = [local_song(f"本地歌曲 {index}", path) for index, path in enumerate(paths, 1)]
        window.song_list.clear()
        for song in songs:
            window.song_list.addItem(window.create_song_list_item(song))
        window.playlists = {
            "liked": normalized_playlist([], []),
            "custom": normalized_playlist([], []),
            "legacy": {
                "name": "旧格式歌单",
                "songs": [paths[0]],
                "remoteSongs": ["remote-preserved"],
                "fixed": False,
            },
        }
        window.playlists["liked"]["name"] = "我喜欢"
        window.playlists["liked"]["fixed"] = True
        window.invalidate_playlist_membership_snapshot()
        window.current_media_item = MediaItem.from_local(songs[0])
        window.current_song_path = paths[0]
        window.current_track_kind = "local"
        window.refresh_playing_song_indicators()
        playing_identity = window.current_track_identity()

        window.current_library_view = "playlist:custom"
        window.library_sort_field = None
        window.song_list.clearSelection()
        for index in range(3):
            window.song_list.item(index).setSelected(True)
        selected_paths = window.get_selected_song_paths_for_playlist_menu()
        assert selected_paths == paths[:3]

        with counted_ui_calls(window) as counts:
            window.add_selected_songs_to_playlist("custom", selected_paths)
        assert_one_transaction(counts)
        assert counts["sort_song_list_for_current_view"] == 1
        assert counts["filter_song_list"] == 1
        assert window.get_playlist_song_paths("custom") == [
            normalize_path(path) for path in paths[:3]
        ]
        timestamps = [
            member["added_at"]
            for member in window.playlists["custom"]["members"]
        ]
        assert timestamps == sorted(timestamps)
        assert window.current_track_identity() == playing_identity

        with counted_ui_calls(window) as counts:
            window.add_selected_songs_to_playlist("custom", selected_paths)
        assert counts["save_playlists"] == 0
        assert counts["mark_library_list_dirty"] == 0
        assert counts["sort_song_list_for_current_view"] == 0
        assert counts["filter_song_list"] == 0

        online = remote_track("online-one", "在线歌曲一")
        stable_id = RemoteTrackStore.stable_id_for_track(online)
        window.current_library_view = "all"
        with counted_ui_calls(window) as counts:
            window.add_online_track_to_playlist(online, "custom")
        assert_one_transaction(counts, "refresh_playlist_membership_views")
        assert stable_id in window.get_playlist_remote_ids("custom")

        mixed_remote = remote_track("online-two", "在线歌曲二")
        mixed_stable_id = RemoteTrackStore.stable_id_for_track(mixed_remote)
        with counted_ui_calls(window) as counts:
            result = window.add_playlist_members(
                "custom",
                [
                    (PlaylistMembership.LOCAL, paths[3]),
                    (PlaylistMembership.REMOTE, mixed_stable_id),
                    (PlaylistMembership.LOCAL, paths[3]),
                ],
            )
        assert_one_transaction(counts)
        assert result["added"] == 2
        assert result["skipped_duplicate"] == 1
        assert window.get_playlist_song_paths("liked") == []
        assert window.get_playlist_remote_ids("liked") == []

        window.current_library_view = "playlist:custom"
        window.library_sort_field = "title"
        window.library_sort_descending = False
        window.song_list.clearSelection()
        local_item = item_by_title(window, "本地歌曲 2")
        remote_item = item_by_title(window, "在线歌曲一")
        assert local_item is not None and remote_item is not None
        local_item.setSelected(True)
        remote_item.setSelected(True)
        with counted_ui_calls(window) as counts:
            window.remove_current_song_from_current_playlist()
        assert_one_transaction(counts, "refresh_playlist_membership_views")
        assert normalize_path(paths[1]) not in window.get_playlist_song_paths("custom")
        assert stable_id not in window.get_playlist_remote_ids("custom")
        assert window.current_track_identity() == playing_identity
        assert window.library_sort_field == "title"
        playing_item = window.find_song_item_by_identity(playing_identity)
        assert playing_item is not None
        playing_data = playing_item.data(Qt.ItemDataRole.UserRole)
        assert window.get_song_item_display_text(playing_data).startswith("▶")

        with counted_ui_calls(window) as counts:
            liked_result = window.add_playlist_members(
                "liked",
                [
                    (PlaylistMembership.LOCAL, paths[0]),
                    (PlaylistMembership.REMOTE, stable_id),
                ],
            )
        assert_one_transaction(counts)
        assert liked_result["added"] == 2

        before_failure = deepcopy(window.playlists)
        dirty_before = window.library_list_dirty
        revision_before = window.library_data_revision
        view_before = window.current_library_view
        sort_before = window.library_sort_field
        selected_before = [
            window.track_identity_for_song_data(window.get_song_data_from_item(item))
            for item in window.get_selected_song_items()
        ]
        disk_before = window.playlists_file.read_bytes()
        warning_messages = []
        original_save = window.save_playlists
        window.save_playlists = lambda: False
        try:
            with patch.object(
                QMessageBox,
                "warning",
                side_effect=lambda _parent, _title, message: warning_messages.append(message),
            ):
                failed = window.add_playlist_members(
                    "custom",
                    [(PlaylistMembership.LOCAL, paths[4])],
                )
        finally:
            window.save_playlists = original_save
        assert not failed["changed"]
        assert failed["failed"] == 1
        assert failed["rolled_back"]
        assert window.playlists == before_failure
        assert window.library_list_dirty == dirty_before
        assert window.library_data_revision == revision_before
        assert window.current_library_view == view_before
        assert window.library_sort_field == sort_before
        assert window.current_track_identity() == playing_identity
        assert [
            window.track_identity_for_song_data(window.get_song_data_from_item(item))
            for item in window.get_selected_song_items()
        ] == selected_before
        assert window.playlists_file.read_bytes() == disk_before
        assert len(warning_messages) == 1

        remote_before_cleanup = {
            playlist_id: list(playlist.get("remoteSongs", []))
            for playlist_id, playlist in window.playlists.items()
        }
        with counted_ui_calls(window) as counts:
            assert window.remove_songs_from_playlists_and_queue(
                {normalize_path(paths[0])}
            )
        assert_one_transaction(counts)
        assert counts["refresh_playlist_membership_views"] == 0
        for playlist_id, playlist in window.playlists.items():
            assert normalize_path(paths[0]) not in window.get_playlist_song_paths(
                playlist_id
            )
            assert playlist.get("remoteSongs", []) == remote_before_cleanup[playlist_id]

        before_cleanup_failure = deepcopy(window.playlists)
        window.playlists["custom"]["songs"].append(normalize_path(paths[4]))
        window.playlists["custom"]["members"].append(
            {
                "kind": PlaylistMembership.LOCAL,
                "id": normalize_path(paths[4]),
                "added_at": 9_999,
            }
        )
        before_cleanup_failure = deepcopy(window.playlists)
        original_save = window.save_playlists
        window.save_playlists = lambda: False
        try:
            with patch.object(QMessageBox, "warning", return_value=None):
                assert not window.remove_songs_from_playlists_and_queue(
                    {normalize_path(paths[4])}
                )
        finally:
            window.save_playlists = original_save
        assert window.playlists == before_cleanup_failure

        saved = json.loads(window.playlists_file.read_text(encoding="utf-8"))
        assert "liked" in saved and "custom" in saved
    finally:
        if window is not None:
            window.hide()
            window.deleteLater()
            app.processEvents()
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        test_service_batch_equivalence(RUNTIME_ROOT)
        test_ui_batch_paths(app, RUNTIME_ROOT)
        print("playlist batch membership smoke: OK")
        return 0
    finally:
        RUNTIME.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
