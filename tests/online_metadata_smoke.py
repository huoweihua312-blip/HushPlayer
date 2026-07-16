from __future__ import annotations

import os
import sys
import tempfile
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-online-metadata-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem


def test_metadata_merge() -> None:
    item = MediaItem.from_online(
        {
            "sourceId": "fixture_source",
            "sourceName": "Fixture source",
            "id": "track-1",
            "title": "Search title",
            "artist": "Search artist",
            "album": "Search album",
            "artwork": "https://example.invalid/search.jpg",
            "capabilities": {"playback": True},
        }
    )
    identity = item.stable_identity
    updated = item.with_metadata(
        {
            "available": True,
            "item": {"title": "Normalized title"},
            "metadata": {
                "data": {
                    "title": "Detailed title",
                    "artist": "Detailed artist",
                    "albumName": "Detailed album",
                    "coverImg": "https://example.invalid/detail.jpg",
                    "duration": 245000,
                }
            },
        }
    )
    assert updated.stable_identity == identity
    assert updated.track_id == "track-1"
    assert updated.title == "Detailed title"
    assert updated.artist == "Detailed artist"
    assert updated.album == "Detailed album"
    assert updated.duration == 245
    assert updated.cover_url.endswith("/detail.jpg")


def test_main_window_metadata_flow(app: QApplication) -> None:
    from app.ui.main_window import MainWindow

    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    try:
        window = MainWindow()
        request_ids = {"playback": 100, "metadata": 200}
        cancelled: list[int] = []
        artwork_requests: list[tuple[str, str]] = []

        def resolve_playback(_source_id: str, _track: dict) -> int:
            request_ids["playback"] += 1
            return request_ids["playback"]

        def get_metadata(_source_id: str, _track: dict, timeout_ms: int) -> int:
            assert timeout_ms == 10000
            request_ids["metadata"] += 1
            return request_ids["metadata"]

        window.online_source_client.resolve_playback = resolve_playback
        window.online_source_client.get_metadata = get_metadata
        window.online_source_client.cancel_request = lambda request_id: cancelled.append(request_id) or True
        window.online_lyrics_service.request_lyrics = lambda _item: 1
        window.online_artwork_service.request = (
            lambda key, url: artwork_requests.append((key, url)) or len(artwork_requests)
        )

        first = {
            "sourceId": "fixture_source",
            "sourceName": "Fixture source",
            "id": "first",
            "title": "First search title",
            "artist": "First search artist",
            "album": "First search album",
            "artwork": "https://example.invalid/first.jpg",
            "capabilities": {"playback": True},
        }
        second = {
            **first,
            "id": "second",
            "title": "Second search title",
            "artist": "Second search artist",
            "artwork": "https://example.invalid/second.jpg",
        }

        window.request_online_playback(first)
        first_metadata_request = window.pending_online_metadata_request
        assert window.bottom_song_title.text() == "First search title"
        assert window.bottom_song_artist.text() == "First search artist"
        assert "First search artist" in window.now_artist.text()
        assert "Fixture source" in window.now_stats.text()
        assert "正在解析" in window.now_stats.text()
        assert not window.like_btn.isEnabled()

        window.request_online_playback(second)
        second_playback_request = window.pending_online_playback_request
        second_metadata_request = window.pending_online_metadata_request
        assert first_metadata_request in cancelled
        assert window.bottom_song_title.text() == "Second search title"

        window.on_online_metadata_finished(
            first_metadata_request,
            "fixture_source",
            {"metadata": {"title": "Stale title"}},
        )
        assert window.bottom_song_title.text() == "Second search title"

        window.on_online_metadata_finished(
            second_metadata_request,
            "fixture_source",
            {
                "metadata": {
                    "title": "Detailed second title",
                    "artist": "Detailed second artist",
                    "album": "Detailed second album",
                    "artwork": "https://example.invalid/detailed.jpg",
                }
            },
        )
        assert window.bottom_song_title.text() == "Detailed second title"
        assert window.bottom_song_artist.text() == "Detailed second artist"
        assert "Detailed second album" in window.now_artist.text()
        assert window.pending_online_track["title"] == "Detailed second title"

        window.on_online_playback_resolved(
            second_playback_request,
            "fixture_source",
            {
                "url": "https://example.invalid/audio.mp3",
                "headers": {},
                "title": "Resolved second title",
                "quality": "lossless",
                "format": "flac",
            },
        )
        assert window.current_media_item is not None
        assert window.current_media_item.stable_identity == "remote:fixture_source:second"
        assert window.current_media_item.title == "Resolved second title"
        assert window.bottom_song_title.text() == "Resolved second title"
        assert "LOSSLESS" in window.now_stats.text().upper()
        assert window.like_btn.isEnabled()

        shown: list[bytes] = []
        window.show_cover_from_bytes = lambda data: shown.append(data) or True
        window.presented_online_identity = window.current_media_item.stable_identity
        window.online_artwork_service._generation = 9
        window.on_online_artwork_ready(8, window.presented_online_identity, b"old-generation")
        window.on_online_artwork_ready(9, "remote:fixture_source:first", b"old-track")
        assert not shown
        window.on_online_artwork_ready(9, window.presented_online_identity, b"current")
        assert shown == [b"current"]

        window.request_online_playback(first)
        stale_metadata_request = window.pending_online_metadata_request
        with tempfile.TemporaryDirectory(prefix="hushplayer_metadata_local_") as temp_dir:
            local_path = Path(temp_dir) / "local.wav"
            with wave.open(str(local_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b"\x00\x00" * 800)
            window.load_lyrics_for_song = lambda *args, **kwargs: None
            window.update_cover = lambda *args, **kwargs: None
            window.load_song_for_playback(
                {
                    "title": "Local title",
                    "artist": "Local artist",
                    "album": "Local album",
                    "path": str(local_path),
                    "demo": False,
                }
            )
            assert window.current_media_item is not None
            assert window.current_media_item.media_type == "local"
            assert window.bottom_song_title.text() == "Local title"
            window.on_online_metadata_finished(
                stale_metadata_request,
                "fixture_source",
                {"metadata": {"title": "Late remote title"}},
            )
            assert window.bottom_song_title.text() == "Local title"
            window.media_player.stop()
            window.media_player.setSource(QUrl())
            app.processEvents()

        assert artwork_requests
        window.online_source_client.stop()
        window.deleteLater()
        app.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_metadata_merge()
    test_main_window_metadata_flow(app)
    print("online metadata smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
