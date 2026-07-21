from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, QProcess, QThread, Qt, Signal
from PySide6.QtWidgets import QApplication

from app.services.unified_search_service import UnifiedSearchService
from app.ui.main_window import MainWindow
from app.ui.unified_search_panel import UnifiedSearchResultsPanel


SOURCE_IDS = ("source_a", "source_b", "source_c", "source_d")


class FakeOnlineSourceClient(QObject):
    responseReceived = Signal(int, str, object)
    searchFinished = Signal(int, str, list)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.next_request_id = 1
        self.list_requests: list[int] = []
        self.search_requests: dict[int, tuple[str, str]] = {}
        self.cancelled: list[int] = []

    def _next_id(self) -> int:
        request_id = self.next_request_id
        self.next_request_id += 1
        return request_id

    def list_sources(self, timeout_ms: int = 8000) -> int:
        assert timeout_ms == 8000
        request_id = self._next_id()
        self.list_requests.append(request_id)
        return request_id

    def search(
        self,
        source_id: str,
        keyword: str,
        page: int = 1,
        search_type: str = "music",
        timeout_ms: int = 9000,
    ) -> int:
        assert page == 1
        assert search_type == "music"
        assert timeout_ms == 9000
        request_id = self._next_id()
        self.search_requests[request_id] = (str(source_id), str(keyword))
        return request_id

    def cancel_request(self, request_id: int) -> bool:
        self.cancelled.append(int(request_id))
        return True

    def answer_sources(self, request_id: int, sources: list[dict]) -> None:
        self.responseReceived.emit(request_id, "listSources", sources)

    def answer_search(self, request_id: int, results: list[dict]) -> None:
        source_id, _keyword = self.search_requests[request_id]
        self.searchFinished.emit(request_id, source_id, results)

    def fail_search(self, request_id: int, message: str) -> None:
        self.requestFailed.emit(request_id, "search", message)


def source_fixture(source_id: str, *, enabled: bool = True) -> dict:
    return {
        "id": source_id,
        "name": source_id.replace("_", " ").title(),
        "sourceUrl": f"https://example.invalid/{source_id}.js",
        "userInstalled": True,
        "enabled": enabled,
        "fileExists": True,
        "scanError": "",
        "sha256": (source_id * 8)[:64],
        "capabilities": {
            "search": True,
            "playback": True,
            "download": True,
        },
    }


def remote_results(source_id: str, count: int = 50) -> list[dict]:
    return [
        {
            "id": f"{source_id}-track-{index:03d}",
            "title": f"Online Track {index:03d}",
            "artist": f"Online Artist {index % 10}",
            "album": f"Online Album {index % 5}",
            "duration": 180 + index,
        }
        for index in range(count)
    ]


def prepare_isolated_storage(root: Path) -> None:
    data_dir = root / "appdata" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "ignored_imports.json": [],
        "library.json": [],
        "pending_imports.json": [],
        "playback_session.json": {},
        "playlists.json": {},
        "play_queue.json": [],
        "remote_tracks.json": {"version": 1, "tracks": {}},
        "settings.json": {},
        "stats.json": {},
        "lyrics_bindings.json": {},
    }
    for filename, value in defaults.items():
        (data_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "metadata_cache.json").write_text("{}", encoding="utf-8")
    registry_path = root / "appdata" / "source_runtime" / "source_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {"version": 1, "sources": [source_fixture(value) for value in SOURCE_IDS]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def process_events(app: QApplication, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def install_local_library(window: MainWindow, count: int) -> None:
    window.song_list.clear()
    window.song_identity_to_item = {}
    for index in range(count):
        window.song_list.addItem(
            window.create_song_list_item(
                {
                    "title": f"Local Track {index:04d}",
                    "artist": f"Local Artist {index % 20}",
                    "album": f"Local Album {index % 10}",
                    "path": f"C:/fixture/local_{index:04d}.mp3",
                    "added_at": index + 1,
                    "demo": False,
                }
            )
        )
    window.mark_library_list_dirty()


def attach_service(window: MainWindow) -> tuple[FakeOnlineSourceClient, UnifiedSearchService]:
    client = FakeOnlineSourceClient()
    service = UnifiedSearchService(client, window)
    service.resultsChanged.connect(window.on_unified_search_results_changed)
    service.sourceResultsChanged.connect(window.on_unified_search_source_results_changed)
    window.unified_search_service = service
    return client, service


def set_query_text(window: MainWindow, keyword: str) -> None:
    previous = window.search_input.blockSignals(True)
    window.search_input.setText(keyword)
    window.search_input.blockSignals(previous)


