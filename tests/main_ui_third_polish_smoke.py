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


activate_isolated_app_storage("hushplayer-main-ui-third-polish-")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.ui.design_system import UI_CONTROL_SIZES
from app.ui.main_window import MainWindow
from app.ui.track_list_view import OnlineTrackDelegate, OnlineTrackListWidget


def online_track(track_id: str, *, can_play: bool = True) -> dict:
    return {
        "track_id": track_id,
        "source_id": "fixture",
        "source_name": "测试来源",
        "media_type": "online",
        "title": f"在线歌曲 {track_id}",
        "artist": "在线歌手",
        "album": "在线专辑",
        "duration": 185,
        "can_play": can_play,
        "can_download": can_play,
        "availability": "available" if can_play else "unavailable",
    }


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
        assert UI_CONTROL_SIZES["track_row_height"] == 52
        assert window.library_page.page_header.minimumHeight() == 58
        assert window.search_page.page_header.minimumHeight() == 58
        assert window.library_page.page_header.objectName() == "pageHeader"
        assert window.search_page.page_header.objectName() == "pageHeader"
        assert "浏览本地音乐" not in window.library_page.page_subtitle.text()
        assert window.sidebar_navigation_hint.isHidden()

        product_qss = window.build_player_product_qss()
        header_rule = product_qss.split("QFrame#songTableHeader", 1)[1].split("}", 1)[0]
        assert "border-bottom" in header_rule
        assert "border: 1px" not in header_rule

        assert window.now_open_folder_btn.isHidden()
        assert window.now_info_box.layout().contentsMargins().left() == 0
        assert window.now_like_btn.isVisible()
        assert window.now_more_btn.isVisible()
        assert window.lyrics_view.isHidden()

        window.current_lyrics = [
            (0, "第一句歌词"),
            (1000, "当前歌词"),
            (2000, "下一句歌词"),
        ]
        window.lyrics_view.set_lyrics(window.current_lyrics)
        rebuild_count = window.lyrics_view.content_rebuild_count
        window.lyrics_view.update_by_position(1500, window.current_lyrics)
        window.update_now_lyrics_preview(1500)
        assert window.now_current_lyric.text() == "当前歌词"
        assert window.now_next_lyric.text() == "下一句歌词"
        for position in range(1500, 1600, 5):
            window.lyrics_view.update_by_position(position, window.current_lyrics)
            window.update_now_lyrics_preview(position)
        assert window.lyrics_view.content_rebuild_count == rebuild_count

        large_library = [
            {
                "title": f"大列表歌曲 {index}",
                "artist": f"歌手 {index % 17}",
                "album": f"专辑 {index % 23}",
                "path": f"C:/hushplayer-smoke/missing-{index}.flac",
                "duration": 120 + index % 180,
                "demo": False,
            }
            for index in range(520)
        ]
        started = time.perf_counter()
        window.rebuild_song_list_from_data(large_library)
        large_library_ms = (time.perf_counter() - started) * 1000
        assert window.song_list.count() == 520
        assert all(
            window.song_list.itemWidget(window.song_list.item(row)) is None
            for row in range(window.song_list.count())
        )
        scroll_bar = window.song_list.verticalScrollBar()
        started = time.perf_counter()
        for value in (0, scroll_bar.maximum() // 3, scroll_bar.maximum() * 2 // 3, scroll_bar.maximum()):
            scroll_bar.setValue(value)
            app.processEvents()
        large_scroll_ms = (time.perf_counter() - started) * 1000

        list_items_before = [
            window.song_list.item(row)
            for row in range(window.song_list.count())
        ]
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#4c8dff"))
        started = time.perf_counter()
        window.show_cover_pixmap(pixmap)
        window.now_song_title.setText("新的当前歌曲")
        window.now_artist.setText("歌手 · 专辑")
        right_update_ms = (time.perf_counter() - started) * 1000
        assert [
            window.song_list.item(row)
            for row in range(window.song_list.count())
        ] == list_items_before
        assert not window.bottom_cover_label.pixmap().isNull()

        process_layout(app, window, 1600)
        assert window.player_bar_layout.indexOf(window.player_left_box) >= 0
        assert window.player_bar_layout.indexOf(window.player_center_box) >= 0
        assert window.player_bar_layout.indexOf(window.player_right_box) >= 0
        assert window.player_left_box.x() < window.player_center_box.x()
        assert window.player_center_box.x() < window.player_right_box.x()
        assert window.player_center_box.maximumWidth() == UI_CONTROL_SIZES[
            "player_center_max_width"
        ]
        assert window.current_time_label.x() < window.progress_slider.x()
        assert window.progress_slider.x() < window.total_time_label.x()
        assert window.player_queue_button.parent() is window.player_right_box
        assert window.play_mode_btn.parent() is window.player_center_box
        player_layout_count = window.player_bar_layout.count()
        center_geometry = window.player_center_box.geometry()
        for position in range(0, 180000, 3000):
            window.update_current_time_display(position)
        assert window.player_bar_layout.count() == player_layout_count
        assert window.player_center_box.geometry() == center_geometry

        process_layout(app, window, 900)
        assert window.now_playing_panel.isHidden()
        assert window.bottom_cover_label.isHidden()
        assert window.volume_slider.isHidden()
        assert window.player_left_box.geometry().right() <= window.player_center_box.geometry().left()
        assert window.player_center_box.geometry().right() <= window.player_right_box.geometry().left()

        panel = window.search_page.online_results
        assert isinstance(panel.result_list.itemDelegate(), OnlineTrackDelegate)
        assert panel.table_header.objectName() == "onlineTableHeader"
        panel.begin_results("测试", {"resultCount": 0})
        state = {
            "sourceId": "fixture",
            "sourceName": "测试来源",
            "status": "success",
            "resultCount": 1,
        }
        started = time.perf_counter()
        panel.update_source_group(
            "fixture",
            "测试来源",
            [online_track("one")],
            state,
        )
        first_append_ms = (time.perf_counter() - started) * 1000
        header = panel._group_headers["fixture"]
        track_item = panel.result_list.item(panel.result_list.row(header) + 1)
        assert track_item.sizeHint().height() == UI_CONTROL_SIZES["track_row_height"]
        assert "可播放" not in track_item.text()
        assert "可下载" not in track_item.text()
        panel.update_source_group(
            "fixture_two",
            "第二来源",
            [online_track("two")],
            {**state, "sourceId": "fixture_two", "sourceName": "第二来源"},
        )
        second_header = panel._group_headers["fixture_two"]
        panel.update_source_group(
            "fixture",
            "测试来源",
            [online_track("one"), online_track("three", can_play=False)],
            {**state, "resultCount": 2},
        )
        assert panel._group_headers["fixture_two"] is second_header
        assert panel._group_headers["fixture"] is header

        action_list = OnlineTrackListWidget()
        action_list.setItemDelegate(OnlineTrackDelegate(parent=action_list))
        action_item = QListWidgetItem("online action")
        action_item.setData(Qt.ItemDataRole.UserRole, online_track("action"))
        action_list.addItem(action_item)
        action_list.resize(820, 90)
        action_list.show()
        app.processEvents()
        more_requests: list[dict] = []
        action_list.moreRequested.connect(
            lambda track, _position: more_requests.append(dict(track))
        )
        more_center = action_list.more_rect_for_item(action_item).center().toPoint()
        QTest.mouseClick(
            action_list.viewport(),
            Qt.MouseButton.LeftButton,
            pos=more_center,
        )
        app.processEvents()
        assert [track["track_id"] for track in more_requests] == ["action"]
        action_list.close()
        action_list.deleteLater()

        window._apply_current_like_state(True, True)
        assert window.like_btn.text() == "♥ 已收藏"
        assert window.now_like_btn.text() == "♥ 已收藏"
        window._apply_current_like_state(False, True)
        assert window.like_btn.toolTip() == "添加到我喜欢"
        assert window.now_like_btn.toolTip() == "添加到我喜欢"

        print(
            "main UI third polish smoke: OK",
            f"right_update_ms={right_update_ms:.2f}",
            f"online_first_append_ms={first_append_ms:.2f}",
            f"library_520_build_ms={large_library_ms:.2f}",
            f"library_520_scroll_ms={large_scroll_ms:.2f}",
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
