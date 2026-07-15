from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QProcess, QThread, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.ui.main_window import MainWindow
from app.ui.search_page import SearchPage


SEARCH_TERMS = ("t", "tr", "tra", "trac", "track")


def process_events(app: QApplication, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()


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
    registry = root / "appdata" / "source_runtime" / "source_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"version": 1, "sources": []}, ensure_ascii=False),
        encoding="utf-8",
    )


def local_tracks(root: Path, count: int, chinese_artists: int = 0) -> list[dict]:
    return [
        {
            "title": f"Track {index:04d}",
            "artist": "中文歌手" if index < chinese_artists else "Fixture Artist",
            "album": f"Fixture Album {index % 8}",
            "path": str(root / f"track_{index:04d}.mp3"),
            "added_at": index + 1,
            "demo": False,
        }
        for index in range(count)
    ]


def install_tracks(
    window: MainWindow,
    app: QApplication,
    tracks: list[dict],
) -> None:
    window.cancel_pending_local_search()
    window.song_list.clear()
    window.song_identity_to_item = {}
    for track in tracks:
        window.song_list.addItem(window.create_song_list_item(track))
    window.current_library_view = "all"
    window.library_sort_field = None
    window.library_sort_descending = False
    window.clear_library_category_filter(refresh=False)
    window.mark_library_list_dirty()
    window.set_library_view("all")
    if window.search_input.text():
        window.search_input.clear()
    else:
        window.search_page.set_local_results("", [])
    window.last_applied_local_search_key = ""
    window.last_applied_local_search_revision = window.library_data_revision
    process_events(app)


class SearchMetrics:
    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.search_count = 0
        self.rebuild_count = 0
        self.search_durations: list[float] = []
        self.rebuild_durations: list[float] = []
        self.original_collect = window.collect_local_search_results
        self.original_set_items = window.search_page.local_view.set_items

        def counted_collect(keyword: str) -> list[dict]:
            started = time.perf_counter()
            result = self.original_collect(keyword)
            self.search_durations.append((time.perf_counter() - started) * 1000)
            self.search_count += 1
            return result

        def counted_set_items(
            items,
            empty_text: str = "没有找到歌曲",
            preserve_scroll: bool = False,
        ) -> None:
            started = time.perf_counter()
            self.original_set_items(
                items,
                empty_text=empty_text,
                preserve_scroll=preserve_scroll,
            )
            self.rebuild_durations.append((time.perf_counter() - started) * 1000)
            self.rebuild_count += 1

        window.collect_local_search_results = counted_collect
        window.search_page.local_view.set_items = counted_set_items

    def reset(self) -> None:
        self.search_count = 0
        self.rebuild_count = 0
        self.search_durations.clear()
        self.rebuild_durations.clear()

    def restore(self) -> None:
        self.window.collect_local_search_results = self.original_collect
        self.window.search_page.local_view.set_items = self.original_set_items

    def max_block_ms(self) -> float:
        return max([0.0, *self.search_durations, *self.rebuild_durations])


def wait_for_debounce(app: QApplication) -> None:
    QTest.qWait(260)
    process_events(app)


def clear_search(window: MainWindow, app: QApplication) -> None:
    window.search_input.setText("")
    process_events(app)
    assert not window.search_debounce_timer.isActive()
    assert window.search_page._local_results == []


