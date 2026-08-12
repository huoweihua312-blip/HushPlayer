from __future__ import annotations

import json
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

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

    @staticmethod
    def _pixels(widget) -> bytes:
        image = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        return memoryview(image.bits())[: image.sizeInBytes()].tobytes()

    def _queue_transition_tracks(self):
        tracks = [
            track
            for track in self.window.library_page.track_table.model.tracks()
            if not track.is_missing and track.duration_ms is not None
        ]
        self.assertGreaterEqual(len(tracks), 2)
        short = replace(
            tracks[0],
            id="queue-short-title",
            title="短标题 A",
            artist="中文艺术家",
        )
        long = replace(
            tracks[1],
            id="queue-long-title",
            title="A deliberately long English title that must elide cleanly in the current queue row",
            artist="English Artist",
        )
        return short, long

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
        self.assertEqual(shell.queue_panel.list_widget.count(), len(self.window.playback_adapter.queue_tracks) - 1)
        self.assertIsNotNone(shell.queue_panel.current_track)
        self.assertEqual(shell.queue_panel.current_track.id, self.window.playback_adapter.state.current_track.id)
        self.assertEqual(len(shell.queue_panel.track_rows), len(self.window.playback_adapter.queue_tracks))
        self.assertEqual(
            shell.queue_panel.list_widget.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        shell.show_queue_panel()
        self.app.processEvents()
        self.assertTrue(shell.queue_panel_visible)
        self.assertTrue(shell.queue_panel.current_section.isVisible())
        self.assertTrue(shell.queue_panel.next_section.isVisible())
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

    def test_global_queue_and_lyrics_buttons_use_independent_signals_and_routes(self) -> None:
        self._play_track()
        queue_events: list[bool] = []
        lyrics_events: list[bool] = []
        self.window.player_bar.queue_requested.connect(lambda: queue_events.append(True))
        self.window.player_bar.lyrics_requested.connect(lambda: lyrics_events.append(True))

        self.window.navigation_adapter.set_route("library")
        self.window.player_bar.queue_button.click()
        self.app.processEvents()
        shell = self._shell()
        self.assertEqual(queue_events, [True])
        self.assertEqual(lyrics_events, [])
        self.assertEqual(shell.mode, "now_playing")
        self.assertTrue(shell.queue_panel_visible)

        shell.hide_queue_panel()
        self.window.navigation_adapter.set_route("library")
        self.window.player_bar.lyrics_button.click()
        self.app.processEvents()
        shell = self._shell("immersive_lyrics")
        self.assertEqual(queue_events, [True])
        self.assertEqual(lyrics_events, [True])
        self.assertEqual(shell.mode, "lyrics")
        self.assertFalse(shell.queue_panel_visible)

    def test_immersive_queue_only_toggles_panel_and_lyrics_mode_closes_it(self) -> None:
        shell = self._shell("immersive_now_playing")
        route = self.window.navigation_adapter.route
        shell.controls.queue_button.click()
        self.app.processEvents()
        self.assertTrue(shell.queue_panel_visible)
        self.assertEqual(self.window.navigation_adapter.route, route)
        shell.controls.queue_button.click()
        self.app.processEvents()
        self.assertFalse(shell.queue_panel_visible)
        shell.show_queue_panel()
        shell.header_lyrics.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_lyrics")
        self.assertEqual(shell.mode, "lyrics")
        self.assertFalse(shell.queue_panel_visible)

    def test_queue_panel_uses_immersive_glass_tokens_and_fluent_dismiss_icon(self) -> None:
        shell = self._shell()
        panel = shell.queue_panel
        qss = panel.styleSheet()
        self.assertIn("rgba(14, 18, 24, 0.88)", qss)
        self.assertIn("rgba(255, 255, 255, 0.10)", qss)
        self.assertIn("border-radius: 10px", qss)
        self.assertNotIn(self.window._theme.colors.surface_elevated, qss)
        self.assertEqual(panel.close_button.property("fluentIconFile"), "dismiss_20_regular.svg")
        self.assertEqual(panel.close_button.iconSize().width(), 18)

    def test_queue_rows_show_artwork_metadata_duration_and_elide_without_horizontal_scroll(self) -> None:
        short, long = self._queue_transition_tracks()
        adapter = self.window.playback_adapter
        adapter.set_queue((long, short))
        adapter.play_track(long.id)
        shell = self._shell("immersive_now_playing")
        shell.show_queue_panel()
        self.app.processEvents()
        panel = shell.queue_panel
        current_view = panel.content.current_list
        current_index = current_view.model().index(0, 0)
        self.assertEqual(current_view.model().rowCount(), 1)
        self.assertEqual(current_view.model().data(current_index, Qt.ItemDataRole.DisplayRole), long.title)
        self.assertEqual(current_view.model().data(current_index, Qt.ItemDataRole.ToolTipRole), f"{long.title}\n{long.artist}")
        self.assertEqual(current_view.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(panel.list_widget.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(current_view.findChildren(type(panel.content.current_title)), [])
        self.assertLessEqual(current_view.width(), panel.width())

    def test_queue_updates_current_and_next_in_place_without_replacing_playback_sources(self) -> None:
        self._play_track()
        shell = self._shell("immersive_now_playing")
        shell.show_queue_panel()
        self.app.processEvents()
        panel = shell.queue_panel
        model = panel.list_widget.model()
        adapter = self.window.playback_adapter
        controller = adapter.controller
        queue_source = shell.queue_model
        first_id = adapter.state.current_track.id
        adapter.play_next()
        self.app.processEvents()
        second_id = adapter.state.current_track.id
        self.assertNotEqual(first_id, second_id)
        self.assertIs(panel.list_widget.model(), model)
        self.assertIs(shell.queue_model, queue_source)
        self.assertIs(adapter.controller, controller)
        self.assertEqual(panel.current_track.id, second_id)
        self.assertNotIn(second_id, [track.id for track in panel.next_rows])

    def test_queue_current_row_repaints_without_title_residue_across_title_scripts(self) -> None:
        short, long = self._queue_transition_tracks()
        adapter = self.window.playback_adapter
        adapter.set_queue((short, long))
        adapter.play_track(short.id)
        shell = self._shell("immersive_now_playing")
        shell.show_queue_panel()
        self.app.processEvents()
        panel = shell.queue_panel
        current_view = panel.content.current_list
        current_model = current_view.model()
        self.assertIs(current_view.parentWidget(), panel.current_section)
        self.assertEqual(current_view.findChildren(type(panel.content.current_title)), [])
        model = panel.list_widget.model()
        adapter.play_next()
        self.app.processEvents()
        self.assertIs(panel.list_widget.model(), model)
        self.assertIs(current_view.model(), current_model)
        self.assertEqual(panel.current_track.id, long.id)
        self.assertEqual(
            current_model.data(current_model.index(0, 0), Qt.ItemDataRole.DisplayRole),
            long.title,
        )
        self.assertNotEqual(self._pixels(current_view.viewport()), b"")

        adapter.pause()
        self.app.processEvents()
        self.assertEqual(panel.current_track.id, long.id)
        adapter.play_track(short.id)
        self.app.processEvents()
        self.assertEqual(panel.current_track.id, short.id)
        self.assertEqual(
            current_model.data(current_model.index(0, 0), Qt.ItemDataRole.DisplayRole),
            short.title,
        )

    def test_queue_panel_floats_without_reflowing_content_at_reference_sizes(self) -> None:
        self._play_track()
        shell = self._shell("immersive_now_playing")
        panel = shell.queue_panel
        model = panel.list_widget.model()
        for width, height, min_width, max_width, min_height, max_height in (
            (1600, 900, 380, 410, 610, 700),
            (1200, 800, 350, 380, 520, 610),
            (900, 600, 310, 340, 400, 470),
        ):
            self.window.resize(width, height)
            self.app.processEvents()
            before = (
                shell.content_stack.geometry(),
                shell.canvas.geometry(),
                shell.controls.geometry(),
                QRect(shell.now_playing_page.artwork.mapTo(shell, QPoint(0, 0)), shell.now_playing_page.artwork.size()),
            )
            shell.show_queue_panel()
            self.app.processEvents()
            after = (
                shell.content_stack.geometry(),
                shell.canvas.geometry(),
                shell.controls.geometry(),
                QRect(shell.now_playing_page.artwork.mapTo(shell, QPoint(0, 0)), shell.now_playing_page.artwork.size()),
            )
            self.assertEqual(before, after)
            self.assertIs(panel.parentWidget(), shell.overlay_layer)
            self.assertFalse(hasattr(panel, "presentation_mode"))
            self.assertGreaterEqual(panel.width(), min_width)
            self.assertLessEqual(panel.width(), max_width)
            self.assertGreaterEqual(panel.height(), min_height)
            self.assertLessEqual(panel.height(), max_height)
            self.assertEqual(shell.width() - panel.geometry().right() - 1, 16 if width == 900 else 18 if width == 1200 else 20)
            self.assertGreaterEqual(panel.geometry().top(), shell.header.height() + 12)
            self.assertFalse(panel.geometry().intersects(shell.header.geometry()))
            self.assertIs(panel.list_widget.model(), model)
            self.assertEqual(panel.list_widget.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            shell.hide_queue_panel()
            self.app.processEvents()

    def test_queue_rows_select_then_play_existing_queue_item_from_double_click_or_enter(self) -> None:
        short, long = self._queue_transition_tracks()
        adapter = self.window.playback_adapter
        adapter.set_queue((short, long))
        adapter.play_track(short.id)
        shell = self._shell("immersive_now_playing")
        shell.show_queue_panel()
        self.app.processEvents()
        view = shell.queue_panel.list_widget
        target = view.model().index(0, 0)
        target_rect = view.visualRect(target)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target_rect.center())
        self.app.processEvents()
        self.assertEqual(adapter.state.current_track.id, short.id)
        self.assertEqual(view.currentIndex(), target)
        self.assertEqual(shell.queue_panel.content.selected_track.id, long.id)

        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target_rect.center())
        self.app.processEvents()
        self.assertEqual(adapter.state.current_track.id, long.id)

        adapter.play_track(short.id)
        self.app.processEvents()
        target = view.model().index(0, 0)
        view.setCurrentIndex(target)
        view.setFocus()
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(adapter.state.current_track.id, long.id)

    def test_quick_settings_floats_without_reflowing_lyrics_at_reference_sizes(self) -> None:
        self._play_track()
        shell = self._shell("immersive_lyrics")
        drawer = shell.lyrics_quick_settings
        self.assertIsNotNone(drawer)
        for width, height, min_width, max_width, min_height, max_height in (
            (1600, 900, 360, 390, 590, 680),
            (1200, 800, 340, 370, 500, 590),
            (900, 600, 310, 340, 410, 480),
        ):
            self.window.resize(width, height)
            self.app.processEvents()
            before = (shell.content.geometry(), shell.canvas.geometry(), shell.controls.geometry())
            shell.show_lyrics_quick_settings()
            self.app.processEvents()
            after = (shell.content.geometry(), shell.canvas.geometry(), shell.controls.geometry())
            self.assertEqual(before, after)
            self.assertIs(drawer.parentWidget(), shell.overlay_layer)
            self.assertFalse(hasattr(drawer, "presentation_mode"))
            self.assertGreaterEqual(drawer.width(), min_width)
            self.assertLessEqual(drawer.width(), max_width)
            self.assertGreaterEqual(drawer.height(), min_height)
            self.assertLessEqual(drawer.height(), max_height)
            self.assertEqual(shell.width() - drawer.geometry().right() - 1, 16 if width == 900 else 18 if width == 1200 else 20)
            self.assertGreaterEqual(drawer.geometry().top(), shell.header.height() + 12)
            self.assertFalse(drawer.geometry().intersects(shell.header.geometry()))
            self.assertTrue(drawer.footer.isVisible())
            self.assertEqual(drawer.content.scroll.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            shell.hide_lyrics_quick_settings(cancel=True)
            self.app.processEvents()

    def test_immersive_focus_tokens_and_entry_labels_are_consistent(self) -> None:
        self._play_track()
        shell = self._shell("immersive_lyrics")
        focus = self.window._theme.colors.focus_ring
        for button in (
            shell.controls.shuffle_button,
            shell.controls.previous_button,
            shell.controls.play_button,
            shell.controls.next_button,
            shell.controls.repeat_button,
            shell.controls.queue_button,
            shell.controls.volume_button,
            shell.controls.more_button,
        ):
            self.assertIn(focus, button.styleSheet())
        self.assertEqual(shell.controls.more_button.toolTip(), "更多操作")
        self.assertEqual(shell.controls.more_button.accessibleName(), "更多操作")
        self.assertEqual(shell.lyrics_settings_button.toolTip(), "歌词快捷设置")
        self.assertEqual(shell.lyrics_settings_button.accessibleName(), "歌词快捷设置")
        self.assertEqual(shell.header_lyrics.accessibleName(), "歌词")

        shell.show_queue_panel()
        self.app.processEvents()
        self.assertEqual(shell.queue_panel.list_widget.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertIn(focus, shell.queue_panel.close_button.parentWidget().styleSheet())
        shell.show_lyrics_quick_settings()
        self.app.processEvents()
        drawer = shell.lyrics_quick_settings
        self.assertIn(focus, drawer.save_button.styleSheet())
        scale = drawer.content.controls["immersive_lyrics_font_scale"]
        self.assertIn(focus, scale.slider.styleSheet())
        self.assertIn(focus, scale.spin.styleSheet())

    def test_lyrics_mode_exposes_one_settings_entry_and_uses_quick_drawer(self) -> None:
        self._play_track()
        shell = self._shell("immersive_lyrics")
        queue_model = shell.queue_model
        current_track = self.window.playback_adapter.state.current_track
        self.assertTrue(shell.lyrics_settings_button.isVisible())
        self.assertEqual(shell.lyrics_settings_button.toolTip(), "歌词快捷设置")
        self.assertEqual(shell.lyrics_settings_button.size().toTuple(), (32, 32))
        self.assertEqual(shell.lyrics_settings_button.iconSize().width(), 18)
        self.assertEqual(
            shell.lyrics_settings_button.property("fluentIconFile"),
            "settings_20_regular.svg",
        )
        shell.header_now_playing.click()
        self.app.processEvents()
        self.assertFalse(shell.lyrics_settings_button.isVisible())
        shell.header_lyrics.click()
        self.app.processEvents()
        self.assertTrue(shell.lyrics_settings_button.isVisible())

        shell.lyrics_settings_button.click()
        self.app.processEvents()
        drawer = shell.lyrics_quick_settings
        self.assertIsNotNone(drawer)
        self.assertTrue(drawer.isVisible())
        self.assertIsNone(self.window.settings_overlay)
        self.assertEqual(drawer.title_label.text(), "歌词设置")
        session = drawer.session
        self.assertIsNotNone(session)
        original_scale = shell.options.global_font_scale
        drawer.content.controls["immersive_lyrics_font_scale"].slider.setValue(125)
        self.app.processEvents()
        self.assertEqual(shell.options.global_font_scale, 125)
        self.assertTrue(drawer.is_dirty)
        drawer.cancel_button.click()
        self.app.processEvents()
        self.assertFalse(drawer.isVisible())
        self.assertEqual(shell.options.global_font_scale, original_scale)
        shell.lyrics_settings_button.click()
        self.app.processEvents()
        drawer = shell.lyrics_quick_settings
        drawer.content.controls["immersive_lyrics_font_scale"].slider.setValue(125)
        self.app.processEvents()
        drawer.restore_button.click()
        self.app.processEvents()
        self.assertEqual(shell.options.global_font_scale, original_scale)
        self.assertFalse(drawer.is_dirty)
        drawer.cancel_and_close()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_lyrics")
        self.assertEqual(shell.mode, "lyrics")
        self.assertIs(shell.queue_model, queue_model)
        self.assertIs(self.window.playback_adapter.state.current_track, current_track)

    def test_quick_drawer_save_uses_existing_settings_bridge(self) -> None:
        shell = self._shell("immersive_lyrics")
        shell.show_lyrics_quick_settings()
        drawer = shell.lyrics_quick_settings
        drawer.content.controls["immersive_lyrics_font_scale"].slider.setValue(125)
        self.app.processEvents()
        drawer.save_button.click()
        self.app.processEvents()
        self.assertFalse(drawer.isVisible())
        snapshot = self.window.settings_bridge.read_snapshot()
        self.assertEqual(self.window.settings_bridge.value(snapshot, "immersive_lyrics_font_scale"), 125)
        self.assertEqual(shell.options.global_font_scale, 125)

    def test_queue_and_quick_drawers_are_mutually_exclusive(self) -> None:
        shell = self._shell("immersive_lyrics")
        shell.show_queue_panel()
        self.assertTrue(shell.queue_panel_visible)
        shell.show_lyrics_quick_settings()
        self.app.processEvents()
        self.assertFalse(shell.queue_panel_visible)
        self.assertTrue(shell.lyrics_quick_settings_visible)
        shell.show_queue_panel()
        self.app.processEvents()
        self.assertTrue(shell.queue_panel_visible)
        self.assertFalse(shell.lyrics_quick_settings_visible)

    def test_same_session_current_track_is_shared_by_playerbar_nowplaying_queue_and_lyrics(self) -> None:
        self._play_track()
        first = self.window.playback_adapter.state.current_track
        shell = self._shell("immersive_now_playing")
        self.assertIsNotNone(first)
        self.assertEqual(self.window.player_bar.title_label.full_text, shell.now_playing_page.title_label.full_text)
        self.assertEqual(shell.queue_panel.playback.state.current_track.id, first.id)
        shell.header_lyrics.click()
        self.app.processEvents()
        self.assertEqual(shell.lyrics_adapter.track.id, first.id)
        self.window.lyrics_adapter.load_mock_scenario("empty")
        self.app.processEvents()
        self.assertEqual(shell.lyrics_adapter.track.id, first.id)
        self.assertEqual(shell.lyrics_state_view.title_label.text(), f"{first.title} 暂无歌词")
        self.assertNotIn("未选择歌曲", shell.lyrics_state_view.title_label.text())
        self.window.playback_adapter.play_next()
        self.app.processEvents()
        second = self.window.playback_adapter.state.current_track
        self.assertIsNotNone(second)
        self.assertEqual(shell.lyrics_adapter.track.id, second.id)
        shell.show_queue_panel()
        self.app.processEvents()
        self.assertEqual(shell.queue_panel.current_track.id, second.id)
        self.assertEqual(self.window.playback_adapter.state.current_track.id, second.id)
        self.assertEqual(self.window.player_bar.title_label.full_text, shell.now_playing_page.title_label.full_text)

    def test_drawer_lifecycle_survives_twenty_resize_close_and_destroy_cycles(self) -> None:
        window = MainWindow()
        window.playback_adapter._timer_enabled = False
        window.resize(1200, 800)
        window.show()
        self.app.processEvents()
        try:
            model = window.library_page.track_table.model
            index = next(
                model.index(row, int(TrackColumn.TITLE))
                for row, track in enumerate(model.tracks())
                if not track.is_missing and track.duration_ms is not None
            )
            window.library_page.track_table.doubleClicked.emit(index)
            self.app.processEvents()

            for _cycle in range(20):
                window.navigation_adapter.set_route("immersive_now_playing")
                self.app.processEvents()
                shell = window.router.currentWidget()
                self.assertIsInstance(shell, ImmersivePlayerShell)
                queue_model = shell.queue_panel.list_widget.model()
                queue_content = shell.queue_panel.content

                shell.show_queue_panel()
                for width in (1200, 900, 1200):
                    window.resize(width, 600 if width == 900 else 800)
                    self.app.processEvents()
                self.assertFalse(hasattr(shell.queue_panel, "presentation_mode"))
                self.assertIs(shell.queue_panel.parentWidget(), shell.overlay_layer)
                self.assertIs(shell.queue_panel.list_widget.model(), queue_model)
                self.assertIs(queue_content.parentWidget(), shell.queue_panel.content_host)
                self.assertIs(shell.controls.parentWidget(), shell)
                shell.hide_queue_panel()

                shell.header_lyrics.click()
                self.app.processEvents()
                shell.show_lyrics_quick_settings()
                drawer = shell.lyrics_quick_settings
                self.assertIsNotNone(drawer)
                session = drawer.session
                for width in (1200, 900, 1200):
                    window.resize(width, 600 if width == 900 else 800)
                    self.app.processEvents()
                self.assertFalse(hasattr(drawer, "presentation_mode"))
                self.assertIs(drawer.parentWidget(), shell.overlay_layer)
                self.assertIs(drawer.session, session)
                self.assertIs(drawer.content.parentWidget(), drawer.content_host)
                self.assertIs(drawer.footer.parentWidget(), drawer)
                shell.hide_lyrics_quick_settings(cancel=True)

                window.playback_adapter.play_next()
                self.app.processEvents()
                current = window.playback_adapter.state.current_track
                self.assertIsNotNone(current)
                self.assertEqual(shell.queue_panel.current_track.id, current.id)
                self.assertEqual(shell.now_playing_page.title_label.full_text, current.title)
                self.assertEqual(window.player_bar.title_label.full_text, current.title)
                self.assertEqual(shell.lyrics_adapter.track.id, current.id)
                self.assertTrue(all(
                    isValid(item)
                    for item in (
                        window,
                        shell,
                        shell.controls,
                        shell.queue_panel,
                        queue_content,
                        queue_model,
                        drawer,
                        drawer.content,
                        drawer.footer,
                    )
                ))
                window.navigation_adapter.set_route("library")
                self.app.processEvents()
        finally:
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.assertFalse(isValid(window))


if __name__ == "__main__":
    unittest.main()
