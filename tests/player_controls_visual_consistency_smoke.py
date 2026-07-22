"""Regression coverage for the bottom player control visual roles."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


activate_isolated_app_storage("hushplayer-player-controls-")

from PySide6.QtWidgets import QApplication

from app.ui.design_system import UI_CONTROL_SIZES
from app.ui.main_window import MainWindow


def _process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 760)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def _qss_rule(qss: str, selector: str) -> str:
    start = qss.index(selector)
    end = qss.index("}", start) + 1
    return qss[start:end]


def _assert_control_geometry(window: MainWindow) -> None:
    secondary = UI_CONTROL_SIZES["transport_button_size"]
    primary = UI_CONTROL_SIZES["play_button_size"]
    buttons = (window.like_btn, window.prev_btn, window.next_btn)
    assert all(button.width() == secondary and button.height() == secondary for button in buttons)
    assert window.play_btn.width() == primary
    assert window.play_btn.height() == primary
    assert primary > secondary
    assert window.play_mode_btn.height() == UI_CONTROL_SIZES["player_mode_button_height"]
    assert window.play_mode_btn.minimumWidth() == UI_CONTROL_SIZES["player_mode_button_min_width"]
    assert window.play_mode_btn.maximumWidth() == UI_CONTROL_SIZES["player_mode_button_max_width"]
    centers = {
        name: button.mapTo(window.player_center_box, button.rect().center()).y()
        for name, button in (
            ("favorite", window.like_btn),
            ("previous", window.prev_btn),
            ("play", window.play_btn),
            ("next", window.next_btn),
            ("mode", window.play_mode_btn),
        )
    }
    assert len(set(centers.values())) == 1, centers


def run_test(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        assert window.like_btn.property("playerFavoriteButton") is True
        assert window.prev_btn.property("playerTransportButton") is True
        assert window.next_btn.property("playerTransportButton") is True
        assert window.play_btn.property("playerPrimaryButton") is True
        assert window.play_mode_btn.property("playerModeButton") is True
        assert not window.play_mode_btn.isCheckable()

        source = (PROJECT_ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
        assert "self.prev_btn.clicked.connect(self.play_previous_song)" in source
        assert "self.play_btn.clicked.connect(self.toggle_play)" in source
        assert "self.next_btn.clicked.connect(self.play_next_song)" in source
        assert "self.like_btn.clicked.connect(self.toggle_like_current_song)" in source
        assert "self.play_mode_btn.clicked.connect(self.toggle_play_mode)" in source

        for appearance in ("light", "dark"):
            window.set_appearance_mode(appearance, persist=False)
            _process_layout(app, window, 1450)
            tokens = window.get_dark_theme_tokens()
            qss = window.build_theme_overrides_qss()
            assert 'QPushButton#transportButton[playerTransportButton="true"]' in qss
            assert 'QPushButton#likeButton[playerFavoriteButton="true"]' in qss
            assert 'QPushButton#transportPlayButton[playerPrimaryButton="true"]' in qss
            assert 'QPushButton#controlButton[playerModeButton="true"]' in qss
            assert "QPushButton#controlButton[modeActive" not in qss
            assert f"border-radius: {UI_CONTROL_SIZES['transport_button_size'] // 2}px" in qss
            assert f"border-radius: {UI_CONTROL_SIZES['play_button_size'] // 2}px" in qss
            assert tokens["text_secondary"] != tokens["surface"]
            assert tokens["text_primary"] != tokens["surface"]

            liked_rule = _qss_rule(
                qss,
                'QPushButton#likeButton[playerFavoriteButton="true"][liked="true"]',
            )
            assert f"color: {tokens['danger']}" in liked_rule
            assert f"border-color: {tokens['border']}" in liked_rule
            assert f"border-color: {tokens['danger']}" not in liked_rule

            for width in (900, 1100, 1450, 1920, 2560):
                _process_layout(app, window, width)
                _assert_control_geometry(window)

            _process_layout(app, window, 1450)
            window._apply_current_like_state(False, True)
            before = (window.like_btn.size(), window.like_btn.minimumSize(), window.like_btn.maximumSize())
            window._apply_current_like_state(True, True)
            after = (window.like_btn.size(), window.like_btn.minimumSize(), window.like_btn.maximumSize())
            assert before == after
            assert window.like_btn.property("liked") is True

            mode_width = window.play_mode_btn.width()
            for mode in ("sequence", "list_loop", "single_loop", "shuffle"):
                window.play_mode = mode
                window.update_play_mode_button()
                app.processEvents()
                assert window.play_mode_btn.property("playerModeButton") is True
                assert window.play_mode_btn.property("modeActive") is None
                assert window.play_mode_btn.width() == mode_width
                _assert_control_geometry(window)
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
        print("player controls visual consistency smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
