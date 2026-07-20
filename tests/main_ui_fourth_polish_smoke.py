from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


activate_isolated_app_storage("hushplayer-main-ui-fourth-polish-")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import (
    SIDEBAR_NAVIGATION_DEFAULT_ORDER,
    MainWindow,
    merge_sidebar_navigation_order,
)


REMOVED_NAVIGATION_ATTRIBUTES = (
    "recent_nav_button",
    "frequent_nav_button",
    "recent_added_nav_button",
    "artists_nav_button",
    "albums_nav_button",
    "playlist_nav_button",
    "lyrics_nav_button",
)


def process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 760)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def run_test(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        expected_order = [
            "liked",
            "online_search",
            "library_all",
            "pending_imports",
            "custom_sources",
        ]
        assert list(SIDEBAR_NAVIGATION_DEFAULT_ORDER) == expected_order
        assert window.sidebar_navigation.ordered_ids() == expected_order
        assert [
            window.sidebar_navigation_buttons[item_id].text()
            for item_id in expected_order
        ] == ["我喜欢", "搜索", "本地歌曲", "待导入", "自定义来源"]
        assert window.library_nav_button.toolTip().startswith("本地歌曲；")
        assert window.library_page.page_title.text() == "本地歌曲"
        assert all(not hasattr(window, name) for name in REMOVED_NAVIGATION_ATTRIBUTES)
        assert window.sidebar_playlist_box is not None

        assert merge_sidebar_navigation_order(
            [
                "albums",
                "artists",
                "recent_added",
                "all_songs",
                "liked",
                "search",
                "liked",
                "unknown",
            ]
        ) == [
            "library_all",
            "liked",
            "online_search",
            "pending_imports",
            "custom_sources",
        ]

        assert not hasattr(window, "player_queue_button")
        assert not hasattr(window, "floating_lyrics_button")
        assert not hasattr(window, "player_more_button")
        assert not hasattr(window, "floating_lyrics_action")
        assert not hasattr(window, "player_like_action")
        assert window.immersive_lyrics_button.toolTip() == "打开沉浸歌词"
        assert window.desktop_lyrics_button.toolTip() == "开启桌面歌词"

        assert window.like_btn.text() == ""
        assert window.now_like_btn.text() == ""
        assert window.like_btn.width() <= 36
        assert window.now_like_btn.width() <= 36
        window._apply_current_like_state(True, True)
        assert window.like_btn.toolTip() == "从我喜欢移除"
        assert window.now_like_btn.toolTip() == "从我喜欢移除"
        assert not window.like_btn.icon().isNull()
        assert not window.now_like_btn.icon().isNull()

        lyrics = [
            (index * 1000, f"第 {index + 1} 句")
            for index in range(30)
        ]
        window.current_lyrics = lyrics
        window.lyrics_view.set_lyrics(lyrics)
        window.lyrics_view.update_by_position(14500, lyrics)
        label_ids = [id(label) for label in window.lyrics_view.labels]
        list_items = [
            window.song_list.item(row) for row in range(window.song_list.count())
        ]
        started = time.perf_counter()
        for position in range(14000, 15000, 5):
            window.lyrics_view.update_by_position(position, lyrics)
            window.update_now_lyrics_preview(position)
        preview_update_ms = (time.perf_counter() - started) * 1000
        assert [id(label) for label in window.lyrics_view.labels] == label_ids
        assert [
            window.song_list.item(row) for row in range(window.song_list.count())
        ] == list_items

        for width in (1100, 1450, 1600, 1920, 2560):
            process_layout(app, window, width)
            assert window.now_playing_panel.isVisible()
            assert window.lyrics_view.isVisible()
            assert not window.now_like_btn.geometry().intersects(
                window.now_more_btn.geometry()
            )

        process_layout(app, window, 900)
        assert window.now_playing_panel.isHidden()
        assert window.like_btn.isVisible()
        assert window.immersive_lyrics_button.isVisible()
        assert window.desktop_lyrics_button.isVisible()
        assert window.player_left_box.geometry().right() <= (
            window.player_center_box.geometry().left()
        )
        assert window.player_center_box.geometry().right() <= (
            window.player_right_box.geometry().left()
        )

        assert not hasattr(window, "full_lyrics_page")
        initial_pages = window.content_stack.count()
        window.show_full_lyrics_page()
        app.processEvents()
        assert window.content_stack.currentWidget() is window.full_lyrics_page
        assert window.content_stack.count() == initial_pages + 1
        page = window.full_lyrics_page
        window.show_full_lyrics_page()
        assert window.full_lyrics_page is page
        assert window.content_stack.count() == initial_pages + 1

        print(
            "main UI fourth polish smoke: OK",
            f"preview_200_updates_ms={preview_update_ms:.2f}",
            f"navigation_items={len(expected_order)}",
            f"lyric_labels={len(window.lyrics_view.labels)}",
        )
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def main() -> int:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        run_test(app)
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
