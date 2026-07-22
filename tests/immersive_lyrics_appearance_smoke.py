from __future__ import annotations

import os
import sys
import tempfile
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui.immersive_appearance import (
    ImmersiveAppearanceConfig,
    ImmersiveAppearanceDialog,
)
from app.ui.design_system import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS, set_active_theme_tokens
from app.ui.main_window import ImmersiveLyricsWindow, LyricsView


class StubMainWindow:
    def __init__(self, settings: dict | None = None) -> None:
        self.settings = deepcopy(settings or {})
        self.saved_updates: list[dict] = []
        self.immersive_lyrics_window = None
        self.close_count = 0
        self.current_song_path = "fixture-song.mp3"
        self.playback_position = 43210
        self.lyrics_request_count = 0

    def get_hush_settings(self) -> dict:
        return deepcopy(self.settings)

    def get_user_setting(self, key: str, default=None):
        return deepcopy(self.settings.get(key, default))

    def save_hush_settings(self, updates: dict, *, immediate: bool = False) -> bool:
        _ = immediate
        self.settings.update(deepcopy(updates))
        self.saved_updates.append(deepcopy(updates))
        return True

    def on_immersive_lyrics_closed(self) -> None:
        self.close_count += 1


def wait_until(app: QApplication, predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def create_image(path: Path, color: str, size: tuple[int, int] = (900, 540)) -> None:
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(color))
    assert image.save(str(path)), path


def config_checks() -> None:
    defaults = ImmersiveAppearanceConfig.from_settings({})
    assert defaults == ImmersiveAppearanceConfig.defaults()
    assert defaults.background_mode == "cover"
    assert defaults.lyrics_font_scale == 100
    assert defaults.background_transparency == 38

    legacy_default = ImmersiveAppearanceConfig.from_settings(
        {
            "immersive_cover_background_enabled": False,
            "immersive_background_alpha": 55,
        }
    )
    assert legacy_default.background_mode == "default"
    assert legacy_default.darkness == 55

    new_fields_win = ImmersiveAppearanceConfig.from_settings(
        {
            "immersive_background_mode": "custom",
            "immersive_background_darkness": 23,
            "immersive_cover_background_enabled": True,
            "immersive_background_alpha": 80,
            "immersive_background_custom_path": "kept.png",
        }
    )
    assert new_fields_win.background_mode == "custom"
    assert new_fields_win.darkness == 23
    assert new_fields_win.custom_image_path == "kept.png"

    invalid = ImmersiveAppearanceConfig.from_settings(
        {
            "immersive_background_mode": ["bad"],
            "immersive_cover_background_enabled": "bad",
            "immersive_background_blur": -10,
            "immersive_background_darkness": 500,
            "immersive_background_image_opacity": 0,
            "immersive_background_fill_mode": "stretch",
            "immersive_background_transparency": 500,
            "immersive_lyrics_font_scale": 999,
        }
    )
    assert invalid.background_mode == "cover"
    assert invalid.blur_radius == 0
    assert invalid.darkness == 90
    assert invalid.image_opacity == 20
    assert invalid.fill_mode == "cover"
    assert invalid.background_transparency == 85
    assert invalid.lyrics_font_scale == 160

    invalid_type = ImmersiveAppearanceConfig.from_settings(
        {"immersive_lyrics_font_scale": {"bad": True}}
    )
    assert invalid_type.lyrics_font_scale == 100


def _rgba_alpha(value: str) -> int:
    assert value.startswith("rgba(") and value.endswith(")"), value
    return int(value[:-1].rsplit(",", 1)[1].strip())


def _qss_rule(qss: str, selector: str) -> str:
    start = qss.index(selector)
    end = qss.index("}", start) + 1
    return qss[start:end]