def start_query(
    window: MainWindow,
    client: FakeOnlineSourceClient,
    service: UnifiedSearchService,
    keyword: str,
    sources: list[dict] | None = None,
) -> dict[str, int]:
    set_query_text(window, keyword)
    service.schedule_search(keyword)
    service.start_pending_search()
    list_request = service._source_list_request
    assert list_request > 0
    client.answer_sources(
        list_request,
        list(sources or [source_fixture(value) for value in SOURCE_IDS]),
    )
    return {
        source_id: request_id
        for request_id, (source_id, request_keyword) in client.search_requests.items()
        if request_keyword == keyword
    }


class Metrics:
    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.decorations = 0
        self.group_updates = 0
        self.full_group_rebuilds = 0
        self.registry_reads = 0
        self.callback_durations: list[float] = []
        self.original_decorate = window.decorate_unified_search_result
        self.original_group_update = window.unified_search_panel.update_source_group
        self.original_full_rebuild = window.unified_search_panel._render_results
        self.original_list_sources = window.source_registry_manager.list_sources

        def counted_decorate(track: dict) -> dict:
            self.decorations += 1
            return self.original_decorate(track)

        def counted_group_update(*args, **kwargs):
            self.group_updates += 1
            return self.original_group_update(*args, **kwargs)

        def counted_full_rebuild(*args, **kwargs):
            self.full_group_rebuilds += 1
            return self.original_full_rebuild(*args, **kwargs)

        def counted_list_sources() -> list[dict]:
            self.registry_reads += 1
            return self.original_list_sources()

        window.decorate_unified_search_result = counted_decorate
        window.unified_search_panel.update_source_group = counted_group_update
        window.unified_search_panel._render_results = counted_full_rebuild
        window.source_registry_manager.list_sources = counted_list_sources

    def reset(self) -> None:
        self.decorations = 0
        self.group_updates = 0
        self.full_group_rebuilds = 0
        self.registry_reads = 0
        self.callback_durations.clear()

    def restore(self) -> None:
        self.window.decorate_unified_search_result = self.original_decorate
        self.window.unified_search_panel.update_source_group = self.original_group_update
        self.window.unified_search_panel._render_results = self.original_full_rebuild
        self.window.source_registry_manager.list_sources = self.original_list_sources


def run_order_benchmark(
    window: MainWindow,
    client: FakeOnlineSourceClient,
    service: UnifiedSearchService,
    metrics: Metrics,
    app: QApplication,
    label: str,
    order: list[str],
) -> None:
    window.invalidate_registered_source_snapshot()
    window.invalidate_local_song_match_index()
    metrics.reset()
    requests = start_query(window, client, service, f"benchmark-{label}")
    panel = window.unified_search_panel
    header_ids = {
        source_id: id(panel._group_headers[source_id]) for source_id in SOURCE_IDS
    }
    if label == "normal":
        panel.toggle_source_group("source_b")
        assert panel.is_source_collapsed("source_b") is True
    index_builds_before = window._local_song_match_index_build_count
    started = time.perf_counter()
    selected_key = ()
    preserved_scroll = 0
    for callback_index, source_id in enumerate(order):
        callback_started = time.perf_counter()
        client.answer_search(requests[source_id], remote_results(source_id))
        process_events(app, 1)
        metrics.callback_durations.append(
            (time.perf_counter() - callback_started) * 1000
        )
        assert {
            current_id: id(panel._group_headers[current_id])
            for current_id in SOURCE_IDS
        } == header_ids
        if callback_index == 0:
            header_row = panel.result_list.row(panel._group_headers[source_id])
            selected = panel.result_list.item(header_row + 1)
            panel.result_list.setCurrentItem(selected)
            selected_key = panel._track_key(panel.current_track())
            panel.result_list.verticalScrollBar().setValue(3)
            preserved_scroll = panel.result_list.verticalScrollBar().value()
        elif selected_key:
            assert panel._track_key(panel.current_track()) == selected_key
            assert panel.result_list.verticalScrollBar().value() == preserved_scroll
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert len(window.unified_search_results) == 200
    assert [
        value["source_id"] for value in window.unified_search_results[::50]
    ] == list(SOURCE_IDS)
    assert metrics.registry_reads == 1
    assert window._local_song_match_index_build_count - index_builds_before == 1
    assert metrics.decorations == 200
    assert metrics.full_group_rebuilds == 0
    assert metrics.group_updates == 4
    assert all(
        len(window.unified_search_results_by_source[source_id]) == 50
        for source_id in SOURCE_IDS
    )
    assert all(
        panel._source_states_by_id[source_id]["status"] == "success"
        for source_id in SOURCE_IDS
    )
    if label == "normal":
        source_b_header_row = panel.result_list.row(panel._group_headers["source_b"])
        next_item = panel.result_list.item(source_b_header_row + 1)
        assert next_item is not None
        assert str(next_item.data(panel.GROUP_SOURCE_ROLE) or "") == "source_c"
        panel.toggle_source_group("source_b")
        assert panel.is_source_collapsed("source_b") is False
        assert panel._track_key(panel.result_list.item(source_b_header_row + 1).data(
            Qt.ItemDataRole.UserRole
        ))[0] == "source_b"
    print(
        "online incremental benchmark: OK "
        f"order={label} registry_reads={metrics.registry_reads} "
        f"library_scans={window._local_song_match_index_build_count - index_builds_before} "
        f"decorations={metrics.decorations} full_rebuilds={metrics.full_group_rebuilds} "
        f"group_updates={metrics.group_updates} elapsed={elapsed_ms:.1f} ms "
        f"max_block={max(metrics.callback_durations):.1f} ms results=200"
    )


