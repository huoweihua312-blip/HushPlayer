from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import wave
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.models.media_item import MediaItem
from app.services.online_download_manager import OnlineDownloadManager
from app.services.online_source_client import OnlineSourceClient
from app.services.remote_track_store import RemoteTrackStore
from app.services.source_registry import SourceRegistryManager
from app.services.unified_search_service import UnifiedSearchService
from app.ui.online_source_pages import OnlineSearchPage


STAGING_ROOT = PROJECT_ROOT / "source_runtime" / "sources" / "staging"
TEST_ROOT = STAGING_ROOT / f"hushplayer_qprocess_{os.getpid()}"


def wait_until(predicate, timeout_ms: int = 5000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def prepare_fixture() -> Path:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    plugin_path = TEST_ROOT / "open_fixture.js"
    plugin_path.write_text(
        """module.exports = {
            search: async (keyword) => [{ id: `open-${keyword}`, title: `Open ${keyword}`, artist: "Fixture", album: "Tests", duration: 120 }],
            resolvePlayback: async (track) => {
                await new Promise((resolve) => setTimeout(resolve, Number(track.delay || 0)));
                if (track.fail) throw new Error("fixture failure");
                return { url: `http://127.0.0.1:8765/${track.id}.mp3`, headers: {} };
            }
        };\n""",
        encoding="utf-8",
    )
    independent_path = TEST_ROOT / "independent_fixture.js"
    independent_path.write_text(
        """module.exports = {
            search: async (keyword) => [{ id: `independent-${keyword}`, title: `Independent ${keyword}`, artist: "Fixture", album: "Tests", duration: 150 }],
            resolvePlayback: async () => ({ url: "http://127.0.0.1/fallback.wav" }),
            resolveDownload: async () => ({ url: "http://127.0.0.1/independent.flac", filename: "independent.flac" })
        };\n""",
        encoding="utf-8",
    )
    registry_path = TEST_ROOT / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "open_fixture",
                        "name": "Open fixture",
                        "filename": plugin_path.relative_to(PROJECT_ROOT / "source_runtime").as_posix(),
                        "enabled": True,
                        "userInstalled": True,
                        "sourceUrl": "https://example.invalid/open_fixture.js",
                        "contentPolicy": "open",
                        "capabilities": {
                            "search": True,
                            "playback": True,
                            "download": True,
                            "downloadViaPlayback": True,
                        },
                    },
                    {
                        "id": "independent_fixture",
                        "name": "Independent fixture",
                        "filename": independent_path.relative_to(PROJECT_ROOT / "source_runtime").as_posix(),
                        "enabled": True,
                        "userInstalled": True,
                        "sourceUrl": "https://example.invalid/independent_fixture.js",
                        "contentPolicy": "open",
                        "capabilities": {
                            "search": True,
                            "playback": True,
                            "download": True,
                            "downloadViaPlayback": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry_path


def test_qprocess_client(app: QApplication, registry_path: Path) -> None:
    os.environ["HUSHPLAYER_SOURCE_REGISTRY"] = str(registry_path)
    client = OnlineSourceClient(PROJECT_ROOT)
    resolved: list[tuple[int, dict]] = []
    failures: list[tuple[int, str, str]] = []
    stopped: list[bool] = []
    client.playbackResolved.connect(lambda request_id, _source, data: resolved.append((request_id, data)))
    client.requestFailed.connect(lambda request_id, action, message: failures.append((request_id, action, message)))
    client.processStopped.connect(lambda: stopped.append(True))
    assert client.start()
    assert wait_until(client.is_running)

    old_id = client.resolve_playback("open_fixture", {"id": "old", "delay": 250})
    current_id = client.resolve_playback("open_fixture", {"id": "current", "delay": 10})
    assert client.cancel_request(old_id)
    assert wait_until(lambda: any(item[0] == current_id for item in resolved))
    assert not any(item[0] == old_id for item in resolved)
    assert resolved[-1][1]["url"].endswith("/current.mp3")

    downloads: list[tuple[int, dict]] = []
    client.downloadResolved.connect(lambda request_id, _source, data: downloads.append((request_id, data)))
    fallback_download_id = client.resolve_download("open_fixture", {"id": "fallback"})
    assert wait_until(lambda: any(item[0] == fallback_download_id for item in downloads))
    fallback_resolution = next(item[1] for item in downloads if item[0] == fallback_download_id)
    assert fallback_resolution["viaPlayback"] is True
    assert fallback_resolution["url"].endswith("/fallback.mp3")

    independent_id = client.resolve_download("independent_fixture", {"id": "independent"})
    assert wait_until(lambda: any(item[0] == independent_id for item in downloads))
    independent = next(item[1] for item in downloads if item[0] == independent_id)
    assert independent["viaPlayback"] is False
    assert independent["filename"] == "independent.flac"

    error_id = client.resolve_playback("open_fixture", {"id": "error", "fail": True})
    assert wait_until(lambda: any(item[0] == error_id for item in failures))
    timeout_id = client.resolve_playback(
        "open_fixture",
        {"id": "timeout", "delay": 1800},
        timeout_ms=1000,
    )
    assert wait_until(lambda: any(item[0] == timeout_id for item in failures), 3000)
    assert "超时" in next(item[2] for item in failures if item[0] == timeout_id)

    client.stop()
    assert wait_until(lambda: bool(stopped))
    assert not client.is_running()
    client.deleteLater()
    app.processEvents()


def test_unified_qprocess_search(app: QApplication, registry_path: Path) -> None:
    os.environ["HUSHPLAYER_SOURCE_REGISTRY"] = str(registry_path)
    client = OnlineSourceClient(PROJECT_ROOT)
    service = UnifiedSearchService(client, debounce_ms=500)
    emissions: list[tuple[list, dict]] = []
    service.resultsChanged.connect(
        lambda _generation, _keyword, results, summary:
        emissions.append((list(results), dict(summary)))
    )
    service.schedule_search("fixture")
    service.start_pending_search()
    assert wait_until(lambda: bool(emissions) and emissions[-1][1].get("final"), 12000)
    assert {item["sourceId"] for item in emissions[-1][0]} == {
        "open_fixture",
        "independent_fixture",
    }
    service.shutdown()
    client.stop()
    client.deleteLater()
    app.processEvents()


def test_search_page_signals() -> None:
    client = OnlineSourceClient(PROJECT_ROOT)
    page = OnlineSearchPage(client)
    emitted: list[dict] = []
    page.play_requested.connect(emitted.append)

    unsupported = QListWidgetItem("unsupported")
    unsupported.setData(
        Qt.ItemDataRole.UserRole,
        {"sourceId": "closed", "id": "1", "capabilities": {"playback": False}},
    )
    page.request_playback(unsupported)
    assert not emitted
    assert "未启用播放能力" in page.status_label.text()

    supported = QListWidgetItem("supported")
    supported.setData(
        Qt.ItemDataRole.UserRole,
        {"sourceId": "open", "id": "2", "capabilities": {"playback": True}},
    )
    page.request_playback(supported)
    assert len(emitted) == 1
    assert "正在获取播放地址" in page.status_label.text()

    page.result_list.addItem(unsupported)
    page.result_list.setCurrentItem(unsupported)
    page.update_detail_buttons()
    assert not page.download_button.isEnabled()
    downloadable = QListWidgetItem("downloadable")
    downloadable.setData(
        Qt.ItemDataRole.UserRole,
        {"sourceId": "open", "id": "3", "capabilities": {"download": True}},
    )
    page.result_list.addItem(downloadable)
    page.result_list.setCurrentItem(downloadable)
    page.update_detail_buttons()
    assert page.download_button.isEnabled()
    page.deleteLater()
    client.deleteLater()


def test_download_manager() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_download_") as temp_dir:
        root = Path(temp_dir)
        payload = b"RIFF" + b"\x00" * 4092
        (root / "fixture.wav").write_bytes(payload)

        (root / "error.html").write_text("<!doctype html><html>error</html>", encoding="utf-8")

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, _format: str, *args) -> None:
                pass

            def do_GET(self) -> None:
                if self.path.endswith("fixture.wav") and self.headers.get("Referer") != "https://example.invalid/":
                    self.send_error(403)
                    return
                super().do_GET()

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(QuietHandler, directory=str(root)),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            manager = OnlineDownloadManager()
            finished: list[str] = []
            failures: list[str] = []
            manager.finished.connect(finished.append)
            manager.failed.connect(failures.append)
            target = root / "saved.wav"
            assert manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {
                        "Referer": "https://example.invalid/",
                        "User-Agent": "HushPlayer test",
                    },
                },
                str(target),
            )
            assert wait_until(lambda: bool(finished or failures))
            assert not failures
            assert target.read_bytes() == payload

            inferred_target = root / "inferred"
            assert manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {"Referer": "https://example.invalid/"},
                },
                str(inferred_target),
            )
            assert wait_until(lambda: len(finished) >= 2 or bool(failures))
            assert not failures
            assert (root / "inferred.wav").read_bytes() == payload

            assert not manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {"Authorization": "secret"},
                },
                str(root / "blocked.wav"),
            )
            assert "不受支持" in failures[-1]
            assert not (root / "blocked.wav").exists()
            assert not manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {"Referer": "safe\r\nInjected: value"},
                },
                str(root / "injected.wav"),
            )
            assert "换行" in failures[-1]
            assert not manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {"Proxy-Authorization": "secret"},
                },
                str(root / "proxy.wav"),
            )
            assert "不受支持" in failures[-1]

            html_target = root / "html_error"
            assert manager.start_download(
                {"url": f"http://127.0.0.1:{server.server_port}/error.html", "headers": {}},
                str(html_target),
            )
            assert wait_until(lambda: not manager.is_active())
            assert any("text/html" in failure or "HTML" in failure for failure in failures)
            assert not html_target.exists()
            manager.deleteLater()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_js_and_json_import_capabilities() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_registry_") as temp_dir:
        root = Path(temp_dir)
        manager = SourceRegistryManager(root)
        code = (
            b"module.exports = { resolvePlayback: async () => ({url: 'https://example.invalid/a.mp3'}), "
            b"resolveDownload: async () => ({url: 'https://example.invalid/a.mp3'}) };"
        )
        raw_candidate = manager.stage_bytes(code, "raw_source.js")
        assert raw_candidate["contentPolicy"] == "unknown"
        assert raw_candidate["capabilities"]["playback"] is False
        assert raw_candidate["capabilities"]["download"] is False

        custom_url = "HTTPS://Example.Invalid:443/sources/open.js#fragment"
        custom_candidate = manager.stage_bytes(
            code,
            "open.js",
            source_url=custom_url,
            content_policy="user_owned",
            user_installed=True,
        )
        assert custom_candidate["capabilities"]["playback"] is True
        assert custom_candidate["capabilities"]["download"] is True
        assert custom_candidate["capabilities"]["downloadViaPlayback"] is False
        installed = manager.install_candidate(custom_candidate, enabled=True)
        assert installed["enabled"] is True
        assert manager.find_by_source_url("https://example.invalid/sources/open.js")["id"] == installed["id"]
        update_candidate = manager.stage_bytes(
            code + b"\n// safe update",
            "open.js",
            source_url="https://example.invalid/sources/open.js",
            content_policy="user_owned",
            user_installed=True,
        )
        updated = manager.update_candidate(installed["id"], update_candidate)
        assert updated["id"] == installed["id"]
        assert updated["sha256"] != installed["sha256"]
        assert Path(updated["backupPath"]).is_file()

        playback_only = b"module.exports = { search: async () => [], getMediaSource: async () => ({url: 'https://example.invalid/a.mp3'}) };"
        first = manager.stage_bytes(
            playback_only,
            "playback_only.js",
            source_url="https://example.invalid/playback_only.js",
            content_policy="open",
            user_installed=True,
        )
        second = manager.stage_bytes(
            playback_only + b"\n// changed",
            "playback_only.js",
            source_url="https://example.invalid/playback_only.js",
            content_policy="open",
            user_installed=True,
        )
        assert first["id"] == second["id"]
        assert first["capabilities"]["playback"] is True
        assert first["capabilities"]["download"] is True
        assert first["capabilities"]["downloadViaPlayback"] is True

        no_media = manager.stage_bytes(
            b"module.exports = { search: async () => [] };",
            "no_media.js",
            source_url="https://example.invalid/no_media.js",
            content_policy="open",
            user_installed=True,
        )
        assert no_media["capabilities"]["playback"] is False
        assert no_media["capabilities"]["download"] is False

        json_candidate = manager.stage_bytes(
            json.dumps(
                {
                    "id": "json-track",
                    "title": "JSON track",
                    "url": "https://example.invalid/track.ogg",
                }
            ).encode("utf-8"),
            "track.json",
            source_url="https://example.invalid/track.json",
            content_policy="open",
            user_installed=True,
        )
        json_installed = manager.install_candidate(json_candidate, enabled=True)
        restarted = SourceRegistryManager(root)
        assert restarted.get_source(json_installed["id"])["sourceUrl"] == "https://example.invalid/track.json"

        user_sources = root / "user_sources"
        user_sources.mkdir(parents=True)
        (user_sources / "open_source.js").write_bytes(code)
        manifest = {
            "id": "open_source",
            "name": "Open source",
            "filename": "../user_sources/open_source.js",
            "contentPolicy": "open",
            "capabilities": {"playback": True, "download": True},
        }
        manifest_candidate = manager.stage_bytes(
            json.dumps(manifest).encode("utf-8"),
            "open_source.json",
        )
        assert manifest_candidate["capabilities"]["playback"] is True
        assert manifest_candidate["capabilities"]["download"] is True


