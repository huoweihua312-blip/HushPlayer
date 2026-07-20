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


activate_isolated_app_storage("hushplayer-bottom-lyrics-layout-")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy

from app.ui.main_window import MainWindow, NowPlayingLyricsView


def process_layout(
    app: QApplication,
    window: MainWindow,
    width: int,
    height: int,
) -> None:
    window.resize(width, height)
    window._update_responsive_layout(force=True)
    for _ in range(8):
        app.processEvents()


def run_test(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    process_layout(app, window, 1600, 900)
    try:
        assert window.bottom_cover_label.size().width() == 48
        assert window.player_left_box.findChildren(QPushButton) == []
        assert not hasattr(window, "bottom_source_badge")
        assert window.player_left_box.layout().spacing() == 10

        window.bottom_song_title.setText("一首用于验证省略号与提示的很长歌曲标题")
        window.bottom_song_artist.setText("一位名字同样很长的测试歌手")
        assert window.bottom_song_title.toolTip().endswith("很长歌曲标题")
        assert window.bottom_song_artist.toolTip().endswith("测试歌手")

        assert window.like_btn.parent() is window.player_leading_controls
        assert window.like_btn.size().width() == 36
        assert window.like_btn.iconSize().width() == 20
        assert window.like_btn.text() == ""
        assert not window.like_btn.isEnabled()
        assert window.like_btn.mapToGlobal(window.like_btn.rect().center()).x() < (
            window.prev_btn.mapToGlobal(window.prev_btn.rect().center()).x()
        )
        play_center_x = window.play_btn.mapToGlobal(
            window.play_btn.rect().center()
        ).x()
        center_box_x = window.player_center_box.mapToGlobal(
            window.player_center_box.rect().center()
        ).x()
        assert abs(play_center_x - center_box_x) <= 2
        player_layout_count = window.player_bar_layout.count()
        center_geometry = window.player_center_box.geometry()
        window._apply_current_like_state(True, True)
        assert window.like_btn.toolTip() == "从我喜欢移除"
        assert window.player_bar_layout.count() == player_layout_count
        assert window.player_center_box.geometry() == center_geometry

        assert not hasattr(window, "player_queue_button")
        assert not hasattr(window, "player_more_button")
        assert not hasattr(window, "floating_lyrics_action")
        assert not hasattr(window, "player_like_action")
        assert window.immersive_lyrics_button.parent() is window.player_right_box
        assert window.desktop_lyrics_button.parent() is window.player_right_box
        assert window.immersive_lyrics_button.text() == "歌词"
        assert window.desktop_lyrics_button.text() == "桌面歌词"
        assert not window.immersive_lyrics_button.icon().isNull()
        assert not window.desktop_lyrics_button.icon().isNull()
        assert (
            window.desktop_lyrics_button.fontMetrics().horizontalAdvance("桌面歌词")
            + window.desktop_lyrics_button.iconSize().width()
            + 24
            <= window.desktop_lyrics_button.width()
        )
        assert window.immersive_lyrics_button.geometry().bottom() < (
            window.volume_slider.geometry().top()
        )

        desktop_clicks = []
        window.toggle_floating_lyrics = lambda: desktop_clicks.append(True)
        QTest.mouseClick(window.immersive_lyrics_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(window.desktop_lyrics_button, Qt.MouseButton.LeftButton)
        assert window._immersive_button_test_calls == 1
        assert desktop_clicks == [True]

        class VisibleFloatingLyrics:
            @staticmethod
            def isVisible() -> bool:
                return True

        window.floating_lyrics_window = VisibleFloatingLyrics()
        window.update_floating_lyrics_button_state()
        assert window.desktop_lyrics_button.isChecked()
        assert window.desktop_lyrics_button.toolTip() == "关闭桌面歌词"
        window.floating_lyrics_window = None
        window.update_floating_lyrics_button_state()
        assert not window.desktop_lyrics_button.isChecked()
        assert window.desktop_lyrics_button.toolTip() == "开启桌面歌词"

        for width in (900, 1100, 1450, 1600, 1920, 2560):
            process_layout(app, window, width, 760)
            assert window.player_left_box.geometry().right() <= (
                window.player_center_box.geometry().left()
            )
            assert window.player_center_box.geometry().right() <= (
                window.player_right_box.geometry().left()
            )
            assert window.immersive_lyrics_button.geometry().right() <= (
                window.player_right_box.contentsRect().right()
            )
            assert window.desktop_lyrics_button.geometry().right() <= (
                window.player_right_box.contentsRect().right()
            )

        lyrics = [
            (
                index * 1000,
                (
                    "这是一条需要在较窄右栏内自然换行并保持完整高度的测试歌词 " * 3
                    if index == 12
                    else f"第 {index + 1} 句自适应歌词"
                ),
            )
            for index in range(40)
        ]
        window.current_lyrics = lyrics
        window.lyrics_view.set_lyrics(lyrics)
        assert isinstance(window.lyrics_view, NowPlayingLyricsView)
        assert window.lyrics_view.sizePolicy().verticalPolicy() == (
            QSizePolicy.Policy.Expanding
        )
        lyric_label_ids = [id(label) for label in window.lyrics_view.labels]
        rebuild_count = window.lyrics_view.content_rebuild_count
        song_items = [
            window.song_list.item(row) for row in range(window.song_list.count())
        ]

        process_layout(app, window, 1450, 760)
        window.lyrics_view.update_by_position(20000, lyrics)
        for _ in range(4):
            app.processEvents()
        normal_visible = window.lyrics_view.fully_visible_label_indexes()
        normal_ratio = window.lyrics_view.current_line_viewport_ratio()
        assert len(normal_visible) >= 5
        assert normal_ratio is not None and 0.42 <= normal_ratio <= 0.48

        process_layout(app, window, 1450, 1050)
        for _ in range(4):
            app.processEvents()
        tall_visible = window.lyrics_view.fully_visible_label_indexes()
        assert len(tall_visible) > len(normal_visible)
        assert len(tall_visible) >= 8
        assert window.cover_label.height() <= round(
            window.now_playing_panel.height() * 0.34
        )
        tall_cover_height = window.cover_label.height()

        window.resize(1450, 760)
        for _ in range(8):
            app.processEvents()
        assert window._responsive_height == 760
        assert window.cover_label.height() <= tall_cover_height
        assert len(window.lyrics_view.fully_visible_label_indexes()) < len(tall_visible)

        window.lyrics_view.update_by_position(0, lyrics)
        app.processEvents()
        start_visible = window.lyrics_view.fully_visible_label_indexes()
        assert start_visible[0] == 0
        assert start_visible[-1] >= 5
        first_label_top = (
            window.lyrics_view.labels[0].y()
            - window.lyrics_view.verticalScrollBar().value()
        )
        assert first_label_top <= 8

        window.lyrics_view.update_by_position(39000, lyrics)
        app.processEvents()
        end_visible = window.lyrics_view.fully_visible_label_indexes()
        assert end_visible[-1] == len(lyrics) - 1
        assert end_visible[0] <= len(lyrics) - 6
        last_label = window.lyrics_view.labels[-1]
        last_label_bottom = (
            last_label.y()
            + last_label.height()
            - window.lyrics_view.verticalScrollBar().value()
        )
        assert last_label_bottom >= window.lyrics_view.viewport().height() - 8

        long_label = window.lyrics_view.labels[12]
        assert long_label.height() > long_label.fontMetrics().lineSpacing()
        assert [id(label) for label in window.lyrics_view.labels] == lyric_label_ids
        assert window.lyrics_view.content_rebuild_count == rebuild_count
        assert [
            window.song_list.item(row) for row in range(window.song_list.count())
        ] == song_items

        started = time.perf_counter()
        for position in range(10000, 30000, 100):
            window.update_now_lyrics_preview(position)
        lyric_updates_ms = (time.perf_counter() - started) * 1000
        assert [id(label) for label in window.lyrics_view.labels] == lyric_label_ids
        assert window.lyrics_view.content_rebuild_count == rebuild_count

        process_layout(app, window, 900, 760)
        assert window.now_playing_panel.isHidden()
        assert window.immersive_lyrics_button.text() == ""
        assert window.desktop_lyrics_button.text() == ""
        assert window.immersive_lyrics_button.isVisible()
        assert window.desktop_lyrics_button.isVisible()
        assert window.volume_value_label.isHidden()
        assert window.immersive_lyrics_button.toolTip() == "打开沉浸歌词"

        process_layout(app, window, 1600, 900)
        assert window.now_playing_panel.isVisible()
        assert window.lyrics_view.isVisible()
        assert window.lyrics_view.fully_visible_label_indexes()

        progress_geometry = window.progress_slider.geometry()
        for position in range(0, 180000, 3000):
            window.update_current_time_display(position)
        assert window.player_bar_layout.count() == player_layout_count
        assert window.progress_slider.geometry() == progress_geometry

        window.lyrics_view.set_placeholder(
            "暂时没有找到歌词",
            "可打开沉浸歌词或检查本地 .lrc 文件",
        )
        app.processEvents()
        assert not window.lyrics_view.labels
        assert window.lyrics_view.height() >= 132

        print(
            "main UI bottom/lyrics layout smoke: OK",
            f"normal_visible={len(normal_visible)}",
            f"tall_visible={len(tall_visible)}",
            f"current_ratio={normal_ratio:.3f}",
            f"lyric_200_updates_ms={lyric_updates_ms:.2f}",
        )
    finally:
        window.floating_lyrics_window = None
        window.close()
        window.deleteLater()
        app.processEvents()


def main() -> int:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_open_immersive = MainWindow.open_immersive_lyrics_window

    def record_immersive_open(self: MainWindow) -> None:
        self._immersive_button_test_calls = (
            getattr(self, "_immersive_button_test_calls", 0) + 1
        )

    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    MainWindow.open_immersive_lyrics_window = record_immersive_open
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        run_test(app)
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        MainWindow.open_immersive_lyrics_window = original_open_immersive


if __name__ == "__main__":
    raise SystemExit(main())
