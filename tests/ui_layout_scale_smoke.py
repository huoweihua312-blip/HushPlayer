from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


activate_isolated_app_storage("hushplayer-ui-layout-scale-")

from PySide6.QtWidgets import QApplication

from app.ui.design_system import UI_CONTROL_SIZES, UI_RADII, UI_SPACING, UI_TYPOGRAPHY
from app.ui.main_window import MainWindow


def _process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 760)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def _snapshot(window: MainWindow) -> tuple[int, int, int, int]:
    return (
        window.player_bar.height(),
        window.bottom_cover_label.width(),
        window.library_nav_button.minimumHeight(),
        window.progress_slider.minimumHeight(),
    )


def run_test(app: QApplication) -> None:
    required_typography = {
        "font_caption",
        "font_secondary",
        "font_body",
        "font_body_emphasis",
        "font_section",
        "font_page_title",
        "font_track_title",
        "font_player_title",
        "font_player_artist",
    }
    required_controls = {
        "icon_small",
        "icon_normal",
        "icon_large",
        "control_height_small",
        "control_height_normal",
        "navigation_item_height",
        "table_row_height",
        "player_height",
        "player_height_narrow",
        "player_height_compact",
        "player_height_full",
        "player_vertical_padding_narrow",
        "player_vertical_padding_compact",
        "player_vertical_padding_full",
        "player_cover_size",
        "player_cover_size_compact",
        "player_cover_size_full",
        "now_playing_cover_size",
        "play_button_size",
        "transport_button_size",
    }
    assert required_typography.issubset(UI_TYPOGRAPHY)
    assert required_controls.issubset(UI_CONTROL_SIZES)
    assert {"radius_sm", "radius_md", "radius_lg"}.issubset(UI_RADII)
    assert {"spacing_xs", "spacing_sm", "spacing_md", "spacing_lg", "spacing_xl"}.issubset(UI_SPACING)
    assert all(value >= 0 for value in UI_CONTROL_SIZES.values())
    assert UI_CONTROL_SIZES["play_button_size"] > UI_CONTROL_SIZES["icon_large"]
    assert UI_CONTROL_SIZES["player_height_compact"] >= UI_CONTROL_SIZES["player_cover_size"] + 24
    assert UI_CONTROL_SIZES["player_height_full"] >= UI_CONTROL_SIZES["player_cover_size_full"] + 24
    assert UI_CONTROL_SIZES["player_height_narrow"] >= UI_CONTROL_SIZES["player_cover_size_compact"] + 24
    assert UI_CONTROL_SIZES["table_row_height"] >= UI_TYPOGRAPHY["font_body"] + 24
    assert UI_CONTROL_SIZES["navigation_item_height"] >= UI_CONTROL_SIZES["icon_normal"] + 16

    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        responsive_profiles = {
            "narrow": ("player_height_narrow", "player_cover_size_compact"),
            "compact": ("player_height_compact", "player_cover_size"),
            "full": ("player_height_full", "player_cover_size_full"),
        }
        expected_spacings = {
            "narrow": (UI_SPACING["xxs"], UI_SPACING["xs"], UI_SPACING["xxs"]),
            "compact": (UI_SPACING["xs"], UI_SPACING["sm"], UI_SPACING["xs"]),
            "full": (UI_SPACING["sm"], UI_SPACING["sm"], UI_SPACING["sm"]),
        }
        for width, expected_mode in (
            (900, "narrow"),
            (1100, "compact"),
            (1450, "full"),
            (1600, "full"),
            (1920, "full"),
            (2560, "full"),
        ):
            _process_layout(app, window, width)
            assert window._responsive_mode == expected_mode
            height_key, cover_key = responsive_profiles[expected_mode]
            assert window.player_bar.height() == UI_CONTROL_SIZES[height_key]
            assert window.bottom_cover_label.width() == UI_CONTROL_SIZES[cover_key]
            assert (
                window.player_center_layout.spacing(),
                window.player_progress_layout.spacing(),
                window.player_right_layout.spacing(),
            ) == expected_spacings[expected_mode]
            assert window.library_nav_button.minimumHeight() == UI_CONTROL_SIZES["navigation_item_height"]
            assert UI_CONTROL_SIZES["table_row_height"] >= UI_TYPOGRAPHY["font_body"] + 24
            assert window.progress_slider.minimumHeight() >= 20
            assert window.theme_quick_button.isVisible()
            if expected_mode == "narrow":
                assert window.theme_quick_button.parentWidget() is window.sidebar_content
            else:
                assert window.theme_quick_button.parentWidget() is window.now_playing_panel
                assert window.cover_label.width() <= UI_CONTROL_SIZES["now_playing_cover_size"]
            assert window.theme_quick_button.parentWidget() is not window.centralWidget()

        _process_layout(app, window, 1450)
        baseline = _snapshot(window)
        window.set_appearance_mode("light", persist=False)
        app.processEvents()
        assert _snapshot(window) == baseline
        window.set_appearance_mode("dark", persist=False)
        app.processEvents()
        assert _snapshot(window) == baseline
        _process_layout(app, window, 900)
        _process_layout(app, window, 1450)
        assert _snapshot(window) == baseline
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
        print("ui layout scale smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