def test_input_timing_and_normalization(
    window: MainWindow,
    app: QApplication,
    metrics: SearchMetrics,
) -> None:
    clear_search(window, app)
    metrics.reset()
    online_calls_before = len(window._test_online_schedule_calls)
    for term in SEARCH_TERMS:
        window.search_input.setText(term)
        process_events(app, 1)
    final_generation = window.pending_local_search_generation
    assert final_generation == window.local_search_generation
    wait_for_debounce(app)
    assert metrics.search_count == 1
    assert metrics.rebuild_count == 1
    assert window.search_page._keyword == "track"
    assert len(window.search_page._local_results) == 100
    assert [
        keyword
        for keyword, _local_only in window._test_online_schedule_calls[
            online_calls_before:
        ]
    ] == list(SEARCH_TERMS)

    clear_search(window, app)
    metrics.reset()
    window.search_input.setText("t")
    wait_for_debounce(app)
    window.search_input.setText("tr")
    wait_for_debounce(app)
    assert metrics.search_count == 2
    assert metrics.rebuild_count == 1

    window.search_input.setText("  TR  ")
    wait_for_debounce(app)
    assert metrics.search_count == 2
    assert not window.search_debounce_timer.isActive()

    clear_search(window, app)
    metrics.reset()
    window.search_input.setText("中")
    wait_for_debounce(app)
    window.search_input.setText("中文")
    wait_for_debounce(app)
    assert metrics.search_count == 2
    assert metrics.rebuild_count == 1
    assert len(window.search_page._local_results) == 12


def test_clear_and_stale_page_request(
    window: MainWindow,
    app: QApplication,
    metrics: SearchMetrics,
) -> None:
    before_clear = metrics.search_count
    window.search_input.clear()
    process_events(app)
    assert metrics.search_count == before_clear
    assert window.search_page._keyword == ""
    assert window.search_page._local_results == []
    assert window.content_stack.currentWidget() is window.library_panel

    metrics.reset()
    window.search_input.setText("track")
    process_events(app, 1)
    assert window.search_debounce_timer.isActive()
    window.show_full_lyrics_page()
    assert not window.search_debounce_timer.isActive()
    wait_for_debounce(app)
    assert metrics.search_count == 0
    assert window.content_stack.currentWidget() is window.full_lyrics_page

    window.show_search_page()
    assert window.search_debounce_timer.isActive()
    wait_for_debounce(app)
    assert metrics.search_count == 1
    assert window.search_page._keyword == "track"
    assert len(window.search_page._local_results) == 100


def item_identity(item) -> str:
    return MediaItem.from_mapping(
        item.data(Qt.ItemDataRole.UserRole)
    ).stable_identity


def test_result_reuse_state_and_signals(
    window: MainWindow,
    app: QApplication,
    metrics: SearchMetrics,
    context_calls: list[int],
) -> None:
    result_list = window.search_page.local_view.list_widget
    assert result_list.count() == 100
    selected_item = result_list.item(75)
    selected_identity = item_identity(selected_item)
    playing_item = result_list.item(5)
    playing_data = playing_item.data(Qt.ItemDataRole.UserRole)
    window.current_queue_identity = ""
    window.current_media_item = MediaItem.from_mapping(playing_data)
    window.current_song_path = window.current_media_item.local_file_path
    window.refresh_playing_song_indicators()
    result_list.setCurrentItem(selected_item)
    selected_item.setSelected(True)
    result_list.scrollToBottom()
    process_events(app)
    scroll_value = result_list.verticalScrollBar().value()
    assert scroll_value > result_list.verticalScrollBar().minimum()

    ordered_results = [
        dict(window.search_page._local_results[index])
        for index in range(len(window.search_page._local_results))
    ]
    reversed_results = list(reversed(ordered_results))
    rebuilds_before = metrics.rebuild_count
    assert window.search_page.set_local_results("track", reversed_results)
    process_events(app)
    assert metrics.rebuild_count == rebuilds_before + 1
    assert item_identity(result_list.currentItem()) == selected_identity
    assert result_list.currentItem().isSelected()
    assert result_list.verticalScrollBar().value() == scroll_value
    delegate = result_list.itemDelegate()
    assert delegate.playing_key_provider() == window.current_media_key()
    assert window.current_media_key() == window.current_media_item.stable_identity

    rebuilds_before = metrics.rebuild_count
    assert not window.search_page.set_local_results("TRACK", reversed_results)
    process_events(app)
    assert metrics.rebuild_count == rebuilds_before
    assert item_identity(result_list.currentItem()) == selected_identity
    assert result_list.verticalScrollBar().value() == scroll_value

    browsed: list[dict] = []
    played: list[dict] = []
    window.search_page.localBrowseRequested.connect(browsed.append)
    window.search_page.localPlayRequested.connect(played.append)
    context_calls[0] = 0
    current = result_list.currentItem()
    result_list.itemClicked.emit(current)
    result_list.itemDoubleClicked.emit(current)
    result_list.customContextMenuRequested.emit(QPoint(1, 1))
    assert len(browsed) == 1
    assert len(played) == 1
    assert context_calls[0] == 1


