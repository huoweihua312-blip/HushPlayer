from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
        self.next_request_id = 0
        self.calls: list[tuple[int, str, dict, int]] = []
        self.cancelled: list[int] = []

    def get_lyric(
        self,
        source_id: str,
        music_item: dict,
        timeout_ms: int = 25000,
    ) -> int:
        self.next_request_id += 1
        request_id = self.next_request_id
        self.calls.append((request_id, source_id, dict(music_item), timeout_ms))
        return request_id

    def cancel_request(self, request_id: int) -> bool:
        self.cancelled.append(request_id)
        return True


def remote_item(source_id: str, track_id: str, title: str = "Fixture") -> MediaItem:
    return MediaItem.from_online(
        {
            "sourceId": source_id,
            "sourceName": f"Source {source_id}",
            "id": track_id,
            "title": title,
            "artist": "Test artist",
            "album": "Test album",
            "capabilities": {"playback": True},
        }
    )


def request_and_emit(
    service: OnlineLyricsService,
    client: FakeLyricsClient,
    item: MediaItem,
    result: dict,
) -> tuple[int, int]:
    generation = service.request_lyrics(item)
    request_id = client.calls[-1][0]
    client.lyricFinished.emit(request_id, item.source_id, result)
    return generation, request_id


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="hushplayer_online_lyrics_") as temp_dir:
        cache_path = Path(temp_dir) / "online_lyrics.json"
        cache = LyricsCache(cache_path)
        first = remote_item("fixture_a", "same-id", "First")
        second_source = remote_item("fixture_b", "same-id", "First")
        second_track = remote_item("fixture_a", "second-id", "First")
        assert LyricsCache.key_for(first) != LyricsCache.key_for(second_source)
        assert LyricsCache.key_for(first) != LyricsCache.key_for(second_track)
        assert first.stable_identity == "remote:fixture_a:same-id"

        client = FakeLyricsClient()
        service = OnlineLyricsService(client, cache)
        statuses: list[tuple[int, str, str]] = []
        payloads: list[tuple[int, str, dict]] = []
        service.statusChanged.connect(
            lambda generation, key, message: statuses.append((generation, key, message))
        )
        service.lyricsReady.connect(
            lambda generation, key, payload: payloads.append(
                (generation, key, dict(payload))
            )
        )

        generation, _request_id = request_and_emit(
            service,
            client,
            first,
            {"available": True, "rawLrc": "[00:00.00]第一行\n[00:01.00]第二行"},
        )
        assert statuses[0] == (generation, first.stable_identity, "正在获取歌词")
        assert payloads[-1][1] == first.stable_identity
        assert payloads[-1][2]["type"] == "lrc"
        assert "第一行" in payloads[-1][2]["text"]
        raw_cache = cache_path.read_bytes()
        assert not raw_cache.startswith(b"\xef\xbb\xbf")
        raw_cache.decode("utf-8")
        cache_document = json.loads(raw_cache.decode("utf-8"))
        assert all(
            len(key) == 64 and set(key) <= set("0123456789abcdef")
            for key in cache_document["entries"]
        )

        unavailable_cache_path = Path(temp_dir) / "cache_target"
        unavailable_cache_path.mkdir()
        unavailable_cache = LyricsCache(unavailable_cache_path)
        unavailable_cache.put(
            remote_item("fixture_a", "cache-write-failure"),
            OnlineLyricsService._payload("仍然可以显示", "fixture"),
        )

        persistent_client = FakeLyricsClient()
        persistent_service = OnlineLyricsService(
            persistent_client,
            LyricsCache(cache_path),
        )
        persistent_payloads: list[dict] = []
        persistent_service.lyricsReady.connect(
            lambda _generation, _key, payload: persistent_payloads.append(dict(payload))
        )
        persistent_service.request_lyrics(first)
        assert not persistent_client.calls
        assert persistent_payloads[-1]["source"].startswith("本地缓存/")
        persistent_service.request_lyrics(first)
        assert not persistent_client.calls
        assert persistent_payloads[-1]["source"].startswith("内存缓存/")

        plain = remote_item("fixture_a", "plain")
        request_and_emit(
            service,
            client,
            plain,
            {"available": True, "data": {"plainLyrics": "纯文本第一行\n纯文本第二行"}},
        )
        assert payloads[-1][2]["type"] == "plain"

        line_array = remote_item("fixture_a", "line-array")
        request_and_emit(
            service,
            client,
            line_array,
            {
                "available": True,
                "result": {"lines": [{"text": "数组第一行"}, {"words": "数组第二行"}]},
            },
        )
        assert payloads[-1][2]["text"] == "数组第一行\n数组第二行"

        no_lyrics = remote_item("fixture_a", "none")
        calls_before_none = len(client.calls)
        request_and_emit(
            service,
            client,
            no_lyrics,
            {"available": False, "rawLrc": "", "raw": {}},
        )
        assert payloads[-1][2]["type"] == "none"
        assert payloads[-1][2]["not_found"] is True
        service.request_lyrics(no_lyrics)
        assert len(client.calls) == calls_before_none + 1
        assert payloads[-1][2]["source"].startswith("内存缓存/")

        timeout_item = remote_item("fixture_a", "timeout")
        timeout_generation = service.request_lyrics(timeout_item)
        timeout_request = client.calls[-1][0]
        client.requestFailed.emit(timeout_request, "getLyric", "请求超时")
        assert payloads[-1][0] == timeout_generation
        assert payloads[-1][2]["type"] == "error"
        assert payloads[-1][2]["error"] is True
        calls_before_retry = len(client.calls)
        service.request_lyrics(timeout_item)
        assert len(client.calls) == calls_before_retry + 1

        malformed = remote_item("fixture_a", "malformed")
        request_and_emit(
            service,
            client,
            malformed,
            {"available": True, "data": {"unexpected": 123}},
        )
        assert payloads[-1][2]["type"] == "error"
        assert "格式异常" in payloads[-1][2]["source"]

        race_first = remote_item("fixture_a", "race-first")
        race_second = remote_item("fixture_a", "race-second")
        first_generation = service.request_lyrics(race_first)
        first_request = client.calls[-1][0]
        second_generation = service.request_lyrics(race_second)
        second_request = client.calls[-1][0]
        assert first_request in client.cancelled
        payload_count = len(payloads)
        client.lyricFinished.emit(
            first_request,
            race_first.source_id,
            {"available": True, "rawLrc": "[00:00.00]过期歌词"},
        )
        assert len(payloads) == payload_count
        client.lyricFinished.emit(
            second_request,
            race_second.source_id,
            {"available": True, "rawLrc": "[00:00.00]当前歌词"},
        )
        assert first_generation != second_generation
        assert payloads[-1][0] == second_generation
        assert payloads[-1][1] == race_second.stable_identity
        assert "当前歌词" in payloads[-1][2]["text"]

        service.deleteLater()
        persistent_service.deleteLater()
        client.deleteLater()
        persistent_client.deleteLater()
        app.processEvents()

    print("online lyrics/cache/race smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
