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
from PySide6.QtWidgets import QApplication, QLabel

from app.models.media_item import MediaItem
from app.services.lyrics_cache import LyricsCache
from app.services.online_lyrics_service import OnlineLyricsService
from app.ui.library_page import GroupedLibraryView, LibraryPage
from app.ui.search_page import SearchPage
from app.ui.track_details_panel import TrackDetailsPanel


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


def test_lazy_library_grouping(app: QApplication) -> None:
    tracks = [
        MediaItem.from_local(
            {
                "title": "One",
                "artist": "Artist A",
                "album": "Album A",
                "path": "C:/missing/one.flac",
            }
        ).to_dict(),
        MediaItem.from_local(
            {
                "title": "Two",
                "artist": "Artist A",
                "album": "Album A",
                "path": "C:/missing/two.flac",
            }
        ).to_dict(),
        MediaItem.from_local(
            {
                "title": "Three",
                "artist": "Artist B",
                "album": "Album B",
                "path": "C:/missing/three.flac",
            }
        ).to_dict(),
    ]
    artist_groups = GroupedLibraryView.build_groups(tracks, "artist")
    album_groups = GroupedLibraryView.build_groups(tracks, "album")
    assert [len(group["tracks"]) for group in artist_groups] == [2, 1]
    assert len(album_groups) == 2
    page = LibraryPage()
    page.set_scope("全部歌曲", tracks, "fixture:1")
    assert page.artist_view.group_list.count() == 0
    page.show_mode("artists")
    for _ in range(5):
        app.processEvents()
    assert page.content_stack.currentWidget() is page.artist_view
    assert page.artist_view.group_list.count() == 2
    page.artist_view.open_group(page.artist_view.group_list.item(0))
    assert page.artist_view.detail_tracks.list_widget.count() == 2
    page.deleteLater()


def test_search_page_tabs() -> None:
    page = SearchPage()
    local = MediaItem.from_local(
        {
            "title": "Local Result",
            "artist": "Local Artist",
            "album": "Local Album",
            "path": "C:/missing/local-result.flac",
        }
    ).to_dict()
    page.set_local_results("result", [local])
    assert page.current_tab() == "local"
    assert page.local_view.list_widget.count() == 1
    page.set_online_results("result", [online_fixture()], {"final": True})
    assert page.online_results.result_list.count() == 2
    page.show_tab("online")
    assert page.current_tab() == "online"
    page.show_tab("local")
    assert page.local_view.list_widget.count() == 1
    page.deleteLater()


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
        assert ready[-1][1] == embedded.key
        assert ready[-1][2]["type"] == "lrc"
        client.lyricFinished.emit(
            1,
            pending.source_id,
            {"rawLrc": "[00:00.00]Stale line"},
        )
        assert ready[-1][1] == embedded.key
        restored = LyricsCache(Path(temp_dir) / "online_lyrics.json").get(embedded)
        assert restored and restored["type"] == "lrc"
        service.deleteLater()
        client.deleteLater()


def test_track_details_separate_local_and_online() -> None:
    online_panel = TrackDetailsPanel(MediaItem.from_online(online_fixture()))
    online_text = "\n".join(label.text() for label in online_panel.findChildren(QLabel))
    assert "Fixture Source" in online_text
    assert "文件路径" not in online_text
    local_panel = TrackDetailsPanel(
        MediaItem.from_local(
            {
                "title": "Local",
                "artist": "Artist",
                "album": "Album",
                "path": "C:/missing/local.flac",
            }
        ),
        {"play_count": 3, "total_listen_time": 90000},
    )
    local_text = "\n".join(label.text() for label in local_panel.findChildren(QLabel))
    assert "文件路径" in local_text
    assert "播放次数" in local_text
    online_panel.deleteLater()
    local_panel.deleteLater()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_media_item_boundary()
    test_lazy_library_grouping(app)
    test_search_page_tabs()
    test_lyrics_cache_and_stale_guard()
    test_track_details_separate_local_and_online()
    print("UI restructure smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