def overlay_style_checks(app: QApplication) -> None:
    """Keep translucent immersive chrome scoped without changing its geometry."""
    main = StubMainWindow()
    window = ImmersiveLyricsWindow(main)
    main.immersive_lyrics_window = window
    window.resize(1100, 720)
    window.show()
    assert wait_until(app, lambda: window.isVisible())

    header_size = window.control_header.size()
    footer_size = window.footer.size()
    header_margins = window.control_header.layout().contentsMargins()
    footer_margins = window.footer.layout().contentsMargins()
    header_layout = window.control_header.layout()
    source = (PROJECT_ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    immersive_window_source = source[
        source.index("class ImmersiveLyricsWindow") : source.index("class MainWindow")
    ]
    assert "self.immersive_progress_slider.sliderPressed.connect(" in source
    assert "self.immersive_progress_slider.sliderReleased.connect(" in source
    assert "self.immersive_volume_slider.valueChanged.connect(" in source
    assert "self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)" in source
    assert window.accessibleName() == "沉浸歌词"
    assert not hasattr(window, "immersive_title")
    assert 'QLabel("沉浸歌词")' not in immersive_window_source
    assert "self.immersive_title" not in immersive_window_source
    assert header_layout.count() == 4
    assert header_layout.itemAt(0).spacerItem() is not None
    assert [header_layout.itemAt(index).widget() for index in range(1, 4)] == [
        window.fullscreen_btn,
        window.display_settings_btn,
        window.close_btn,
    ]

    try:
        for resolved_mode, tokens in (
            ("dark", DARK_THEME_TOKENS),
            ("light", LIGHT_THEME_TOKENS),
        ):
            set_active_theme_tokens(resolved_mode)
            window.apply_immersive_style()
            app.processEvents()
            qss = window.styleSheet()

            assert (
                "QFrame#immersiveControlHeader { background: transparent; border: none;"
                in qss
            )
            assert "QLabel#immersivePageTitle" not in qss
            assert f"QPushButton#immersiveButton {{ background: {tokens['immersive_button_surface']};" in qss
            assert f"QPushButton#immersiveButton:hover {{ background: {tokens['immersive_button_hover_surface']};" in qss
            assert f"QPushButton#immersiveButton:pressed {{ background: {tokens['immersive_button_pressed_surface']};" in qss
            assert f"border: 1px solid {tokens['immersive_button_border']};" in qss
            assert f"QFrame#immersivePlaybackFooter {{ background: {tokens['immersive_player_surface']};" in qss
            assert f"border: 1px solid {tokens['immersive_player_border']};" in qss
            assert f"QLabel#immersiveTimeLabel {{ color: {tokens['immersive_player_secondary_text']};" in qss
            surface_alpha = _rgba_alpha(tokens["immersive_player_surface"])
            border_alpha = _rgba_alpha(tokens["immersive_player_border"])
            if resolved_mode == "dark":
                assert 90 <= surface_alpha <= 115
            else:
                assert 80 <= surface_alpha <= 100
            assert 0 <= border_alpha < surface_alpha

            play_button_rules = {
                "normal": _qss_rule(qss, "QPushButton#immersiveTransportPlayButton {"),
                "hover": _qss_rule(qss, "QPushButton#immersiveTransportPlayButton:hover {"),
                "pressed": _qss_rule(qss, "QPushButton#immersiveTransportPlayButton:pressed {"),
                "focus": _qss_rule(qss, "QPushButton#immersiveTransportPlayButton:focus {"),
            }
            assert f"background: {tokens['accent']};" in play_button_rules["normal"]
            for rule in play_button_rules.values():
                assert "border: none;" in rule
                assert "border: 1px solid" not in rule
                assert "border-color:" not in rule
                assert "#ffffff" not in rule.casefold()
                assert "rgba(255, 255, 255" not in rule

            assert "QFrame#immersivePlaybackFooter QSlider#immersiveProgressSlider," in qss
            assert "QFrame#immersivePlaybackFooter QSlider#immersiveVolumeSlider:focus" in qss
            assert "background: transparent; border: none; outline: none;" in qss
            groove_rule = _qss_rule(
                qss,
                "QFrame#immersivePlaybackFooter QSlider#immersiveProgressSlider::groove:horizontal,",
            )
            add_page_rule = _qss_rule(
                qss,
                "QFrame#immersivePlaybackFooter QSlider#immersiveProgressSlider::add-page:horizontal,",
            )
            sub_page_rule = _qss_rule(
                qss,
                "QFrame#immersivePlaybackFooter QSlider#immersiveProgressSlider::sub-page:horizontal,",
            )
            for rule in (groove_rule, add_page_rule, sub_page_rule):
                assert "height: 4px;" in rule
                assert "border: none;" in rule
                assert "border-radius: 2px;" in rule
            assert "QSlider#immersiveProgressSlider:focus::handle:horizontal" in qss

            assert window.control_header.size() == header_size
            assert window.footer.size() == footer_size
            assert window.control_header.layout().contentsMargins() == header_margins
            assert window.footer.layout().contentsMargins() == footer_margins
    finally:
        set_active_theme_tokens("dark")
        window.close()
        assert wait_until(app, lambda: not window.isVisible())
        assert wait_until(app, lambda: not window.background_view.task_running)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def background_checks(app: QApplication, root: Path) -> tuple[dict, int]:
    main = StubMainWindow({"unrelated_setting": {"preserved": True}})
    window = ImmersiveLyricsWindow(main)
    main.immersive_lyrics_window = window
    window.resize(1100, 720)
    window.show()
    assert wait_until(app, lambda: window.isVisible())
    window.set_controls_always_visible(True)
    assert not window.auto_hide_enabled
    assert main.settings["immersive_auto_hide_ui"] is False
    window.set_controls_always_visible(False)
    assert window.auto_hide_enabled
    assert main.settings["immersive_auto_hide_ui"] is True

    pure_default = replace(
        ImmersiveAppearanceConfig.defaults(),
        background_mode="default",
    )
    window.apply_appearance_config(pure_default, persist=True)
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and "纯色" in window.background_view.status_text,
    )

    translucent = replace(
        pure_default,
        background_mode="translucent",
        background_transparency=62,
    )
    translucent_tasks = window.background_view.task_start_count
    window.apply_appearance_config(translucent, persist=True)
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and "半透明" in window.background_view.status_text,
    )
    background_color = (
        window.background_view.grab().toImage().pixelColor(10, 10)
    )
    assert 90 <= background_color.alpha() <= 105
    assert window.windowOpacity() == 1.0
    assert window.header_opacity_effect.opacity() == 1.0
    assert window.background_view.task_start_count == translucent_tasks
    assert main.settings["immersive_background_transparency"] == 62

    custom_path = root / "custom-background.png"
    create_image(custom_path, "#315c9b", (1600, 1000))
    custom_config = replace(
        pure_default,
        background_mode="custom",
        custom_image_path=str(custom_path),
        blur_radius=18,
        darkness=42,
        image_opacity=76,
        fill_mode="contain",
        lyrics_font_scale=115,
    )
    window.apply_appearance_config(custom_config, persist=True)
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and window.background_view.rendered_source_key.startswith("custom:")
        and not window.background_view.task_running,
    )
    assert window.background_view.rendered_source_key.startswith("custom:")
    assert main.settings["immersive_background_custom_path"] == str(custom_path)
    assert main.settings["immersive_lyrics_font_scale"] == 115
    assert main.settings["unrelated_setting"] == {"preserved": True}

    custom_path.unlink()
    window.background_view.revalidate_custom_image()
    assert wait_until(app, lambda: window.background_view.fallback_active)
    assert "回退默认背景" in window.background_view.status_text
    assert window.appearance_config.custom_image_path == str(custom_path)
    assert main.settings["immersive_background_custom_path"] == str(custom_path)

    red = QImage(800, 600, QImage.Format.Format_ARGB32_Premultiplied)
    red.fill(QColor("#a33131"))
    blue = QImage(800, 600, QImage.Format.Format_ARGB32_Premultiplied)
    blue.fill(QColor("#315ca3"))
    cover_config = replace(custom_config, background_mode="cover", blur_radius=12)
    window.apply_appearance_config(cover_config, persist=True)
    window.update_background_cover("local:track-a", QPixmap.fromImage(red))
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and "track-a" in window.background_view.rendered_source_key,
    )

    window.update_background_cover("local:track-b", QPixmap.fromImage(blue))
    assert not window.background_view.fallback_active
    assert "track-a" in window.background_view.rendered_source_key
    assert "继续显示上一首背景" in window.background_view.status_text
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and "track-b" in window.background_view.rendered_source_key,
    )

    window.update_background_cover("local:track-c", None)
    assert not window.background_view.fallback_active
    assert "track-b" in window.background_view.rendered_source_key
    window.mark_background_cover_unavailable("local:track-c")
    assert window.background_view.fallback_active
    assert "track-b" not in window.background_view.rendered_source_key
    assert wait_until(app, lambda: not window.background_view.task_running)
    assert window.background_view.fallback_active

    window.update_background_cover("local:rapid-a", QPixmap.fromImage(red))
    window.update_background_cover("local:rapid-b", QPixmap.fromImage(blue))
    window.update_background_cover("local:rapid-final", QPixmap.fromImage(red))
    assert wait_until(
        app,
        lambda: not window.background_view.fallback_active
        and "rapid-final" in window.background_view.rendered_source_key
        and not window.background_view.task_running,
    )

    paint_only_tasks = window.background_view.task_start_count
    window.apply_appearance_config(
        replace(window.appearance_config, darkness=17, image_opacity=63),
        persist=False,
    )
    assert wait_until(app, lambda: not window.background_view.task_running)
    assert window.background_view.task_start_count == paint_only_tasks

    task_count_before = window.background_view.task_start_count
    for blur in range(0, 41):
        window.apply_appearance_config(
            replace(window.appearance_config, blur_radius=blur),
            persist=False,
        )
    assert wait_until(
        app,
        lambda: not window.background_view.task_running
        and window.appearance_config.blur_radius == 40,
    )
    assert window.background_view.task_start_count - task_count_before <= 2
    assert window.background_view.cache_entry_count <= 3
    assert window.background_view.cache_bytes <= 64 * 1024 * 1024

    render_before_resize = window.background_view.render_count
    window.resize(1280, 760)
    assert window.background_view.geometry() == window.rect()
    assert wait_until(
        app,
        lambda: window.background_view.render_count > render_before_resize
        and not window.background_view.task_running,
    )

    # Custom mode remains stable while songs and their covers change.
    recreated_custom = root / "custom-background-restored.png"
    create_image(recreated_custom, "#526f46")
    custom_stable = replace(
        window.appearance_config,
        background_mode="custom",
        custom_image_path=str(recreated_custom),
    )
    window.apply_appearance_config(custom_stable, persist=False)
    assert wait_until(app, lambda: not window.background_view.fallback_active)
    stable_source = window.background_view.rendered_source_key
    stable_render_count = window.background_view.render_count
    window.update_background_cover("local:custom-song-a", QPixmap.fromImage(red))
    window.update_background_cover("local:custom-song-b", QPixmap.fromImage(blue))
    app.processEvents()
    assert window.background_view.rendered_source_key == stable_source
    assert window.background_view.render_count == stable_render_count

    persisted = deepcopy(main.settings)
    task_count = window.background_view.task_start_count
    window.apply_appearance_config(
        replace(window.appearance_config, blur_radius=39),
        persist=False,
    )
    window.background_view._debounce_timer.stop()
    window.background_view._render_latest()
    assert window.background_view.task_start_count >= task_count + 1
    window.close()
    assert wait_until(app, lambda: not window.isVisible())
    assert window.background_view._closed is True
    assert wait_until(app, lambda: not window.background_view.task_running)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return persisted, window.background_view.task_start_count