def test_failures_duplicates_and_stale_results(
    window: MainWindow,
    client: FakeOnlineSourceClient,
    service: UnifiedSearchService,
    app: QApplication,
) -> None:
    requests = start_query(window, client, service, "failure-cases")
    client.fail_search(requests["source_a"], "fixture failure")
    client.fail_search(requests["source_b"], "请求超时")
    client.answer_search(requests["source_c"], remote_results("source_c", 2))
    client.answer_search(requests["source_d"], remote_results("source_d", 1))
    states = window.unified_search_panel._source_states_by_id
    assert states["source_a"]["status"] == "failed"
    assert states["source_b"]["status"] == "timeout"
    assert states["source_c"]["status"] == "success"
    assert len(window.unified_search_results) == 3
    before = [dict(value) for value in window.unified_search_results]
    client.answer_search(requests["source_c"], remote_results("source_c", 5))
    client.answer_search(requests["source_b"], remote_results("source_b", 5))
    assert window.unified_search_results == before

    panel = window.unified_search_panel
    source_c_header_row = panel.result_list.row(panel._group_headers["source_c"])
    source_c_item = panel.result_list.item(source_c_header_row + 1)
    source_c_item_id = id(source_c_item)
    source_c_state = dict(panel._source_states_by_id["source_c"])
    assert panel.update_source_group(
        "source_c",
        "Source C",
        list(window.unified_search_results_by_source["source_c"]),
        source_c_state,
    ) is False
    assert id(panel.result_list.item(source_c_header_row + 1)) == source_c_item_id

    stale_requests = start_query(window, client, service, "stale-old")
    new_requests = start_query(window, client, service, "stale-new")
    client.answer_search(stale_requests["source_a"], remote_results("source_a", 4))
    assert window.unified_search_results == []
    client.answer_search(new_requests["source_d"], remote_results("source_d", 2))
    assert len(window.unified_search_results) == 2
    assert all(value["source_id"] == "source_d" for value in window.unified_search_results)

    reduced_sources = [source_fixture(value) for value in SOURCE_IDS[:3]]
    reduced_requests = start_query(
        window,
        client,
        service,
        "source-removed",
        reduced_sources,
    )
    assert "source_d" not in window.unified_search_panel._group_headers
    client.answer_search(reduced_requests["source_a"], remote_results("source_a", 1))
    process_events(app)