def test_main_window_online_entry() -> None:
    from app.ui.main_window import MainWindow

    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    try:
        window = MainWindow()
        window.show_pending_playback_restore(
            {
                "title": "Local restore fixture",
                "artist": "Local artist",
                "album": "Local album",
                "path": "C:/Music/local-restore.flac",
            },
            12000,
        )
        assert window.now_open_folder_btn.text() == "打开文件位置"
        assert window.now_open_folder_btn.isEnabled()
        assert not hasattr(window, "source_manager_page")
        assert hasattr(window, "custom_source_manager_page")
        assert hasattr(window, "unified_search_service")
        assert hasattr(window, "unified_search_panel")
        with tempfile.TemporaryDirectory(prefix="hushplayer_local_regression_") as temp_dir:
            root = Path(temp_dir)
            paths = [root / "first.wav", root / "second.wav"]
            for path in paths:
                with wave.open(str(path), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(8000)
                    output.writeframes(b"\x00\x00" * 800)
            lrc_path = paths[0].with_suffix(".lrc")
            lrc_path.write_text("[00:00.00]本地第一行\n[00:01.00]本地第二行", encoding="utf-8")
            assert window.parse_lrc_file(lrc_path) == [
                (0, "本地第一行"),
                (1000, "本地第二行"),
            ]
            local_items = []
            for index, path in enumerate(paths, start=1):
                item = window.create_song_list_item(
                    {
                        "title": f"Local regression {index}",
                        "artist": "Local artist",
                        "album": "Local album",
                        "path": str(path),
                        "added_at": index,
                        "demo": False,
                    }
                )
                window.song_list.addItem(item)
                local_items.append(item)
            window.play_queue.clear()
            window.online_play_queue.clear()
            window.queue_return_state = None
            window.play_mode = "list_loop"
            original_load_lyrics = window.load_lyrics_for_song
            original_update_cover = window.update_cover
            window.load_lyrics_for_song = lambda *args, **kwargs: None
            window.update_cover = lambda *args, **kwargs: None
            source_before_browse = window.media_player.source().toString()
            window.select_song(local_items[0])
            assert window.media_player.source().toString() == source_before_browse
            assert window.current_song_path is None
            window.play_selected_song(local_items[0])
            assert window.current_song_path == window.normalize_song_path(str(paths[0]))
            window.play_next_song()
            assert window.current_song_path == window.normalize_song_path(str(paths[1]))
            window.play_previous_song()
            assert window.current_song_path == window.normalize_song_path(str(paths[0]))
            window.media_player.stop()
            window.media_player.setSource(QUrl())
            QApplication.processEvents()
            window.load_lyrics_for_song = original_load_lyrics
            window.update_cover = original_update_cover

        local_fixture_item = window.create_song_list_item(
            {
                "title": "q",
                "artist": "Local fixture",
                "album": "Local album",
                "path": "C:/Music/local-search-fixture.flac",
                "added_at": 1,
                "demo": False,
            }
        )
        window.song_list.addItem(local_fixture_item)
        window.search_input.setText("q")
        assert local_fixture_item.isHidden() is False
        assert "输入至少 2 个字符" in window.unified_search_panel.status_label.text()
        window.unified_search_panel.set_results(
            "q",
            [
                {
                    "sourceId": "open_fixture",
                    "sourceName": "Fixture",
                    "id": "search-fixture",
                    "title": "Search fixture",
                    "artist": "Artist",
                    "album": "Album",
                    "availability": "available",
                    "capabilities": {"playback": True, "download": True},
                }
            ],
            {"final": True},
        )
        window.search_input.clear()
        assert window.content_stack.currentWidget() is window.library_panel
        assert window.unified_search_panel.result_list.count() == 0
        assert local_fixture_item.isHidden() is False
        track = {
            "sourceId": "open_fixture",
            "id": "fixture",
            "title": "Online fixture",
            "artist": "Test artist",
            "album": "Test album",
        }
        preserved_context = {"kind": "library", "ordered_paths": ["C:/music/local.mp3"]}
        window.online_lyrics_service.request_lyrics = lambda _track: 1
        window.online_artwork_service.request = lambda _key, _url: 1
        window.current_song_path = "C:/music/local.mp3"
        window.playback_context = preserved_context
        window.pending_online_track = dict(track)
        window.pending_online_playback_request = 71
        window.on_online_playback_resolved(
            71,
            "open_fixture",
            {"url": "http://127.0.0.1:8765/header.mp3", "headers": {"Referer": "x"}},
        )
        assert window.current_song_path == "C:/music/local.mp3"
        assert window.current_track_kind == "local"
        assert "附加请求头" in window.online_search_page.status_label.text()

        window.pending_online_track = dict(track)
        window.pending_online_playback_request = 72
        window.on_online_playback_resolved(
            72,
            "open_fixture",
            {"url": "http://127.0.0.1:8765/audio.mp3", "headers": {}},
        )
        assert window.current_track_kind == "online"
        assert window.current_song_path is None
        assert window.current_online_track["title"] == track["title"]
        assert window.current_media_item.source_id == "open_fixture"
        assert window.playback_context is preserved_context
        assert window.media_player.source().toString().startswith("http://127.0.0.1:8765/")
        assert window.now_open_folder_btn.text() == "查看在线歌曲信息"
        assert window.now_open_folder_btn.isEnabled()
        assert window.like_btn.isEnabled()
        window.current_duration = 5000
        window.current_lyrics = [(0, "第一行"), (2000, "第二行")]
        window.displayed_lyrics_track_key = window.current_media_item.key
        window.lyrics_view.set_lyrics(window.current_lyrics)
        window.on_position_changed(2500)
        assert window.lyrics_view.current_index == 1

        window.online_play_queue.clear()
        queued_requests = []
        window.queue_media_item_next(track)
        assert len(window.online_play_queue) == 1
        window.request_online_playback = lambda value: queued_requests.append(value)
        assert window.play_next_queued_online_song() is True
        assert queued_requests[0]["sourceId"] == "open_fixture"
        assert window.online_play_queue == []
        assert window.parse_lrc_text("[00:01.25]第一行\n[00:02.500]第二行") == [
            (1250, "第一行"),
            (2500, "第二行"),
        ]

        with tempfile.TemporaryDirectory(prefix="hushplayer_remote_playlist_") as temp_dir:
            root = Path(temp_dir)
            window.playlists_file = root / "playlists.json"
            window.remote_tracks_file = root / "remote_tracks.json"
            window.remote_track_store = RemoteTrackStore(window.remote_tracks_file)
            window.remote_tracks = {}
            window.remote_tracks_error = ""
            window.playlists = {
                "liked": {"name": "我喜欢", "songs": ["C:/Music/local.flac"], "fixed": True},
                "custom": {"name": "测试歌单", "songs": [], "fixed": False},
            }
            remote_track = {
                "sourceId": "open_fixture",
                "sourceUrl": "https://example.invalid/open_fixture.js",
                "id": "remote-1",
                "title": "Remote fixture",
                "artist": "Remote artist",
                "album": "Remote album",
                "raw": {"id": "remote-1", "url": "https://temporary.invalid/track.mp3"},
            }
            window.like_online_track(remote_track)
            window.add_online_track_to_playlist(remote_track, "custom")
            stable_id = RemoteTrackStore.stable_id_for_track(remote_track)
            window.current_media_item = MediaItem.from_online(remote_track)
            window.current_track_kind = "online"
            window.update_like_button()
            assert window.like_btn.text() == "♥ 已收藏"
            window.toggle_like_current_song()
            assert stable_id not in window.get_playlist_remote_ids("liked")
            window.toggle_like_current_song()
            assert stable_id in window.get_playlist_remote_ids("liked")
            saved_playlists = json.loads(window.playlists_file.read_text(encoding="utf-8"))
            assert saved_playlists["liked"]["songs"] == ["C:/Music/local.flac"]
            assert saved_playlists["liked"]["remoteSongs"] == [stable_id]
            assert saved_playlists["custom"]["remoteSongs"] == [stable_id]
            assert RemoteTrackStore(window.remote_tracks_file).load_tracks()[stable_id]["title"] == "Remote fixture"
            downloaded_path = root / "downloaded.wav"
            downloaded_path.write_bytes(b"RIFF")
            downloaded_record = dict(window.remote_tracks[stable_id])
            downloaded_record["local_path"] = str(downloaded_path)
            window.remote_tracks[stable_id] = downloaded_record
            played_local: list[dict] = []
            window.load_song_for_playback = lambda song: played_local.append(dict(song))
            window.play_current_song = lambda: None
            window.play_unified_search_track(
                {**remote_track, "remoteStableId": stable_id, "availability": "available"}
            )
            assert played_local
            assert played_local[-1]["path"] == str(downloaded_path.resolve())
        window.media_player.stop()
        window.online_source_client.stop()
        window.deleteLater()
        QApplication.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    registry_path = prepare_fixture()
    try:
        test_qprocess_client(app, registry_path)
        test_unified_qprocess_search(app, registry_path)
        test_search_page_signals()
        test_download_manager()
        test_js_and_json_import_capabilities()
        test_main_window_online_entry()
        print("online playback QProcess/UI smoke: OK")
        return 0
    finally:
        resolved_root = TEST_ROOT.resolve()
        resolved_staging = STAGING_ROOT.resolve()
        if resolved_root.parent == resolved_staging and resolved_root.name.startswith("hushplayer_qprocess_"):
            shutil.rmtree(resolved_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
