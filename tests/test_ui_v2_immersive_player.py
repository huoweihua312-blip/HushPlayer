from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.shell.immersive_player_shell import ImmersivePlayerShell
from app.ui_v2.shell.main_window import MainWindow, ShellPresentationMode
from app.ui_v2.theme.icons import FLUENT_IMMERSIVE_ASSETS


class UiV2ImmersivePlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _play_track(self) -> None:
        model = self.window.library_page.track_table.model
        index = next(
            model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if not track.is_missing and track.duration_ms is not None
        )
        self.window.library_page.track_table.doubleClicked.emit(index)
        self.app.processEvents()

    def _shell(self, route: str = "immersive_now_playing") -> ImmersivePlayerShell:
        self.window.navigation_adapter.set_route(route)
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersivePlayerShell)
        return page

    def test_shared_shell_has_two_modes_and_one_playback_source(self) -> None:
        self._play_track()
        shell = self._shell()
        self.assertIsInstance(shell, ImmersiveLyricsPage)
        self.assertIs(shell.playback_adapter, self.window.playback_adapter)
        self.assertIs(shell.now_playing_page.playback, self.window.playback_adapter)
        self.assertEqual(shell.mode, "now_playing")
        shell.header_lyrics.click()
        self.app.processEvents()
        self.assertEqual(shell.mode, "lyrics")
        self.assertIs(shell.content_stack.currentWidget(), shell.content)
        shell.header_now_playing.click()
        self.app.processEvents()
        self.assertEqual(shell.mode, "now_playing")
        self.assertIs(shell.playback_adapter, self.window.playback_adapter)
        self.assertIs(shell.lyrics_adapter, self.window.lyrics_adapter)
        self.assertIs(shell.queue_model, self.window.playback_adapter)

    def test_playerbar_track_entry_hides_normal_chrome(self) -> None:
        self._play_track()
        self.window.player_bar.track_open_requested.emit()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_now_playing")
        self.assertEqual(self.window.presentation_mode, ShellPresentationMode.IMMERSIVE)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertFalse(self.window.title_bar.isVisible())
        self.assertFalse(self.window.player_bar.isVisible())

    def test_exit_restores_the_previous_route_and_cached_page(self) -> None:
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        ordinary = self.window.router.currentWidget()
        self._play_track()
        shell = self._shell("immersive_lyrics")
        shell.header_back_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "library")
        self.assertIs(self.window.router.currentWidget(), ordinary)
        self.assertTrue(self.window.sidebar.isVisible())
        self.assertTrue(self.window.title_bar.isVisible())
        self.assertTrue(self.window.player_bar.isVisible())

    def test_queue_panel_projects_existing_queue_and_esc_closes_first(self) -> None:
        self._play_track()
        shell = self._shell()
        self.assertIs(shell.queue_panel.playback, self.window.playback_adapter)
        self.assertEqual(shell.queue_panel.list_widget.count(), len(self.window.playback_adapter.queue_tracks))
        shell.show_queue_panel()
        self.app.processEvents()
        self.assertTrue(shell.queue_panel_visible)
        QTest.keyClick(shell, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(shell.queue_panel_visible)
        self.assertEqual(self.window.navigation_adapter.route, "immersive_now_playing")

    def test_immersive_space_and_seek_keys_use_existing_adapter(self) -> None:
        self._play_track()
        shell = self._shell()
        self.window.playback_adapter.pause()
        QTest.keyClick(shell, Qt.Key.Key_Space)
        self.assertTrue(self.window.playback_adapter.state.is_playing)
        self.window.playback_adapter.seek(10_000)
        QTest.keyClick(shell, Qt.Key.Key_Left)
        self.assertEqual(self.window.playback_adapter.state.position_ms, 5_000)

    def test_empty_now_playing_is_formal_and_does_not_expose_internal_names(self) -> None:
        shell = self._shell()
        labels = " ".join(
            getattr(label, "_full_text", "")
            for label in shell.now_playing_page.findChildren(type(shell.now_playing_page.title_label))
        )
        self.assertIn("未选择歌曲", labels)
        self.assertNotIn("mock", labels.lower())
        self.assertNotIn("demo", labels.lower())

    def test_now_playing_artwork_uses_real_responsive_rounded_clip(self) -> None:
        shell = self._shell()
        artwork = shell.now_playing_page.artwork
        self.assertTrue(artwork._clip_artwork)
        self.assertIn("background: transparent", artwork.styleSheet())
        artwork.set_display_size(230)
        self.assertEqual(artwork._corner_radius(), 15.0)
        artwork.set_display_size(340)
        self.assertEqual(artwork._corner_radius(), 19.0)
        artwork.set_display_size(390)
        self.assertEqual(artwork._corner_radius(), 21.0)

    def test_header_now_playing_is_a_semantic_mode_switch_not_play_icon(self) -> None:
        shell = self._shell()
        self.assertEqual(shell.header_now_playing.text(), "正在播放")
        self.assertFalse(shell.header_now_playing.icon().isNull())
        self.assertEqual(shell.header_now_playing.property("fluentIconFile"), "music_note_2_play_20_regular.svg")
        self.assertTrue(shell.header_now_playing.isCheckable())
        self.assertEqual(shell.header_lyrics.text(), "歌词")
        self.assertFalse(shell.header_lyrics.icon().isNull())
        self.assertEqual(shell.header_lyrics.property("fluentIconFile"), "subtitles_20_regular.svg")
        header_mode_texts = [
            button.text()
            for button in shell.header.findChildren(type(shell.header_now_playing))
            if button.isVisible()
        ]
        self.assertEqual(header_mode_texts.count("正在播放"), 1)
        self.assertFalse(hasattr(shell.controls, "now_playing_button"))
        self.assertFalse(hasattr(shell.controls, "lyrics_button"))
        self.assertFalse(hasattr(shell.controls, "mode_requested"))

    def test_immersive_mode_and_return_controls_use_fluent_text_tabs(self) -> None:
        shell = self._shell("immersive_lyrics")
        mode_qss = shell.header.styleSheet()
        return_qss = shell.canvas.return_button.styleSheet()
        self.assertEqual(
            FLUENT_IMMERSIVE_ASSETS,
            {
                "now_playing": "music_note_2_play_20_regular.svg",
                "lyrics": "subtitles_20_regular.svg",
                "return_current": "target_arrow_20_regular.svg",
            },
        )
        self.assertEqual(shell.header_now_playing.property("fluentIconFamily"), "fluent_immersive")
        self.assertEqual(shell.header_now_playing.property("fluentIconFile"), "music_note_2_play_20_regular.svg")
        self.assertEqual(shell.header_lyrics.property("fluentIconFile"), "subtitles_20_regular.svg")
        self.assertFalse(shell.header_now_playing.icon().isNull())
        self.assertFalse(shell.header_lyrics.icon().isNull())
        self.assertEqual(shell.header_now_playing.iconSize().width(), 18)
        self.assertEqual(shell.header_lyrics.iconSize().width(), 18)
        self.assertIn("QToolButton#immersiveModeButton:hover { background: transparent", mode_qss)
        self.assertIn("QToolButton#immersiveModeButton:checked { background: transparent", mode_qss)
        self.assertIn("border-bottom: 2px solid", mode_qss)
        self.assertNotIn(shell._theme.colors.surface_selected, mode_qss)
        self.assertNotIn("border-radius: 19px", mode_qss)
        self.assertEqual(shell.canvas.return_button.property("fluentIconFamily"), "fluent_immersive")
        self.assertEqual(shell.canvas.return_button.property("fluentIconFile"), "target_arrow_20_regular.svg")
        self.assertFalse(shell.canvas.return_button.icon().isNull())
        self.assertEqual(shell.canvas.return_button.iconSize().width(), 18)
        self.assertIn("QToolButton#returnToCurrentLyrics {border: 1px solid transparent", return_qss)
        self.assertIn("background: transparent", return_qss)
        self.assertIn("QToolButton#returnToCurrentLyrics:hover", return_qss)
        self.assertNotIn(shell._theme.colors.elevated_background, return_qss)
        self.assertNotIn("border-radius: 19px", return_qss)
        self.assertIn("border-radius: 11px", return_qss)
        self.assertIn("min-height: 36px", return_qss)
        self.assertIn("rgba(", return_qss)
        self.assertNotIn("background: " + shell._theme.colors.accent, mode_qss)
        self.assertNotIn("background: " + shell._theme.colors.accent, return_qss)
        mode_size = (shell.header_now_playing.size(), shell.header_lyrics.size())
        shell.header_now_playing.click()
        self.app.processEvents()
        self.assertEqual(mode_size, (shell.header_now_playing.size(), shell.header_lyrics.size()))

    def test_immersive_icon_manifest_is_vendored_regular_only(self) -> None:
        manifest_path = PROJECT_ROOT / "app" / "ui_v2" / "assets" / "icons" / "fluent_immersive" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.1.334")
        self.assertEqual(manifest["style"], "Regular")
        records = {entry["feature"]: entry for entry in manifest["icons"]}
        self.assertEqual(records["immersive_header_now_playing"]["filename"], "music_note_2_play_20_regular.svg")
        self.assertEqual(records["immersive_header_lyrics"]["filename"], "subtitles_20_regular.svg")
        self.assertEqual(records["immersive_return_to_current_lyrics"]["filename"], "target_arrow_20_regular.svg")
        for record in records.values():
            self.assertEqual(record["render_size_px"], 18)
            self.assertTrue((manifest_path.parent / record["filename"]).exists())
            self.assertNotIn("filled", record["filename"])

    def test_utility_row_centers_remaining_tools_without_mode_gap(self) -> None:
        shell = self._shell()
        for width in (900, 1200, 1600):
            self.window.resize(width, 800 if width != 900 else 600)
            self.app.processEvents()
            row_center = shell.controls.secondary_row.rect().center().x()
            group_center = shell.controls.utility_group.geometry().center().x()
            self.assertLessEqual(abs(row_center - group_center), 2)
            self.assertGreater(shell.controls.utility_group.width(), 0)
            self.assertLess(shell.controls.utility_group.width(), shell.controls.secondary_row.width())

    def test_header_and_utility_have_one_entry_per_utility(self) -> None:
        shell = self._shell()
        self.assertFalse(hasattr(shell, "header_queue"))
        self.assertFalse(hasattr(shell, "header_more"))
        self.assertFalse(hasattr(shell.controls, "back_button"))
        buttons = shell.controls.findChildren(type(shell.controls.queue_button))
        self.assertEqual(sum(button is shell.controls.queue_button for button in buttons), 1)
        self.assertEqual(sum(button is shell.controls.more_button for button in buttons), 1)
        self.assertNotIn("返回普通页面", [button.toolTip() for button in buttons])

    def test_return_to_current_lyrics_is_only_a_temporary_lyrics_button(self) -> None:
        self._play_track()
        shell = self._shell("immersive_lyrics")
        canvas = shell.canvas
        self.assertFalse(canvas.return_button.isVisible())
        event = QWheelEvent(
            QPointF(120, 120),
            QPointF(120, 120),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(canvas, event)
        self.app.processEvents()
        self.assertTrue(canvas.return_button.isVisible())
        canvas.return_button.click()
        self.app.processEvents()
        self.assertFalse(canvas.return_button.isVisible())
        self.assertFalse(any(button.text() == "回到当前歌词" for button in shell.now_playing_page.findChildren(type(shell.controls.queue_button))))

    def test_now_playing_title_uses_responsive_width_and_two_line_elision(self) -> None:
        self._play_track()
        shell = self._shell()
        page = shell.now_playing_page
        page.title_label.set_full_text("Signal From Home")
        self.window.resize(1200, 800)
        self.app.processEvents()
        self.assertGreaterEqual(page._meta_group.width(), 300)
        self.assertNotIn("…", page.title_label.text())
        self.assertEqual(page.title_label.toolTip(), "Signal From Home")
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertGreaterEqual(page._meta_group.width(), 230)
        self.assertNotIn("…", page.title_label.text())
        page.title_label.set_full_text("A Very Long Signal From Home Title That Needs More Than Two Lines")
        self.app.processEvents()
        self.assertLessEqual(page.title_label.text().count("\n"), 1)
        self.assertIn("…", page.title_label.text())

    def test_immersive_primary_play_control_is_high_contrast_and_disabled_visible(self) -> None:
        shell = self._shell()
        button = shell.controls.play_button
        self.assertEqual(button.width(), 58)
        self.assertEqual(button.height(), 58)
        self.assertEqual(button.iconSize().width(), 24)
        self.assertIn("#F4F4F6", button.styleSheet())
        self.assertIn("background", button.styleSheet())
        self.assertFalse(button.isEnabled())
        self.assertFalse(button.icon().isNull())
        self._play_track()
        self.assertTrue(button.isEnabled())
        self.assertFalse(button.icon().isNull())

    def test_global_playerbar_remains_separate_from_immersive_primary_control(self) -> None:
        self._play_track()
        shell = self._shell()
        self.assertIsNot(shell.controls.play_button, self.window.player_bar.play_button)
        self.assertFalse(self.window.player_bar.isVisible())


if __name__ == "__main__":
    unittest.main()
