from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.services.lyrics_cache import LyricsCache
from app.services.online_lyrics_service import OnlineLyricsService


class FakeLyricsClient(QObject):
    lyricFinished = Signal(int, str, dict)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.next_id = 1
        self.cancelled: list[int] = []

    def get_lyric(self, _source_id: str, _payload: dict, timeout_ms: int) -> int:
        assert timeout_ms == 10000
        request_id = self.next_id
        self.next_id += 1
        return request_id

    def cancel_request(self, request_id: int) -> bool:
        self.cancelled.append(request_id)
        return True


def online_fixture(track_id: str = "remote-1", lyrics: str = "") -> dict:
    return {
        "sourceId": "fixture_source",
        "sourceName": "Fixture Source",
        "id": track_id,
        "title": "Fixture Song",
        "artist": "Fixture Artist",
        "album": "Fixture Album",
        "duration": 125,
        "artwork": "https://example.invalid/cover.jpg",
        "lyrics": lyrics,
        "capabilities": {"playback": True, "download": True},
        "raw": {"id": track_id, "providerOnly": "kept-at-adapter-boundary"},
    }


def test_media_item_boundary() -> None:
    item = MediaItem.from_online(online_fixture())
    assert item.track_id == "remote-1"
    assert item.source_name == "Fixture Source"
    assert item.can_play and item.can_download
    canonical = item.to_dict()
    assert "songmid" not in canonical
    assert canonical["extra"]["provider_data"]["providerOnly"] == "kept-at-adapter-boundary"
    legacy = MediaItem.from_mapping(canonical).to_legacy_online()
    assert legacy["raw"]["providerOnly"] == "kept-at-adapter-boundary"
    local = MediaItem.from_mapping(
        {
            "media_type": "local",
            "source_id": "local",
            "track_id": "local-fixture",
            "title": "Local",
            "local_file_path": "C:/missing/local.flac",
        }
    )
    assert local.media_type == "local"


def test_lyrics_cache_and_stale_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_lyrics_cache_") as temp_dir:
        cache = LyricsCache(Path(temp_dir) / "online_lyrics.json")
        client = FakeLyricsClient()
        service = OnlineLyricsService(client, cache)
        ready: list[tuple[int, str, dict]] = []
        service.lyricsReady.connect(
            lambda generation, key, payload: ready.append(
                (generation, key, dict(payload))
            )
        )
        pending = MediaItem.from_online(online_fixture("pending"))
        service.request_lyrics(pending)
        assert client.next_id == 2
        embedded = MediaItem.from_online(
            online_fixture("embedded", "[00:01.00]First line\n[00:02.50]Second line")
        )
        service.request_lyrics(embedded)
        assert client.cancelled == [1]
        assert ready[-1][1] == embedded.stable_identity
        assert ready[-1][2]["type"] == "lrc"
        client.lyricFinished.emit(
            1,
            pending.source_id,
            {"rawLrc": "[00:00.00]Stale line"},
        )
        assert ready[-1][1] == embedded.stable_identity
        restored = LyricsCache(Path(temp_dir) / "online_lyrics.json").get(embedded)
        assert restored and restored["type"] == "lrc"
        service.deleteLater()
        client.deleteLater()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_media_item_boundary()
    test_lyrics_cache_and_stale_guard()
    print("shared media and lyrics smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
