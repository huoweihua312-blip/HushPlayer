from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.models.playback_queue_item import PlaybackQueueItem
from app.services.playback_queue import PlaybackQueue
from app.ui.main_window import MainWindow


def remote_item(track_id: str, title: str) -> PlaybackQueueItem:
    return PlaybackQueueItem(
        MediaItem.from_online(
            {
                "sourceId": "fixture_source",
                "sourceName": "模拟来源",
                "sourceUrl": "https://example.invalid/fixture-source.js",
                "id": track_id,
                "title": title,
                "artist": "Remote artist",
                "album": "Remote album",
                "availability": "available",
                "capabilities": {"playback": True, "download": False},
                "raw": {
                    "id": track_id,
                    "url": f"https://example.invalid/{track_id}.mp3",
                },
            }
        )
    )


def local_item(path: Path, title: str) -> PlaybackQueueItem:
    return PlaybackQueueItem(
        MediaItem.from_local(
            {
                "path": str(path),
                "title": title,
                "artist": "Local artist",
                "album": "Local album",
            }
        )
    )


def test_queue_state(items: list[PlaybackQueueItem]) -> None:
    local_a, remote_b, local_c, remote_d = items
    queue = PlaybackQueue(random.Random(7))
    queue.replace(items, remote_b.stable_identity)

    assert queue.next_index("sequence", 1) == 2
    assert queue.current_item == local_c
    assert queue.next_index("sequence", 1) == 3
    assert queue.current_item == remote_d
    assert queue.next_index("sequence", 1) is None

    queue.set_current_identity(remote_d.stable_identity)
    assert queue.next_index("list_loop", 1) == 0
    assert queue.current_item == local_a
    assert queue.next_index("list_loop", -1) == 3
    assert queue.current_item == remote_d

    queue.replace(items, local_a.stable_identity)
    visited = {queue.current_identity}
    for _ in range(len(items) - 1):
        index = queue.next_index("shuffle", 1)
        assert index is not None
        visited.add(queue.current_identity)
    assert visited == {item.stable_identity for item in items}
    assert any(identity.startswith("remote:") for identity in visited)
    current = queue.current_identity
    previous_index = queue.next_index("shuffle", -1)
    assert previous_index is not None
    assert queue.current_identity != current
    assert queue.next_index("shuffle", 1) is not None
    assert queue.current_identity == current

    queue.set_current_identity(remote_b.stable_identity)
    assert queue.next_index("single_loop", 1) == 1
    assert queue.current_item == remote_b


def test_storage(items: list[PlaybackQueueItem]) -> None:
    local_a, remote_b, _, _ = items
    local_value = local_a.to_storage_value()
    remote_value = remote_b.to_storage_value()
    assert local_value == local_a.local_path
    assert isinstance(remote_value, dict)
    serialized = json.dumps(remote_value, ensure_ascii=False)
    assert "example.invalid" not in serialized
    assert PlaybackQueueItem.from_value(remote_value).stable_identity == remote_b.stable_identity


