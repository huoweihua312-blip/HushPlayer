from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


activate_isolated_app_storage("hushplayer-theme-toggle-layout-")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def _layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 720)
    window._update_responsive_layout(force=True)
    for _ in range(3):
        app.processEvents()


def run_test(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        assert not hasattr(window, "theme_quick_actions")
        queue_before = list(window.play_queue)
        page_before = window.content_stack.currentIndex()
        for width in (900, 1100, 1450):
            _layout(app, window, width)
            button = window.theme_quick_button
            assert button.isVisible()
            assert button.parentWidget() in {window.sidebar_content, window.now_playing_panel}
            assert button.parentWidget() is not window.centralWidget()
            previous_parent = button.parentWidget()
            window.set_appearance_mode("light", persist=False)
            app.processEvents()
            assert button.parentWidget() is previous_parent
            window.set_appearance_mode("dark", persist=False)
            app.processEvents()
            assert button.parentWidget() is previous_parent
            window.set_appearance_mode("system", persist=False)
            app.processEvents()
            assert button.parentWidget() is previous_parent
            assert window.content_stack.currentIndex() == page_before
            assert window.play_queue == queue_before
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
        print("theme toggle layout smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
