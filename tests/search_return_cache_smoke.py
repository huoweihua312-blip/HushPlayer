from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QThread, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.models.media_item import MediaItem
from app.services.playlist_membership import PlaylistMembership
from app.ui.main_window import MainWindow


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


def local_tracks(root: Path, count: int) -> list[dict]:
    return [
        {
            "title": f"本地歌曲 {index:04d}",
            "artist": f"歌手 {index % 2}",
            "album": f"专辑 {index % 5}",
            "path": str(root / f"track_{index:04d}.mp3"),
            "added_at": index + 1,
            "demo": False,
        }
        for index in range(count)
    ]


def normalized_playlist(
    window: MainWindow,
    name: str,
    paths: list[str],
    *,
    fixed: bool,
) -> dict:
    playlist = {
        "name": name,
        "songs": list(paths),
        "remoteSongs": [],
        "fixed": fixed,
    }
    PlaylistMembership.normalize_playlist(
        playlist,
        window.normalize_song_path,
        anchor_ms=1_700_000_000_000,
    )
    return playlist


def install_tracks(window: MainWindow, tracks: list[dict]) -> None:
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


def prepare_cached_view(
    window: MainWindow,
    app: QApplication,
    view_name: str,
) -> None:
    if window.content_stack.currentWidget() is not window.library_panel:
        window.show_library_container()
    window.clear_library_category_filter(refresh=False)
    window.mark_library_list_dirty()
    window.set_library_view(view_name)
    process_events(app)
    assert window.current_library_view == view_name
    assert not window.library_list_dirty
    assert window.current_library_view_key() == window.last_library_view_key


def assert_cached_return(
    window: MainWindow,
    app: QApplication,
    filter_calls: list[int],
    view_name: str,
) -> None:
    prepare_cached_view(window, app, view_name)
    filter_calls[0] = 0
    window.show_search_page()
    assert window.can_reuse_library_view_after_search()
    window.return_to_library_view()
    process_events(app)
    assert filter_calls[0] == 0
    assert window.content_stack.currentWidget() is window.library_panel
    assert window.current_library_view == view_name


def test_cached_views(
    window: MainWindow,
    app: QApplication,
    filter_calls: list[int],
) -> None:
    assert_cached_return(window, app, filter_calls, "all")
    assert_cached_return(window, app, filter_calls, "liked")
    assert_cached_return(window, app, filter_calls, "playlist:road")


def test_other_return_path_still_refreshes(
    window: MainWindow,
    app: QApplication,
    filter_calls: list[int],
) -> None:
    prepare_cached_view(window, app, "all")
    filter_calls[0] = 0
    window.content_stack.setCurrentWidget(window.custom_source_manager_page)
    window.return_to_library_view()
    assert filter_calls[0] == 1


def test_mutations_force_refresh(
    window: MainWindow,
    app: QApplication,
    filter_calls: list[int],
    tracks: list[dict],
) -> None:
    prepare_cached_view(window, app, "all")
    target_path = tracks[-1]["path"]
    assert not window.is_song_liked(target_path)
    filter_calls[0] = 0
    window.show_search_page()
    entry_revision = window.search_entry_library_revision
    assert window.add_local_path_to_playlist(target_path, "liked")
    assert window.library_data_revision > entry_revision
    # Even if another refresh remembers the new key, the entry revision still
    # proves that the library changed while search was open.
    window.remember_library_view_key()
    assert not window.can_reuse_library_view_after_search()
    window.return_to_library_view()
    assert filter_calls[0] == 1

    prepare_cached_view(window, app, "all")
    delete_item = window.find_song_item_by_identity(
        MediaItem.from_local(tracks[-2]).stable_identity
    )
    assert delete_item is not None
    window.song_list.clearSelection()
    window.song_list.setCurrentItem(delete_item)
    delete_item.setSelected(True)
    filter_calls[0] = 0
    window.show_search_page()
    original_question = QMessageBox.question
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    try:
        window.remove_selected_songs_from_library()
    finally:
        QMessageBox.question = original_question
    calls_before_return = filter_calls[0]
    assert calls_before_return >= 1
    assert window.library_list_dirty
    window.return_to_library_view()
    assert filter_calls[0] == calls_before_return + 1

    prepare_cached_view(window, app, "all")
    filter_calls[0] = 0
    window.show_search_page()
    window.mark_library_list_dirty()
    assert not window.can_reuse_library_view_after_search()
    window.return_to_library_view()
    assert filter_calls[0] == 1


