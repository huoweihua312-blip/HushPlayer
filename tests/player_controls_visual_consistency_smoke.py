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

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.design_system import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS, UI_CONTROL_SIZES
from app.ui.main_window import MainWindow, PlayerProgressSlider, PlayerVolumeSlider


def _process_layout(app: QApplication, window: MainWindow, width: int) -> None:
    window.resize(width, 760)
    window._update_responsive_layout(force=True)
    for _ in range(4):
        app.processEvents()


def _qss_rule(qss: str, selector: str) -> str:
    start = qss.index(selector)
    end = qss.index("}", start) + 1
    return qss[start:end]


def _relative_luminance(color: str) -> float:
    value = color.lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in range(0, 6, 2)]

    def linearize(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter, darker = sorted((first_luminance, second_luminance), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


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


def _pixel_rgba(image, point: QPoint) -> tuple[int, int, int, int]:
    color = image.pixelColor(point)
    return (color.red(), color.green(), color.blue(), color.alpha())


def _assert_slider_has_no_background_block(
    app: QApplication,
    window: MainWindow,
    slider,
) -> None:
    """The 32px slider body must blend into the player surface around its track."""
    slider.setValue(50)
    slider.setEnabled(True)
    app.processEvents()

    def capture() -> tuple[tuple[int, int, int, int], ...]:
        image = window.player_bar.grab().toImage()
        origin = slider.mapTo(window.player_bar, QPoint(0, 0))
        x = origin.x() + max(2, slider.width() * 3 // 4)
        center_y = origin.y() + slider.height() // 2
        surface = _pixel_rgba(
            image,
            QPoint(x, max(1, origin.y() - 7)),
        )
        top = _pixel_rgba(image, QPoint(x, origin.y() + 2))
        bottom = _pixel_rgba(
            image,
            QPoint(x, origin.y() + slider.height() - 3),
        )
        groove = _pixel_rgba(image, QPoint(x, center_y))
        return surface, top, bottom, groove

    surface, top, bottom, groove = capture()
    assert top == surface, (slider.objectName(), "normal-top", surface, top)
    assert bottom == surface, (slider.objectName(), "normal-bottom", surface, bottom)
    assert groove != surface, (slider.objectName(), "normal-groove", surface, groove)

    slider.setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.mouseMove(slider, QPoint(slider.width() // 2, slider.height() // 2))
    app.processEvents()
    surface, top, bottom, _ = capture()
    assert top == surface, (slider.objectName(), "hover-focus-top", surface, top)
    assert bottom == surface, (slider.objectName(), "hover-focus-bottom", surface, bottom)

    slider.setEnabled(False)
    app.processEvents()
    surface, top, bottom, groove = capture()
    assert top == surface, (slider.objectName(), "disabled-top", surface, top)
    assert bottom == surface, (slider.objectName(), "disabled-bottom", surface, bottom)
    assert groove != surface, (slider.objectName(), "disabled-groove", surface, groove)
    slider.setEnabled(True)
    app.processEvents()


def run_test(app: QApplication) -> None:
    player_tokens = {
        "player_surface",
        "player_border",
        "player_surface_separator",
        "player_secondary_background",
        "player_secondary_border",
        "player_secondary_icon",
        "player_secondary_hover_background",
        "player_secondary_hover_border",
        "player_secondary_hover_icon",
        "player_secondary_pressed_background",
        "player_secondary_pressed_border",
        "player_secondary_disabled_background",
        "player_secondary_disabled_icon",
        "slider_groove",
        "slider_fill",
        "slider_handle",
        "slider_handle_border",
        "slider_handle_hover",
        "slider_disabled",
    }
    assert player_tokens.issubset(DARK_THEME_TOKENS)
    assert player_tokens.issubset(LIGHT_THEME_TOKENS)
    assert LIGHT_THEME_TOKENS["player_surface"] != LIGHT_THEME_TOKENS["surface"]
    assert LIGHT_THEME_TOKENS["player_surface_separator"] != LIGHT_THEME_TOKENS["player_surface"]
    assert LIGHT_THEME_TOKENS["player_secondary_background"] != LIGHT_THEME_TOKENS["player_surface"]
    assert UI_CONTROL_SIZES["player_slider_groove_height"] == 4
    assert UI_CONTROL_SIZES["player_slider_handle_size"] == 14
    assert _contrast_ratio(
        LIGHT_THEME_TOKENS["player_secondary_icon"],
        LIGHT_THEME_TOKENS["player_secondary_background"],
    ) >= 4.5
    assert _contrast_ratio(
        LIGHT_THEME_TOKENS["player_secondary_disabled_icon"],
        LIGHT_THEME_TOKENS["player_secondary_disabled_background"],
    ) >= 3.0

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
        assert isinstance(window.progress_slider, PlayerProgressSlider)
        assert isinstance(window.volume_slider, PlayerVolumeSlider)
        for slider in (window.progress_slider, window.volume_slider):
            local_qss = slider.styleSheet()
            assert "background: transparent" in local_qss
            assert "border-image: none" in local_qss
            assert "::groove" not in local_qss

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
            assert f"background: {tokens['player_surface']};" in qss
            assert f"border-top: 1px solid {tokens['player_surface_separator']};" in qss
            assert f"background: {tokens['player_secondary_background']};" in qss
            assert f"color: {tokens['player_secondary_icon']};" in qss
            assert f"background: {tokens['player_secondary_hover_background']};" in qss
            assert f"background: {tokens['player_secondary_pressed_background']};" in qss
            assert f"background: {tokens['player_secondary_disabled_background']};" in qss
            assert f"background: {tokens['slider_groove']};" in qss
            assert f"background: {tokens['slider_fill']};" in qss
            assert f"border: 1px solid {tokens['slider_handle_border']};" in qss
            assert "QFrame#playerBar QFrame#playerCenter, QFrame#playerBar QFrame#playerRight" in qss
            assert "QFrame#playerBar QSlider#progressSlider," in qss
            assert "QFrame#playerBar QSlider#volumeSlider:focus" in qss
            assert "QFrame#playerBar QSlider#progressSlider:disabled" in qss
            slider_root_rule = _qss_rule(
                qss,
                "QFrame#playerBar QSlider#progressSlider,",
            )
            assert "background: transparent;" in slider_root_rule
            assert "border: none;" in slider_root_rule
            assert "outline: none;" in slider_root_rule
            slider_parent_rule = _qss_rule(
                qss,
                "QFrame#playerBar QFrame#playerCenter,",
            )
            assert "background: transparent;" in slider_parent_rule
            assert "border: none;" in slider_parent_rule
            groove_rule = _qss_rule(
                qss,
                "QFrame#playerBar QSlider#progressSlider::groove:horizontal,",
            )
            add_page_rule = _qss_rule(
                qss,
                "QFrame#playerBar QSlider#progressSlider::add-page:horizontal,",
            )
            sub_page_rule = _qss_rule(
                qss,
                "QFrame#playerBar QSlider#progressSlider::sub-page:horizontal,",
            )
            for rule in (groove_rule, add_page_rule, sub_page_rule):
                assert "height: 4px;" in rule
                assert "border: none;" in rule
                assert "border-radius: 2px;" in rule
            handle_rule = _qss_rule(
                qss,
                "QFrame#playerBar QSlider#progressSlider::handle:horizontal,",
            )
            assert "width: 14px;" in handle_rule
            assert "height: 14px;" in handle_rule
            assert "margin: -5px 0;" in handle_rule
            assert "QFrame#playerBar QSlider#progressSlider:focus::handle:horizontal" in qss
            assert 'QSlider#progressSlider:disabled::groove:horizontal' in qss
            assert 'QPushButton#playerLyricsButton:pressed' in qss

            # Legacy stylesheet layers must not paint another player-slider
            # groove, fill, or handle behind the final scoped player rules.
            for legacy_qss in (
                window._style_sheet(),
                window.build_visual_polish_qss(),
                window.build_player_product_qss(),
            ):
                assert "QSlider#progressSlider::groove:horizontal" not in legacy_qss
                assert "QSlider#volumeSlider::groove:horizontal" not in legacy_qss
                assert "QSlider#progressSlider::add-page:horizontal" not in legacy_qss
                assert "QSlider#volumeSlider::add-page:horizontal" not in legacy_qss
                assert "QSlider#progressSlider::sub-page:horizontal" not in legacy_qss
                assert "QSlider#volumeSlider::sub-page:horizontal" not in legacy_qss

            main_play_rule = _qss_rule(
                qss,
                'QPushButton#transportPlayButton[playerPrimaryButton="true"]',
            )
            assert f"border: 1px solid {tokens['border']};" in main_play_rule

            liked_rule = _qss_rule(
                qss,
                'QPushButton#likeButton[playerFavoriteButton="true"][liked="true"]',
            )
            assert f"color: {tokens['danger']}" in liked_rule
            assert f"border-color: {tokens['player_secondary_border']}" in liked_rule
            assert f"border-color: {tokens['danger']}" not in liked_rule

            now_liked_rule = _qss_rule(qss, 'QPushButton#nowLikeButton[liked="true"]')
            assert f"background: {tokens['danger_soft']}" in now_liked_rule
            assert f"color: {tokens['danger']}" in now_liked_rule
            assert f"border-color: {tokens['player_secondary_border']}" in now_liked_rule
            assert f"border-color: {tokens['danger']}" not in now_liked_rule

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
            assert "self.volume_slider.valueChanged.connect(self.change_volume)" in source
            _assert_slider_has_no_background_block(app, window, window.progress_slider)
            _assert_slider_has_no_background_block(app, window, window.volume_slider)

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