def test_main_window_navigation(
    app: QApplication,
    items: list[PlaybackQueueItem],
) -> None:
    local_a, remote_b, local_c, remote_d = items
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        window = MainWindow()
        window.create_playback_context(
            remote_b,
            [item.to_mapping() for item in items],
            source_type="playlist",
            source_id="mixed-fixture",
        )
        played: list[str] = []

        def fake_play(value, *, update_context=True):
            item = window.playback_queue_item_from_value(value)
            assert item is not None
            if update_context:
                window.sync_playback_context_current(item.stable_identity)
            window.begin_playback_generation(item.stable_identity)
            window.current_media_item = item.media_item
            window.current_track_kind = "online" if item.kind == "remote" else "local"
            window.current_song_path = item.local_path if item.kind == "local" else None
            played.append(item.stable_identity)
            return True

        window.play_queue_item = fake_play
        window.current_queue_identity = remote_b.stable_identity
        window.current_media_item = remote_b.media_item
        window.current_track_kind = "online"
        window.playback_queue.set_current_identity(remote_b.stable_identity)
        window.play_mode = "sequence"
        window.play_next_song()
        assert played[-1] == local_c.stable_identity
        window.play_next_song()
        assert played[-1] == remote_d.stable_identity
        count_at_end = len(played)
        window.play_next_song()
        assert len(played) == count_at_end

        window.play_mode = "list_loop"
        window.begin_playback_generation(remote_d.stable_identity)
        window.playback_queue.set_current_identity(remote_d.stable_identity)
        window.media_loading_generation = 0
        window.last_advance_at = 0.0
        window.last_end_advance_at = 0.0
        window.on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
        assert played[-1] == local_a.stable_identity

        window.playback_queue.set_current_identity(remote_b.stable_identity)
        window.current_queue_identity = remote_b.stable_identity
        old_generation = window.begin_playback_generation(remote_b.stable_identity)
        window.last_advance_at = 0.0
        window.play_next_song()
        assert played[-1] == local_c.stable_identity
        after_manual = len(played)
        window.handle_song_finished(old_generation)
        assert len(played) == after_manual

        window.playback_queue.set_current_identity(remote_b.stable_identity)
        window.current_queue_identity = remote_b.stable_identity
        window.current_media_item = remote_b.media_item
        window.play_mode = "single_loop"
        replayed: list[str] = []
        window.replay_current_song = lambda: replayed.append(
            window.current_track_identity()
        ) or True
        assert window.play_from_playback_context(1)
        assert replayed == [remote_b.stable_identity]

        window.play_queue_item = MainWindow.play_queue_item.__get__(window, MainWindow)
        requests: list[tuple[str, int]] = []
        window.request_online_playback = (
            lambda track, **kwargs: requests.append(
                (str(track.get("id") or ""), int(kwargs.get("playback_generation") or 0))
            )
        )
        window.playback_queue.set_current_identity(remote_d.stable_identity)
        assert window.play_queue_item(remote_d)
        assert window.playback_queue.current_identity == remote_d.stable_identity
        assert window.current_queue_identity == remote_d.stable_identity
        assert requests and requests[-1][0] == "remote-d"
        window.current_media_item = remote_d.media_item
        window.current_track_kind = "online"
        window.media_player.setSource(QUrl())
        assert window.replay_current_song()
        assert requests[-1][0] == "remote-d"
        failure_generation = window.playback_generation
        window.pending_online_playback_request = 91
        window.pending_online_playback_generation = failure_generation
        window.pending_online_playback_identity = remote_d.stable_identity
        window.pending_online_keep_target_on_failure = True
        window.pending_online_track = remote_d.media_item.to_legacy_online()
        window.pending_online_media_item = remote_d.media_item
        window.on_online_source_request_failed(
            91,
            "resolvePlayback",
            "fixture resolution failure",
        )
        assert window.playback_queue.current_identity == remote_d.stable_identity
        assert window.current_queue_identity == remote_d.stable_identity

        window.play_queue = [local_a, remote_b, local_c, remote_d]
        window.save_play_queue()
        restored_queue = window.load_play_queue()
        assert [item.stable_identity for item in restored_queue] == [
            item.stable_identity for item in window.play_queue
        ]

        identities_before = [item.stable_identity for item in window.playback_queue.items]
        window.pending_online_media_item = remote_d.media_item
        window.pending_online_metadata_identity = remote_d.stable_identity
        window.pending_online_metadata_request = 81
        window.on_online_metadata_finished(
            81,
            remote_d.source_id,
            {"title": "Remote D enriched", "album": "Updated album"},
        )
        assert [item.stable_identity for item in window.playback_queue.items] == identities_before

        window.media_player.stop()
        window.online_source_client.stop()
        window.deleteLater()
        app.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="hushplayer_mixed_queue_") as temp_dir:
        root = Path(temp_dir)
        app_data = root / "appdata"
        cache = root / "cache"
        logs = root / "logs"
        os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(app_data)
        os.environ["HUSHPLAYER_CACHE_DIR"] = str(cache)
        os.environ["HUSHPLAYER_LOG_DIR"] = str(logs)
        local_a_path = root / "local-a.wav"
        local_c_path = root / "local-c.wav"
        local_a_path.write_bytes(b"RIFF")
        local_c_path.write_bytes(b"RIFF")
        items = [
            local_item(local_a_path, "Local A"),
            remote_item("remote-b", "Remote B"),
            local_item(local_c_path, "Local C"),
            remote_item("remote-d", "Remote D"),
        ]
        test_queue_state(items)
        test_storage(items)
        test_main_window_navigation(app, items)
    print("mixed playback queue smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