def test_cache_invalidation_and_actions(
    window: MainWindow,
    metrics: Metrics,
) -> None:
    sample = {
        **remote_results("source_a", 1)[0],
        "sourceId": "source_a",
        "sourceName": "Source A",
        "capabilities": {"playback": True, "download": True},
        "availability": "available",
    }
    window.invalidate_registered_source_snapshot()
    window.invalidate_local_song_match_index()
    metrics.reset()
    first = window.decorate_unified_search_result(sample)
    for _ in range(20):
        window.decorate_unified_search_result(sample)
    assert metrics.registry_reads == 1
    assert window._local_song_match_index_build_count >= 1
    assert first["can_play"] is True
    assert first["can_download"] is True

    window.invalidate_registered_source_snapshot()
    window.decorate_unified_search_result(sample)
    assert metrics.registry_reads == 2
    window.invalidate_registered_source_snapshot()
    assert window._source_registry_snapshot is None

    matching = {
        "title": first["title"],
        "artist": first["artist"],
        "album": first["album"],
        "path": "C:/fixture/matching.mp3",
        "demo": False,
    }
    window.song_list.addItem(window.create_song_list_item(matching))
    previous_builds = window._local_song_match_index_build_count
    window.mark_library_list_dirty()
    matched = window.decorate_unified_search_result(sample)
    assert matched["extra"]["local_existing"] is True
    assert window._local_song_match_index_build_count == previous_builds + 1

    matching_item = window.song_list.item(window.song_list.count() - 1)
    matching_data = dict(matching_item.data(Qt.ItemDataRole.UserRole))
    matching_data["title"] = "Renamed Track"
    matching_item.setData(Qt.ItemDataRole.UserRole, matching_data)
    window.mark_library_list_dirty()
    renamed = window.decorate_unified_search_result(sample)
    assert renamed["extra"]["local_existing"] is False
    window.song_list.takeItem(window.song_list.row(matching_item))
    window.mark_library_list_dirty()
    assert window.has_matching_local_song(sample) is False

    window.get_local_song_match_index()
    assert window._local_song_match_index is not None
    window.persist_remote_track(sample)
    assert window._local_song_match_index is None

    original_invalidate_source = window.unified_search_service.invalidate_source
    original_sync_remote = window.sync_remote_song_items
    original_refresh_states = window.refresh_unified_search_result_states
    invalidated_ids: list[str] = []
    try:
        window.unified_search_service.invalidate_source = (
            lambda source_id="": invalidated_ids.append(str(source_id))
        )
        window.sync_remote_song_items = lambda: None
        window.refresh_unified_search_result_states = lambda source_id="": None
        for change_id in ("added", "removed", "enabled", "disabled"):
            window._source_registry_snapshot = {"fixture": {"id": "fixture"}}
            window.on_custom_sources_changed(change_id)
            assert window._source_registry_snapshot is None
        assert invalidated_ids == ["added", "removed", "enabled", "disabled"]
    finally:
        window.unified_search_service.invalidate_source = original_invalidate_source
        window.sync_remote_song_items = original_sync_remote
        window.refresh_unified_search_result_states = original_refresh_states

    panel = UnifiedSearchResultsPanel()
    panel.begin_results(
        "actions",
        {
            "final": True,
            "resultCount": 1,
            "sources": [
                {
                    "sourceId": "source_a",
                    "sourceName": "Source A",
                    "status": "success",
                    "resultCount": 1,
                }
            ],
        },
    )
    panel.update_source_group("source_a", "Source A", [first], {
        "sourceId": "source_a",
        "sourceName": "Source A",
        "status": "success",
        "resultCount": 1,
    })
    item = panel.result_list.item(1)
    events: list[str] = []
    panel.playRequested.connect(lambda _track: events.append("play"))
    panel.likeRequested.connect(lambda _track: events.append("like"))
    panel.unlikeRequested.connect(lambda _track: events.append("unlike"))
    panel.addToPlaylistRequested.connect(
        lambda _track, _playlist_id: events.append("playlist")
    )
    panel.downloadRequested.connect(lambda _track: events.append("download"))
    panel.request_playback(item)
    panel.likeRequested.emit(dict(first))
    panel.unlikeRequested.emit(dict(first))
    panel.addToPlaylistRequested.emit(dict(first), "fixture")
    panel.downloadRequested.emit(dict(first))
    assert events == ["play", "like", "unlike", "playlist", "download"]
    panel.deleteLater()


def run_test(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_env = {
        name: os.environ.get(name)
        for name in (
            "HUSHPLAYER_APP_DATA_DIR",
            "HUSHPLAYER_CACHE_DIR",
            "HUSHPLAYER_LOG_DIR",
        )
    }
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    window = None
    metrics = None
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="hushplayer_online_incremental_"
    )
    try:
        root = Path(temporary_directory.name)
        prepare_isolated_storage(root)
        os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
        os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
        os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
        window = MainWindow()
        window.resize(1100, 720)
        window.show()
        process_events(app)
        install_local_library(window, 1000)
        client, service = attach_service(window)
        metrics = Metrics(window)
        run_order_benchmark(
            window,
            client,
            service,
            metrics,
            app,
            "normal",
            list(SOURCE_IDS),
        )
        run_order_benchmark(
            window,
            client,
            service,
            metrics,
            app,
            "reverse",
            list(reversed(SOURCE_IDS)),
        )
        random_order = list(SOURCE_IDS)
        random.Random(20260715).shuffle(random_order)
        run_order_benchmark(
            window,
            client,
            service,
            metrics,
            app,
            "random",
            random_order,
        )
        test_failures_duplicates_and_stale_results(window, client, service, app)
        test_cache_invalidation_and_actions(window, metrics)
        assert not [
            thread for thread in window.findChildren(QThread) if thread.isRunning()
        ]
        assert window.online_source_client.process.state() == QProcess.ProcessState.NotRunning
        print("online search incremental smoke: OK")
    finally:
        if metrics is not None:
            metrics.restore()
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        if window is not None:
            window.close()
            assert not window.isVisible()
            window.deleteLater()
            process_events(app, 10)
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        temporary_directory.cleanup()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    run_test(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
