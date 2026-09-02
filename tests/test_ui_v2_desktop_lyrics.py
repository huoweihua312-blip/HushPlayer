from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.startup_diagnostics import StartupDiagnostics
from app.ui_v2.adapters.legacy_settings_bridge import SettingsBridgeError
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.shell.desktop_lyrics_window import (
    DesktopLyricsWindow,
    clamp_desktop_lyrics_position,
    normalize_desktop_lyrics_font,
)
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES, get_theme


class StartupDiagnosticsTests(unittest.TestCase):
    def test_marks_identify_slowest_stage_and_write_failures_are_safe(self) -> None:
        diagnostics = StartupDiagnostics()
        diagnostics.mark("fast")
        time.sleep(0.002)
        diagnostics.mark("slow")
        self.assertEqual([item["name"] for item in diagnostics.marks], ["fast", "slow"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "startup-performance.log"
            self.assertTrue(diagnostics.write(directory))
            text = path.read_text(encoding="utf-8")
            self.assertIn("slowest_stage=slow", text)
        self.assertFalse(diagnostics.write(None))


class DesktopLyricsHelpersTests(unittest.TestCase):
    def test_font_normalization_only_allows_bundled_open_fonts(self) -> None:
        self.assertEqual(normalize_desktop_lyrics_font(OPEN_FONT_FAMILIES[1]), OPEN_FONT_FAMILIES[1])
        self.assertEqual(normalize_desktop_lyrics_font("Segoe UI"), OPEN_FONT_FAMILIES[0])

    def test_position_is_clamped_to_available_work_area(self) -> None:
        position = clamp_desktop_lyrics_position(
            QPoint(-20, 5000),
            QSize(300, 120),
            QRect(10, 20, 1000, 700),
        )
        self.assertEqual(position, QPoint(10, 600))


class DesktopLyricsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.playback = PlaybackAdapter(timer_enabled=False)
        self.lyrics = LyricsAdapter()
        self.window = DesktopLyricsWindow(
            self.playback,
            self.lyrics,
            get_theme("dark"),
        )

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_defaults_to_transparent_input_and_reuses_lyric_adapter(self) -> None:
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )
        self.assertIs(self.window._lyrics_adapter, self.lyrics)
        self.window.apply_settings(
            {
                "floating_lyrics_font_family": "Segoe UI",
                "floating_lyrics_width": 600,
                "floating_lyrics_height": 140,
                "floating_lyrics_passthrough": False,
            }
        )
        self.assertEqual(self.window.width(), 600)
        self.assertEqual(self.window.height(), 140)
        self.assertEqual(
            self.window._settings["floating_lyrics_font_family"], OPEN_FONT_FAMILIES[0]
        )
        self.assertFalse(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )

    def test_reset_position_emits_only_a_position_update(self) -> None:
        changes: list[tuple[int, int]] = []
        self.window.position_changed.connect(lambda x, y: changes.append((x, y)))
        self.window.reset_position()
        self.assertEqual(len(changes), 1)
        self.assertGreaterEqual(changes[0][0], 0)
        self.assertGreaterEqual(changes[0][1], 0)

    def test_only_lyrics_are_rendered_and_empty_state_stays_enabled_but_hidden(self) -> None:
        track = next(track for track in create_mock_tracks(80) if not track.is_missing)
        self.lyrics.set_track(track)
        self.window.show_for_current_screen()
        self.app.processEvents()

        self.assertTrue(self.window.is_enabled)
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window._main_label.text())
        self.assertFalse(hasattr(self.window, "_track_label"))
        self.assertFalse(hasattr(self.window, "_status_label"))
        self.assertIn("background: transparent", self.window._surface.styleSheet())

        self.lyrics.load_mock_scenario("empty")
        self.app.processEvents()
        self.assertTrue(self.window.is_enabled)
        self.assertFalse(self.window.isVisible())

    def test_secondary_lyric_has_a_stable_visual_offset(self) -> None:
        margins = self.window._secondary_layout.contentsMargins()
        self.assertGreater(margins.left(), margins.right())

    def test_secondary_lyric_uses_next_line_then_current_translation(self) -> None:
        track = next(track for track in create_mock_tracks(80) if not track.is_missing)
        self.lyrics.set_track(track)
        self.window._render()
        self.assertIsNotNone(self.lyrics.next_line)
        self.assertEqual(self.window._secondary_label.text(), self.lyrics.next_line.text)

        self.lyrics.load_mock_scenario("translation")
        self.window._render()
        self.assertTrue(self.lyrics.active_line.translation)
        self.assertEqual(
            self.window._secondary_label.text(),
            self.lyrics.active_line.translation,
        )

    def test_long_lyric_expands_width_and_stays_at_two_rows(self) -> None:
        self.window.show()
        self.window.apply_settings(
            {"floating_lyrics_font_size": 84, "floating_lyrics_width": 420}
        )
        self.app.processEvents()
        self.window._main_label.setText("人" * 20)
        self.window._secondary_label.setText("下一句")
        self.window._secondary_label.setVisible(True)
        self.window._apply_content_height_floor()
        expanded_width = self.window.width()
        expanded_height = self.window.height()
        self.assertFalse(self.window._main_label.wordWrap())
        self.assertFalse(self.window._secondary_label.wordWrap())
        self.assertGreater(expanded_width, 420)
        self.assertLessEqual(expanded_height, 220)
        self.assertEqual(
            self.window._main_label.height(),
            self.window._main_label.fontMetrics().height(),
        )

        self.window._main_label.setText("短句")
        self.window._apply_content_height_floor()
        self.assertEqual(self.window.width(), expanded_width)
        self.assertEqual(self.window.height(), expanded_height)

    def test_font_size_uses_pixels_and_only_one_lock_button_is_created(self) -> None:
        self.window.show()
        self.window.apply_settings({"floating_lyrics_font_size": 22})
        self.app.processEvents()
        self.assertEqual(self.window._main_label.font().pixelSize(), 22)
        self.assertEqual(self.window._secondary_label.font().pixelSize(), 14)
        compact_height = self.window.height()
        self.window.apply_settings({"floating_lyrics_font_size": 84})
        self.app.processEvents()
        self.assertEqual(self.window._main_label.font().pixelSize(), 84)
        self.assertEqual(self.window._secondary_label.font().pixelSize(), 42)
        self.assertGreater(self.window.height(), compact_height)
        self.assertGreaterEqual(
            self.window.height(),
            self.window._main_label.fontMetrics().height()
            + self.window._secondary_label.fontMetrics().height()
            + 28,
        )
        self.assertFalse(hasattr(self.window, "_toolbar"))
        self.assertFalse(hasattr(self.window, "_reset_button"))
        self.assertFalse(hasattr(self.window, "_close_button"))
        self.assertFalse(hasattr(self.window, "_settings_button"))
        self.assertEqual(self.window._lock_button.size(), QSize(32, 32))
        self.assertEqual(
            self.window._lock_button.x(),
            self.window.frameGeometry().left()
            + (self.window.width() - self.window._lock_button.width()) // 2,
        )

    def test_live_preview_updates_font_and_expands_two_row_surface(self) -> None:
        self.window.show()
        self.window.apply_settings(
            {
                "floating_lyrics_font_size": 22,
                "floating_lyrics_width": 980,
                "floating_lyrics_height": 135,
            }
        )
        self.window._main_label.setText(
            "人和人之间大杂烩来来浔浔来来浔浔人和人之间大杂烩来来浔浔"
        )
        self.window._secondary_label.setText("这段记忆随雪花融化")
        self.window._secondary_label.setVisible(True)
        self.window._render_timer.stop()

        self.window.apply_settings(
            {"floating_lyrics_font_size": 84, "floating_lyrics_width": 420},
            live_preview=True,
        )
        self.app.processEvents()

        self.assertEqual(self.window._main_label.font().pixelSize(), 84)
        self.assertGreater(self.window.width(), 420)
        self.assertLessEqual(self.window.height(), 220)
        self.assertEqual(self.window._surface.size(), self.window.size())
        self.assertEqual(self.window._surface.layout().geometry(), self.window._surface.rect())
        self.assertFalse(self.window._main_label.wordWrap())
        self.assertFalse(self.window._secondary_label.wordWrap())
        self.assertEqual(
            self.window._main_label.height(),
            self.window._main_label.fontMetrics().height(),
        )
        self.assertFalse(self.window._render_timer.isActive())

    def test_live_width_expansion_preserves_visual_center(self) -> None:
        self.window.apply_settings(
            {
                "floating_lyrics_font_size": 22,
                "floating_lyrics_width": 420,
                "floating_lyrics_height": 135,
            }
        )
        self.window._render_timer.stop()
        self.window._has_renderable_lyric = True
        self.window.show()
        self.window.move(40, 40)
        self.app.processEvents()
        self.window._main_label.setText("冬至的白雪")
        self.window._secondary_label.setText("下一句")
        self.window._secondary_label.setVisible(True)
        before = QPoint(self.window.frameGeometry().center())

        self.window.apply_settings(
            {"floating_lyrics_font_size": 84, "floating_lyrics_width": 420},
            live_preview=True,
        )
        self.app.processEvents()

        self.assertGreater(self.window.width(), 420)
        self.assertEqual(self.window.frameGeometry().center(), before)

    def test_drag_pauses_cursor_polling_and_hides_lock_affordance(self) -> None:
        self.window.apply_settings({"floating_lyrics_passthrough": False})
        self.window._render_timer.stop()
        self.window._has_renderable_lyric = True
        self.window.show()
        self.app.processEvents()
        # Simulate the hover state; offscreen Qt does not always report the
        # cursor over this separate top-level affordance reliably.
        self.window._lock_button.show()
        self.app.processEvents()
        self.assertTrue(self.window._lock_button.isVisible())
        local_position = QPoint(100, 60)
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(local_position),
            QPointF(self.window.mapToGlobal(local_position)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.assertTrue(self.window._begin_drag(event))
        self.assertFalse(self.window._cursor_timer.isActive())
        self.assertTrue(
            self.window._system_drag_active or self.window._drag_move_timer.isActive()
        )
        self.assertFalse(self.window._lock_button.isVisible())
        self.window._finish_drag(persist_position=False)
        self.assertFalse(self.window._drag_move_timer.isActive())
        self.assertTrue(self.window._cursor_timer.isActive())

    def test_unlocked_right_release_requests_settings_once_without_starting_drag(self) -> None:
        requests: list[QPoint] = []
        self.window.settings_requested.connect(requests.append)
        self.window.apply_settings({"floating_lyrics_passthrough": False})
        track = next(track for track in create_mock_tracks(80) if not track.is_missing)
        self.lyrics.set_track(track)
        self.window.show_for_current_screen()
        self.app.processEvents()
        local_position = QPoint(120, 70)
        global_position = self.window.mapToGlobal(local_position)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(local_position),
            QPointF(global_position),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(local_position),
            QPointF(global_position),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(self.window._surface, press)
        self.assertEqual(requests, [])
        QApplication.sendEvent(self.window._surface, release)
        self.app.processEvents()
        self.assertEqual(requests, [global_position])
        self.assertIsNone(self.window._drag_offset)

    def test_settings_visibility_cancels_drag_and_blocks_new_pointer_gestures(self) -> None:
        self.window.apply_settings({"floating_lyrics_passthrough": False})
        self.window.show()
        self.app.processEvents()
        local_position = QPoint(100, 60)
        global_position = self.window.mapToGlobal(local_position)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(local_position),
            QPointF(global_position),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(self.window._begin_drag(press))
        self.assertIsNotNone(self.window._drag_offset)
        self.window.set_settings_popover_visible(True)
        self.assertIsNone(self.window._drag_offset)
        self.assertFalse(self.window._mouse_grabbed)
        self.assertFalse(self.window._begin_drag(press))

    def test_cursor_poll_ends_drag_after_left_button_is_lost(self) -> None:
        self.window.apply_settings({"floating_lyrics_passthrough": False})
        track = next(track for track in create_mock_tracks(80) if not track.is_missing)
        self.lyrics.set_track(track)
        self.window.show_for_current_screen()
        self.app.processEvents()
        local_position = QPoint(100, 60)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(local_position),
            QPointF(self.window.mapToGlobal(local_position)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(self.window._begin_drag(press))
        self.window._poll_cursor()
        self.assertIsNone(self.window._drag_offset)
        self.assertFalse(self.window._mouse_grabbed)

    def test_locked_hover_keeps_input_passthrough_and_lock_button_requests_change(self) -> None:
        requested_states: list[bool] = []
        visibility_changes: list[bool] = []
        self.window.lock_state_change_requested.connect(requested_states.append)
        self.window.visible_changed.connect(visibility_changes.append)
        track = next(track for track in create_mock_tracks(80) if not track.is_missing)
        self.lyrics.set_track(track)
        self.window.show_for_current_screen()
        self.app.processEvents()
        visibility_changes.clear()
        self.assertTrue(self.window.is_locked)
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )

        self.window._show_lock_affordance()
        self.app.processEvents()
        self.assertTrue(self.window.is_locked)
        self.assertTrue(self.window._lock_button.isVisible())
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )
        self.assertTrue(self.window._lock_button.isWindow())
        self.assertIsNone(self.window._lock_button.parentWidget())
        self.assertEqual(self.window._lock_button.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertFalse(
            bool(
                self.window._lock_button.windowFlags()
                & Qt.WindowType.WindowTransparentForInput
            )
        )
        self.assertEqual(visibility_changes, [])
        self.window._lock_button.click()
        self.assertEqual(requested_states, [False])

        self.window._hide_lock_affordance()
        self.app.processEvents()
        self.assertTrue(self.window.is_locked)
        self.assertFalse(self.window._lock_button.isVisible())
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )
        self.assertEqual(visibility_changes, [])

        self.window.apply_settings({"floating_lyrics_passthrough": False})
        self.window._lock_button.click()
        self.assertEqual(requested_states, [False, True])


class DesktopLyricsMainWindowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_player_bar_exposes_desktop_lyrics_without_changing_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(settings_path=Path(directory) / "settings.json")
            try:
                self.assertEqual(window.navigation_adapter.route, "browse")
                self.assertEqual(window.player_bar.desktop_lyrics_button.toolTip(), "桌面歌词")
                self.assertEqual(window.player_bar.desktop_lyrics_button.icon_name, "desktop_lyrics")
                window._on_player_bar_action("desktop_lyrics")
                self.app.processEvents()
                self.assertIsNotNone(window.desktop_lyrics_window)
                self.assertTrue(window.desktop_lyrics_window.is_enabled)
                self.assertFalse(window.desktop_lyrics_window.isVisible())
                self.assertTrue(window.player_bar.desktop_lyrics_button.active)
                self.assertEqual(window.navigation_adapter.route, "browse")
                window._on_player_bar_action("desktop_lyrics")
                self.assertFalse(window.desktop_lyrics_window.is_enabled)
                self.assertFalse(window.player_bar.desktop_lyrics_button.active)
            finally:
                window.close()
                self.app.processEvents()

    def test_player_bar_button_only_toggles_lyrics_without_context_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            window = MainWindow(settings_path=settings_path)
            try:
                window.resize(1200, 800)
                window.show()
                self.app.processEvents()
                self.assertIsNone(window.desktop_lyrics_window)
                self.assertEqual(
                    window.player_bar.desktop_lyrics_button.contextMenuPolicy(),
                    Qt.ContextMenuPolicy.NoContextMenu,
                )
                self.assertIsNone(window.desktop_lyrics_window)
                self.assertEqual(window.navigation_adapter.route, "browse")
                window._on_player_bar_action("desktop_lyrics")
                self.app.processEvents()
                self.assertIsNotNone(window.desktop_lyrics_window)
                self.assertTrue(window.desktop_lyrics_window.is_enabled)
                self.assertIsNone(window.desktop_lyrics_settings_popover)
            finally:
                window.close()
                self.app.processEvents()

    def test_desktop_context_request_opens_settings_near_global_position(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(settings_path=Path(directory) / "settings.json")
            try:
                window.resize(1200, 800)
                window.show()
                self.app.processEvents()
                desktop = window._ensure_desktop_lyrics_window()
                requested_position = QPoint(420, 360)
                desktop.settings_requested.emit(requested_position)
                self.app.processEvents()
                popover = window.desktop_lyrics_settings_popover
                self.assertIsNotNone(popover)
                self.assertTrue(popover.isVisible())
                screen = QGuiApplication.screenAt(requested_position)
                if screen is not None:
                    available = screen.availableGeometry()
                    self.assertTrue(available.contains(popover.frameGeometry()))
                self.assertIsNone(desktop._drag_offset)
                self.assertEqual(window.navigation_adapter.route, "browse")
            finally:
                window.close()
                self.app.processEvents()

    def test_lock_button_uses_existing_preview_and_auto_save_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            window = MainWindow(settings_path=settings_path)
            try:
                desktop = window._ensure_desktop_lyrics_window()
                self.assertTrue(desktop.is_locked)
                desktop._lock_button.click()
                self.app.processEvents()
                self.assertFalse(desktop.is_locked)
                self.assertTrue(window._desktop_lyrics_settings_save_timer.isActive())
                window._desktop_lyrics_settings_save_timer.stop()
                self.assertTrue(window._save_pending_desktop_lyrics_settings())
                document = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertFalse(document["floating_lyrics_passthrough"])
            finally:
                window.close()
                self.app.processEvents()

    def test_tray_unlock_uses_existing_settings_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            window = MainWindow(settings_path=settings_path)
            try:
                desktop = window._ensure_desktop_lyrics_window()
                window._on_player_bar_action("desktop_lyrics")
                self.app.processEvents()
                self.assertTrue(desktop.is_enabled)
                self.assertTrue(desktop.is_locked)
                action = window.close_behavior_controller.desktop_lyrics_unlock_action
                self.assertTrue(action.isVisible())
                action.trigger()
                self.app.processEvents()
                self.assertFalse(desktop.is_locked)
                self.assertFalse(action.isVisible())
                window._desktop_lyrics_settings_save_timer.stop()
                self.assertTrue(window._save_pending_desktop_lyrics_settings())
                document = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertFalse(document["floating_lyrics_passthrough"])
            finally:
                window.close()
                self.app.processEvents()

    def test_quick_settings_preview_and_save_are_coalesced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            window = MainWindow(settings_path=settings_path)
            saves: list[int] = []
            window.settings_bridge.save_succeeded.connect(
                lambda snapshot: saves.append(snapshot.get("floating_lyrics_font_size"))
            )
            try:
                desktop = window._ensure_desktop_lyrics_window()
                popover = window._ensure_desktop_lyrics_settings_popover()
                popover.set_values(window._settings_snapshot.to_dict())
                popover.font_size_slider.slider.setValue(50)
                popover.font_size_slider.slider.setValue(58)
                popover.font_size_slider.slider.setValue(64)
                self.app.processEvents()
                self.assertTrue(window._desktop_lyrics_settings_preview_timer.isActive())
                QTest.qWait(60)
                self.app.processEvents()
                self.assertEqual(desktop._main_label.font().pixelSize(), 64)
                self.assertTrue(window._desktop_lyrics_settings_save_timer.isActive())
                self.assertEqual(window._desktop_lyrics_settings_save_timer.interval(), 250)
                self.assertFalse(settings_path.exists())
                window._desktop_lyrics_settings_save_timer.stop()
                self.assertTrue(window._save_pending_desktop_lyrics_settings())
                document = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(document["floating_lyrics_font_size"], 64)
                self.assertEqual(saves, [64])
                style = popover.font_size_slider.slider.styleSheet()
                self.assertIn("QSlider { background: transparent; border: 0;", style)
            finally:
                window.close()
                self.app.processEvents()

    def test_quick_settings_save_failure_restores_last_saved_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(settings_path=Path(directory) / "settings.json")
            desktop = window._ensure_desktop_lyrics_window()
            popover = window._ensure_desktop_lyrics_settings_popover()
            original_save = window.settings_bridge.save_snapshot
            try:
                popover.set_values(window._settings_snapshot.to_dict())
                popover.font_size_slider.slider.setValue(72)
                QTest.qWait(60)
                self.app.processEvents()
                self.assertEqual(desktop._main_label.font().pixelSize(), 72)

                def fail_save(_snapshot):
                    raise SettingsBridgeError("无法保存桌面歌词设置")

                window.settings_bridge.save_snapshot = fail_save
                window._desktop_lyrics_settings_save_timer.stop()
                self.assertFalse(window._save_pending_desktop_lyrics_settings())
                self.assertEqual(desktop._main_label.font().pixelSize(), 42)
                self.assertEqual(popover.font_size_slider.value(), 42)
                self.assertFalse(popover.error_label.isHidden())
                self.assertIn("无法保存", popover.error_label.text())
            finally:
                window.settings_bridge.save_snapshot = original_save
                window.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