def test_cached_state_and_interactions(
    window: MainWindow,
    app: QApplication,
    filter_calls: list[int],
    interaction_counts: dict[str, int],
) -> None:
    prepare_cached_view(window, app, "all")
    window.library_sort_field = "title"
    window.library_sort_descending = True
    window.sort_song_list_for_current_view(force=True)
    window.apply_library_category_filter("artist", "歌手 0")

    visible_items = [
        window.song_list.item(row)
        for row in range(window.song_list.count())
        if not window.song_list.item(row).isHidden()
    ]
    assert len(visible_items) >= 30
    playing_item = visible_items[0]
    selected_item = visible_items[-1]
    playing_data = window.get_song_data_from_item(playing_item)
    selected_identity = window.track_identity_for_song_data(
        window.get_song_data_from_item(selected_item)
    )
    window.current_queue_identity = ""
    window.current_media_item = MediaItem.from_local(playing_data)
    window.current_song_path = playing_data["path"]
    window.refresh_playing_song_indicators()
    window.song_list.clearSelection()
    window.song_list.setCurrentItem(selected_item)
    selected_item.setSelected(True)
    window.song_list.scrollToBottom()
    process_events(app)
    scroll_value = window.song_list.verticalScrollBar().value()
    assert scroll_value > window.song_list.verticalScrollBar().minimum()
    assert playing_item.text().startswith("▶ ")

    filter_calls[0] = 0
    window.show_search_page()
    assert window.can_reuse_library_view_after_search()
    window.return_to_library_view()
    process_events(app)

    assert filter_calls[0] == 0
    assert window.current_library_view == "all"
    assert window.library_category_filter_type == "artist"
    assert window.library_category_filter_value == "歌手 0"
    assert window.library_sort_field == "title"
    assert window.library_sort_descending is True
    assert window.song_list.verticalScrollBar().value() == scroll_value
    current_item = window.song_list.currentItem()
    assert current_item is not None
    assert window.track_identity_for_song_data(
        window.get_song_data_from_item(current_item)
    ) == selected_identity
    assert selected_item.isSelected()
    assert playing_item.text().startswith("▶ ")

    for name in interaction_counts:
        interaction_counts[name] = 0
    window.song_list.itemClicked.emit(selected_item)
    window.song_list.itemDoubleClicked.emit(selected_item)
    window.song_list.customContextMenuRequested.emit(QPoint(1, 1))
    assert interaction_counts == {"single": 1, "double": 1, "context": 1}


def benchmark_cached_return(
    window: MainWindow,
    app: QApplication,
    original_filter,
    root: Path,
) -> tuple[float, float]:
    tracks = local_tracks(root, 1000)
    install_tracks(window, tracks)
    process_events(app)
    full_times: list[float] = []
    cached_times: list[float] = []

    for _ in range(3):
        window.remember_library_view_key()
        window.show_search_page()
        window.mark_library_list_dirty()
        started = time.perf_counter()
        window.return_to_library_view()
        full_times.append((time.perf_counter() - started) * 1000)

        original_filter("")
        window.remember_library_view_key()
        window.show_search_page()
        started = time.perf_counter()
        window.return_to_library_view()
        cached_times.append((time.perf_counter() - started) * 1000)

    full_ms = statistics.median(full_times)
    cached_ms = statistics.median(cached_times)
    assert cached_ms < full_ms
    assert cached_ms < 50
    print(
        "search return cache benchmark: OK "
        f"tracks=1000 full={full_ms:.1f} ms cached={cached_ms:.1f} ms"
    )
    return full_ms, cached_ms


def run_test(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_select = MainWindow.select_song
    original_play = MainWindow.play_selected_song
    original_context = MainWindow.show_song_context_menu
    original_env = {
        name: os.environ.get(name)
        for name in (
            "HUSHPLAYER_APP_DATA_DIR",
            "HUSHPLAYER_CACHE_DIR",
            "HUSHPLAYER_LOG_DIR",
        )
    }
    interaction_counts = {"single": 0, "double": 0, "context": 0}
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    MainWindow.select_song = lambda self, item: interaction_counts.__setitem__(
        "single", interaction_counts["single"] + 1
    )
    MainWindow.play_selected_song = lambda self, item: interaction_counts.__setitem__(
        "double", interaction_counts["double"] + 1
    )
    MainWindow.show_song_context_menu = lambda self, position: interaction_counts.__setitem__(
        "context", interaction_counts["context"] + 1
    )
    window = None
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_search_return_cache_") as temp_dir:
            root = Path(temp_dir)
            prepare_isolated_storage(root)
            os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
            os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
            os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
            window = MainWindow()
            MainWindow.select_song = original_select
            MainWindow.play_selected_song = original_play
            MainWindow.show_song_context_menu = original_context
            window.resize(1100, 720)
            window.show()
            process_events(app)

            tracks = local_tracks(root, 100)
            paths = [track["path"] for track in tracks]
            window.playlists = {
                "liked": normalized_playlist(
                    window,
                    "我喜欢",
                    paths[:30],
                    fixed=True,
                ),
                "road": normalized_playlist(
                    window,
                    "通勤",
                    paths[20:60],
                    fixed=False,
                ),
            }
            window.invalidate_playlist_membership_snapshot()
            install_tracks(window, tracks)
            process_events(app)

            original_filter = window.filter_song_list
            filter_calls = [0]

            def counted_filter(keyword: str) -> None:
                filter_calls[0] += 1
                original_filter(keyword)

            window.filter_song_list = counted_filter
            test_cached_views(window, app, filter_calls)
            test_other_return_path_still_refreshes(window, app, filter_calls)
            test_mutations_force_refresh(window, app, filter_calls, tracks)
            test_cached_state_and_interactions(
                window,
                app,
                filter_calls,
                interaction_counts,
            )
            window.filter_song_list = original_filter
            benchmark_cached_return(window, app, original_filter, root)

            running_threads = [
                thread
                for thread in window.findChildren(QThread)
                if thread.isRunning()
            ]
            assert not running_threads
            print("search return cache smoke: OK")
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        MainWindow.select_song = original_select
        MainWindow.play_selected_song = original_play
        MainWindow.show_song_context_menu = original_context
        if window is not None:
            window.hide()
            window.deleteLater()
            process_events(app)
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
