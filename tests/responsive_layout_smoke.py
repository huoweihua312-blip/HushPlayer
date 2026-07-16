from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-responsive-layout-")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


EXPECTED_MODES = {
    900: "narrow",
    1100: "compact",
    1280: "compact",
    1400: "compact",
    1450: "full",
    1600: "full",
    1920: "full",
}


def process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 640 if width == 900 else 720)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        window = MainWindow()
        window.show()
        for width, expected_mode in EXPECTED_MODES.items():
            process_layout(app, window, width)
            assert window._responsive_mode == expected_mode
            assert window.sidebar_scroll.verticalScrollBarPolicy() == (
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            assert window.library_nav_button.minimumHeight() >= (
                window.library_nav_button.fontMetrics().height() + 16
            )
            assert window.player_bar.minimumSizeHint().width() <= (
                window.centralWidget().width()
            )
            if expected_mode == "narrow":
                assert window.now_playing_panel.isHidden()
                assert window.body_splitter.sizes()[2] == 0
                assert window.content_stack.width() >= 520
                assert window.sidebar_scroll.verticalScrollBar().maximum() > 0
                window.sidebar_scroll.ensureWidgetVisible(window.settings_nav_button)
                app.processEvents()
                assert not window.settings_nav_button.isHidden()
                assert window.library_page.random_button.isHidden()
                assert window.library_page.folder_button.isHidden()
                assert not window.player_more_button.isHidden()
                assert window.floating_lyrics_button.isHidden()
            elif expected_mode == "compact":
                assert not window.now_playing_panel.isHidden()
                assert 220 <= window.now_playing_panel.width() <= 270
                assert window.content_stack.width() >= 500
                assert window.library_page.random_button.isHidden()
                assert window.library_page.folder_button.isHidden()
                assert not window.player_more_button.isHidden()
            else:
                assert not window.now_playing_panel.isHidden()
                assert 280 <= window.now_playing_panel.width() <= 340
                assert window.content_stack.width() >= 700
                assert not window.library_page.random_button.isHidden()
                assert not window.library_page.folder_button.isHidden()
                assert window.player_more_button.isHidden()
        scale = os.environ.get("QT_SCALE_FACTOR", "1")
        print(
            "responsive layout smoke: OK",
            f"scale={scale}",
            f"devicePixelRatio={window.devicePixelRatioF():.2f}",
        )
        window.hide()
        window.deleteLater()
        app.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