def font_checks(app: QApplication, persisted: dict) -> None:
    main = StubMainWindow(persisted)
    window = ImmersiveLyricsWindow(main)
    main.immersive_lyrics_window = window
    window.resize(1100, 720)
    window.show()
    assert wait_until(app, lambda: window.isVisible())
    assert window.appearance_config.lyrics_font_scale == 115

    lyrics = [
        (0, "中文逐字高亮测试"),
        (1000, "English word highlight test"),
        (2000, "翻译歌词测试"),
        (3000, "可以继续滚动的歌词行"),
    ]
    window.set_lyrics(lyrics)
    window.update_position(1500, lyrics)
    assert window.lyrics_view.current_index == 1
    label_ids = [id(label) for label in window.lyrics_view.labels]
    label_texts = [label.text() for label in window.lyrics_view.labels]
    state_snapshot = [label.property("lyricState") for label in window.lyrics_view.labels]
    position_before = main.playback_position
    requests_before = main.lyrics_request_count
    background_tasks_before = window.background_view.task_start_count
    point_size_before = window.lyrics_view.labels[1].font().pointSizeF()
    refresh_before = window.lyrics_view.layout_refresh_count

    window.apply_appearance_config(
        replace(window.appearance_config, lyrics_font_scale=140),
        persist=True,
    )
    assert wait_until(
        app,
        lambda: not window.font_scale_timer.isActive()
        and window.lyrics_view.layout_refresh_count > refresh_before,
    )
    point_size_after = window.lyrics_view.labels[1].font().pointSizeF()
    assert point_size_after > point_size_before
    assert window.lyrics_view.current_index == 1
    assert [id(label) for label in window.lyrics_view.labels] == label_ids
    assert [label.text() for label in window.lyrics_view.labels] == label_texts
    assert [label.property("lyricState") for label in window.lyrics_view.labels] == state_snapshot
    assert main.playback_position == position_before
    assert main.lyrics_request_count == requests_before
    assert window.background_view.task_start_count == background_tasks_before
    assert "中文" in window.lyrics_view.labels[0].text()
    assert "English" in window.lyrics_view.labels[1].text()

    outside = LyricsView()
    outside.set_lyrics(lyrics)
    outside_font_before = outside.labels[0].font().pointSizeF()
    window.apply_appearance_config(
        replace(window.appearance_config, lyrics_font_scale=70),
        persist=False,
    )
    assert wait_until(app, lambda: not window.font_scale_timer.isActive())
    assert outside.labels[0].font().pointSizeF() == outside_font_before
    assert window.lyrics_view.current_index == 1
    assert window.lyrics_view.verticalScrollBar().maximum() >= 0

    window.apply_appearance_config(
        replace(window.appearance_config, lyrics_font_scale=160),
        persist=False,
    )
    assert wait_until(app, lambda: not window.font_scale_timer.isActive())
    assert window.lyrics_view.current_index == 1
    assert window.lyrics_view.verticalScrollBar().maximum() >= 0

    scale_before_mode_change = window.appearance_config.lyrics_font_scale
    window.showFullScreen()
    app.processEvents()
    window.show_windowed()
    app.processEvents()
    assert window.appearance_config.lyrics_font_scale == scale_before_mode_change

    emitted: list[ImmersiveAppearanceConfig] = []
    dialog = ImmersiveAppearanceDialog(
        window.appearance_config,
        window,
        controls_always_visible=True,
    )
    assert dialog.windowTitle() == "沉浸歌词显示设置"
    assert dialog.findChild(QFrame, "appearanceBackgroundSection") is not None
    assert dialog.findChild(QFrame, "appearanceLyricsSection") is not None
    assert dialog.findChild(QFrame, "appearanceSyncSection") is not None
    assert dialog.findChild(QCheckBox).text() == "控制栏始终显示"
    assert [dialog.mode_combo.itemText(index) for index in range(dialog.mode_combo.count())] == [
        "封面模糊",
        "纯色背景",
        "半透明背景",
        "自定义图片",
    ]
    dialog.configChanged.connect(emitted.append)
    translucent_index = dialog.mode_combo.findData("translucent")
    dialog.mode_combo.setCurrentIndex(translucent_index)
    assert emitted and emitted[-1].background_mode == "translucent"
    assert dialog.background_transparency_slider.isEnabled()
    assert not dialog.opacity_slider.isEnabled()
    always_visible: list[bool] = []
    dialog.controlsAlwaysVisibleChanged.connect(always_visible.append)
    dialog.controls_always_visible.setChecked(False)
    assert always_visible == [False]
    dialog.reset_defaults()
    assert emitted and emitted[-1].lyrics_font_scale == 100
    assert emitted[-1].background_mode == "cover"
    window.apply_appearance_config(emitted[-1], persist=True)
    assert wait_until(app, lambda: not window.font_scale_timer.isActive())
    assert window.appearance_config.lyrics_font_scale == 100
    dialog.close()
    outside.deleteLater()

    saved = deepcopy(main.settings)
    window.close()
    assert wait_until(app, lambda: not window.isVisible())
    restarted = StubMainWindow(saved)
    restored_window = ImmersiveLyricsWindow(restarted)
    assert restored_window.appearance_config.lyrics_font_scale == 100
    assert restored_window.appearance_config.background_mode == "cover"
    restored_window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication([])
    config_checks()
    overlay_style_checks(app)
    supported_formats = {bytes(item).decode("ascii").casefold() for item in QImageReader.supportedImageFormats()}
    assert {"jpg", "jpeg", "png", "webp"}.issubset(supported_formats), supported_formats
    with tempfile.TemporaryDirectory(prefix="hushplayer_immersive_appearance_") as temp_dir:
        persisted, _task_count = background_checks(app, Path(temp_dir))
        font_checks(app, persisted)
    print("immersive lyrics appearance smoke: OK")


if __name__ == "__main__":
    main()