def run_benchmark(
    window: MainWindow,
    app: QApplication,
    metrics: SearchMetrics,
    root: Path,
    count: int,
) -> tuple[float, float]:
    install_tracks(window, app, local_tracks(root, count))
    metrics.reset()
    started = time.perf_counter()
    for term in SEARCH_TERMS:
        window.search_input.setText(term)
        process_events(app, 1)
    wait_for_debounce(app)
    elapsed_ms = (time.perf_counter() - started) * 1000
    max_block_ms = metrics.max_block_ms()
    assert metrics.search_count == 1
    assert metrics.rebuild_count == 1
    assert window.search_page._keyword == "track"
    assert len(window.search_page._local_results) == count
    print(
        "local search debounce benchmark: OK "
        f"tracks={count} searches={metrics.search_count} "
        f"rebuilds={metrics.rebuild_count} elapsed={elapsed_ms:.1f} ms "
        f"max_block={max_block_ms:.1f} ms"
    )
    return elapsed_ms, max_block_ms


def run_test(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_browse = MainWindow.browse_media_item
    original_play = MainWindow.play_media_item
    original_context = SearchPage._show_local_context_menu
    original_env = {
        name: os.environ.get(name)
        for name in (
            "HUSHPLAYER_APP_DATA_DIR",
            "HUSHPLAYER_CACHE_DIR",
            "HUSHPLAYER_LOG_DIR",
        )
    }
    context_calls = [0]
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    MainWindow.browse_media_item = lambda self, value: None
    MainWindow.play_media_item = lambda self, value: None
    SearchPage._show_local_context_menu = (
        lambda self, position: context_calls.__setitem__(0, context_calls[0] + 1)
    )
    window = None
    metrics = None
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_local_search_") as temp_dir:
            root = Path(temp_dir)
            prepare_isolated_storage(root)
            os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
            os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
            os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
            window = MainWindow()
            window._test_online_schedule_calls = []
            window.unified_search_service.schedule_search = (
                lambda keyword, local_only=False: window._test_online_schedule_calls.append(
                    (str(keyword), bool(local_only))
                )
            )
            window.resize(1100, 720)
            window.show()
            process_events(app)
            metrics = SearchMetrics(window)

            install_tracks(window, app, local_tracks(root, 100, chinese_artists=12))
            test_input_timing_and_normalization(window, app, metrics)
            test_clear_and_stale_page_request(window, app, metrics)
            test_result_reuse_state_and_signals(
                window,
                app,
                metrics,
                context_calls,
            )
            run_benchmark(window, app, metrics, root, 300)
            run_benchmark(window, app, metrics, root, 1000)

            assert not [
                thread
                for thread in window.findChildren(QThread)
                if thread.isRunning()
            ]
            assert window.online_source_client.process.state() == QProcess.ProcessState.NotRunning
            print("local search debounce smoke: OK")
    finally:
        if metrics is not None:
            metrics.restore()
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        MainWindow.browse_media_item = original_browse
        MainWindow.play_media_item = original_play
        SearchPage._show_local_context_menu = original_context
        if window is not None:
            window.cancel_pending_local_search()
            window.close()
            assert not window.isVisible()
            window.deleteLater()
            process_events(app, 10)
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    run_test(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
