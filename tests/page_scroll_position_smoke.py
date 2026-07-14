from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.search_page import SearchPage
from app.ui.track_list_view import TrackListView


def local_tracks(count: int) -> list[dict]:
    return [
        {
            "title": f"本地歌曲 {index:03d}",
            "artist": "本机测试歌手",
            "album": "本机测试专辑",
            "path": f"C:/fixtures/scroll-{index:03d}.mp3",
            "media_type": "local",
        }
        for index in range(count)
    ]


def online_tracks(count: int) -> list[dict]:
    return [
        {
            "title": f"在线歌曲 {index:03d}",
            "artist": "本机测试歌手",
            "album": "本机测试专辑",
            "media_type": "online",
            "source_id": "custom_source_scroll_fixture",
            "source_name": "本机模拟来源",
            "track_id": f"remote-{index:03d}",
            "availability": "available",
            "can_play": True,
            "can_download": False,
        }
        for index in range(count)
    ]


def process_events(app: QApplication) -> None:
    for _ in range(5):
        app.processEvents()


def put_at_bottom(view, app: QApplication) -> None:
    view.scrollToBottom()
    process_events(app)
    assert view.verticalScrollBar().value() > view.verticalScrollBar().minimum()


def assert_at_top(view) -> None:
    assert view.verticalScrollBar().value() == view.verticalScrollBar().minimum()


def test_rebuilt_track_list_starts_at_top(app: QApplication) -> None:
    view = TrackListView()
    view.resize(760, 320)
    view.show()
    tracks = local_tracks(80)
    view.set_items(tracks)
    process_events(app)
    view.list_widget.setCurrentRow(79)
    put_at_bottom(view.list_widget, app)
    view.set_items(tracks)
    process_events(app)
    assert_at_top(view.list_widget)
    view.hide()
    view.deleteLater()


def test_search_tabs_start_at_top(app: QApplication) -> None:
    page = SearchPage()
    page.resize(900, 560)
    page.show()
    page.set_local_results("测试", local_tracks(80))
    page.set_online_results("测试", online_tracks(80), {"final": True})
    process_events(app)

    page.show_tab("local")
    process_events(app)
    put_at_bottom(page.local_view.list_widget, app)
    page.show_tab("online")
    page.show_tab("local")
    process_events(app)
    assert_at_top(page.local_view.list_widget)

    page.show_tab("online")
    process_events(app)
    put_at_bottom(page.online_results.result_list, app)
    page.show_tab("local")
    page.show_tab("online")
    process_events(app)
    assert_at_top(page.online_results.result_list)
    page.hide()
    page.deleteLater()


def test_main_page_navigation_starts_at_top(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    window = None
    try:
        window = MainWindow()
        window.resize(1000, 640)
        window.song_list.clear()
        window.song_identity_to_item = {}
        for track in local_tracks(80):
            window.song_list.addItem(window.create_song_list_item(track))
        window.current_library_view = "all"
        window.filter_song_list("")
        window.show()
        window.show_library_page()
        process_events(app)
        put_at_bottom(window.song_list, app)
        window.show_search_page()
        window.show_library_page()
        process_events(app)
        assert_at_top(window.song_list)

        window.pending_imports = local_tracks(80)
        window.show_pending_imports_page()
        process_events(app)
        put_at_bottom(window.pending_imports_list, app)
        window.show_search_page()
        window.show_pending_imports_page()
        process_events(app)
        assert_at_top(window.pending_imports_list)

        sources = [
            {
                "id": f"custom_source_scroll_{index:03d}",
                "name": f"本机模拟来源 {index:03d}",
                "sourceUrl": f"https://example.invalid/source-{index:03d}.js",
                "userInstalled": True,
                "enabled": True,
                "status": "available",
                "capabilities": {"search": True, "playback": True},
            }
            for index in range(80)
        ]
        source_page = window.custom_source_manager_page
        window.content_stack.setCurrentWidget(source_page)
        source_page.on_source_list_received(sources)
        process_events(app)
        source_page.source_list.setCurrentRow(79)
        put_at_bottom(source_page.source_list, app)
        source_page.on_source_list_received(sources)
        process_events(app)
        assert_at_top(source_page.source_list)
    finally:
        if window is not None:
            window.hide()
            window.deleteLater()
            process_events(app)
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_rebuilt_track_list_starts_at_top(app)
    test_search_tabs_start_at_top(app)
    test_main_page_navigation_starts_at_top(app)
    print("page scroll position smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
