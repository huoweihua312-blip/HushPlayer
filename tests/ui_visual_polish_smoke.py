from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-ui-polish-")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from app.services.playlist_membership import PlaylistMembership
from app.ui.design_system import (
    DARK_THEME_TOKENS,
    UI_CONTROL_SIZES,
    UI_RADII,
    UI_SPACING,
    UI_TYPOGRAPHY,
)
from app.ui.main_window import MainWindow, SettingsDialog


def fixture_song(path: Path, index: int) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return {
        "title": f"视觉测试歌曲 {index}",
        "artist": "视觉测试歌手",
        "album": "视觉测试专辑",
        "path": str(path),
        "duration": 120 + index,
        "added_at": index,
        "demo": False,
    }


def process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 720)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def run_test(app: QApplication) -> None:
    required_colors = {
        "app_bg",
        "panel_bg",
        "hover",
        "selected_bg",
        "playing_bg",
        "text",
        "text_secondary",
        "text_disabled",
        "border",
        "accent",
        "favorite",
        "warning",
        "error",
    }
    assert required_colors.issubset(DARK_THEME_TOKENS)
    assert set(UI_RADII.values()) == {6, 8, 10, 12, 16, 22}
    assert {4, 8, 12, 16, 20, 24, 32}.issubset(UI_SPACING.values())
    assert UI_TYPOGRAPHY["page_title"] > UI_TYPOGRAPHY["body"]

    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        window.ensure_play_queue_page()
        app.processEvents()
        expected_pages = {
            window.library_page,
            window.search_page,
            window.play_queue_page,
            window.pending_imports_page,
            window.custom_source_manager_page,
        }
        stack_pages = {
            window.content_stack.widget(index)
            for index in range(window.content_stack.count())
        }
        assert expected_pages.issubset(stack_pages)
        assert not hasattr(window, "full_lyrics_page")
        window.show_full_lyrics_page()
        app.processEvents()
        assert window.full_lyrics_page in {
            window.content_stack.widget(index)
            for index in range(window.content_stack.count())
        }
        assert len(window.sidebar_navigation.navigation_buttons) == 5
        assert set(window.sidebar_navigation.navigation_buttons) == set(
            window.sidebar_navigation.ordered_ids()
        )
        for button in window.sidebar_navigation.navigation_buttons.values():
            assert not button.icon().isNull()
            assert button.iconSize().width() == UI_CONTROL_SIZES["navigation_icon"]
            assert button.minimumHeight() >= UI_CONTROL_SIZES["navigation_height"]
        assert not window.settings_nav_button.icon().isNull()
        assert window.settings_nav_button not in (
            window.sidebar_navigation.navigation_buttons.values()
        )

        assert window.song_table_header.objectName() == "songTableHeader"
        assert window.song_list.objectName() == "songList"
        assert window.progress_slider.objectName() == "progressSlider"
        assert window.volume_slider.objectName() == "volumeSlider"
        assert window.play_btn.objectName() == "transportPlayButton"
        assert window.search_input.isClearButtonEnabled()
        assert window.current_time_label.x() < window.progress_slider.x()
        assert window.progress_slider.x() < window.total_time_label.x()
        assert window.current_time_label.text() == "0:00"
        assert window.total_time_label.text() == "0:00"
        assert not window.lyrics_view.manual_browse_enabled
        assert window.lyrics_view.target_position_ratio == 0.45
        assert window.lyrics_view.scroll_animation.duration() == 0
        assert DARK_THEME_TOKENS["favorite"] in window.build_player_product_qss()
        expected_mode_labels = {
            "sequence": "顺序播放",
            "list_loop": "列表循环",
            "single_loop": "单曲循环",
            "shuffle": "随机播放",
        }
        for appearance in ("light", "dark"):
            window.set_appearance_mode(appearance, persist=False)
            app.processEvents()
            tokens = window.get_dark_theme_tokens()
            player_qss = window.build_theme_overrides_qss()
            assert (
                f"border-radius: {UI_CONTROL_SIZES['transport_button_size'] // 2}px"
                in player_qss
            )
            assert 'QPushButton#transportButton:disabled' in player_qss
            assert 'QPushButton#controlButton:disabled' in player_qss
            assert 'QPushButton#controlButton[modeActive="true"]' in player_qss
            assert (
                f"background: {tokens['selection_background']}; "
                f"color: {tokens['text_primary']};"
            ) in player_qss
            for mode, label in expected_mode_labels.items():
                window.play_mode = mode
                window.update_play_mode_button()
                assert window.play_mode_btn.text() == label
                assert window.play_mode_btn.property("modeActive") is True
        window.set_appearance_mode("dark", persist=False)
        app.processEvents()

        music_root = ISOLATED_STORAGE.root / "music"
        songs = [fixture_song(music_root / f"track-{index}.mp3", index) for index in range(3)]
        window.playlists = {
            "liked": {
                "name": "我喜欢",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": True,
            },
            "ui-fixture": {
                "name": "长时间聆听测试歌单",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": False,
            },
        }
        window.invalidate_playlist_membership_snapshot()
        window.refresh_playlist_view_buttons()
        window.rebuild_song_list_from_data(songs)
        window.filter_song_list("")
        app.processEvents()
        assert len(window.custom_view_buttons) == 1
        assert window.custom_view_buttons[0].text() == "长时间聆听测试歌单"
        assert window.settings_nav_button.isVisible()

        heart_item = window.song_list.item(0)
        play_requests: list[object] = []
        window.song_list.itemDoubleClicked.connect(play_requests.append)
        order_before = [
            window.song_list.item(row).data(Qt.ItemDataRole.UserRole)["title"]
            for row in range(window.song_list.count())
        ]
        row_count = window.song_list.count()
        center = window.song_list.like_rect_for_item(heart_item).center().toPoint()
        QTest.mouseClick(window.song_list.viewport(), Qt.MouseButton.LeftButton, pos=center)
        app.processEvents()
        assert play_requests == []
        assert window.song_list.count() == row_count
        assert order_before == [
            window.song_list.item(row).data(Qt.ItemDataRole.UserRole)["title"]
            for row in range(window.song_list.count())
        ]

        page_instances = [
            window.content_stack.widget(index)
            for index in range(window.content_stack.count())
        ]
        window.search_nav_button.click()
        window.library_nav_button.click()
        app.processEvents()
        assert set(page_instances) == {
            window.content_stack.widget(index)
            for index in range(window.content_stack.count())
        }

        for width in (900, 1100, 1450, 1600):
            process_layout(app, window, width)
            assert window.player_bar.minimumSizeHint().width() <= window.centralWidget().width()
            assert window.progress_slider.width() > 0
            assert window.volume_slider.width() > 0
            assert window.song_list.viewport().width() > UI_CONTROL_SIZES["track_like_width"]
            expected_direction = (
                QBoxLayout.Direction.TopToBottom
                if width == 900
                else QBoxLayout.Direction.LeftToRight
            )
            assert window.custom_source_manager_page.content_row.direction() == expected_direction

        settings_dialog = SettingsDialog(window)
        try:
            assert settings_dialog.settings_scroll.widget() is settings_dialog.settings_scroll_content
            assert settings_dialog.palette().color(settings_dialog.foregroundRole()).isValid()
        finally:
            settings_dialog.deleteLater()
            app.processEvents()

        screenshot_path = str(os.environ.get("HUSHPLAYER_UI_SCREENSHOT") or "").strip()
        if screenshot_path:
            screenshot_width = int(
                os.environ.get("HUSHPLAYER_UI_SCREENSHOT_WIDTH", "1600")
            )
            process_layout(app, window, screenshot_width)
            target = Path(screenshot_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(target))
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
        scale = os.environ.get("QT_SCALE_FACTOR", "1")
        print("UI visual polish smoke: OK", f"scale={scale}")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
