from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.pages.lyrics_page import LyricsPage
from app.ui_v2.shell.main_window import MainWindow


class LyricsAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.track = next(track for track in create_mock_tracks(20) if not track.is_missing)
        self.adapter = LyricsAdapter()
        self.adapter.set_track(self.track)

    def test_chinese_and_english_active_line_and_segments(self) -> None:
        self.assertEqual(self.adapter.state.phase, "ready")
        self.assertEqual(len(self.adapter.document.lines), 100)
        self.adapter.set_position(3_000)
        self.assertEqual(self.adapter.active_line.language, "chinese")
        self.assertEqual(self.adapter.active_line.segments[0].segment_type, "character")
        self.adapter.load_mock_scenario("english_synced")
        self.adapter.set_position(3_000)
        self.assertEqual(self.adapter.active_line.language, "english")
        self.assertEqual(self.adapter.active_line.segments[0].segment_type, "word")

    def test_incremental_seek_offset_and_duplicate_timestamp_location(self) -> None:
        self.adapter.set_position(0)
        first = self.adapter.active_line.id
        self.adapter.set_position(2_500)
        self.assertNotEqual(self.adapter.active_line.id, first)
        target = self.adapter.document.lines[12]
        requested = []
        self.adapter.seek_requested.connect(requested.append)
        self.adapter.seek_to_line(target.id)
        self.assertEqual(self.adapter.active_line.id, target.id)
        self.assertEqual(requested[-1], target.start_ms)
        self.adapter.set_position(0)
        self.adapter.set_offset(3_000)
        self.assertGreaterEqual(self.adapter.active_line.start_ms, 2_400)
        self.adapter.set_offset(0)
        self.adapter.load_mock_scenario("duplicate_timestamps")
        self.adapter.set_position(0)
        self.assertEqual(self.adapter.active_line.id, self.adapter.document.lines[1].id)

    def test_document_states_and_display_options(self) -> None:
        self.adapter.load_mock_scenario("empty")
        self.assertEqual(self.adapter.state.phase, "empty")
        self.assertFalse(self.adapter.document.lines)
        self.adapter.load_mock_scenario("failed")
        self.assertEqual(self.adapter.state.phase, "failed")
        self.assertIsNone(self.adapter.document)
        self.adapter.load_mock_scenario("instrumental")
        self.assertEqual(self.adapter.state.phase, "instrumental")
        self.adapter.load_mock_scenario("loading")
        self.assertEqual(self.adapter.state.phase, "loading")
        self.adapter.complete_loading_for_test()
        self.assertEqual(self.adapter.state.phase, "ready")
        self.adapter.load_mock_scenario("translation")
        self.assertTrue(self.adapter.document.has_translation)
        before = self.adapter.display_options["translation"]
        self.adapter.toggle_translation()
        self.assertNotEqual(self.adapter.display_options["translation"], before)
        self.adapter.load_mock_scenario("romanization")
        self.assertTrue(self.adapter.document.has_romanization)
        self.adapter.toggle_romanization()
        self.assertTrue(self.adapter.display_options["romanization"])


class LyricsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.playback_adapter._timer_enabled = False
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _play_library_track(self) -> None:
        model = self.window.library_page.track_table.model
        index = next(
            model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if not track.is_missing and track.duration_ms is not None
        )
        self.window.library_page.track_table.doubleClicked.emit(index)
        self.app.processEvents()

    def _lyrics_page(self) -> LyricsPage:
        self.window.navigation_adapter.set_route("lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, LyricsPage)
        return page

    def test_route_reuse_playback_sync_and_line_seek(self) -> None:
        page = self._lyrics_page()
        self.assertEqual(page.adapter.state.phase, "idle")
        self._play_library_track()
        self.assertEqual(page.adapter.state.phase, "ready")
        self.window.playback_adapter.advance_for_test(3_000)
        self.assertEqual(page.adapter.active_line.start_ms, 2_400)
        self.assertEqual(page.timeline.slider.value(), 3_000)
        self.window.playback_adapter.seek(5_000)
        self.assertEqual(page.adapter.active_line.start_ms, 4_800)
        line = page.adapter.document.lines[8]
        page.lyrics_view.seek_requested.emit(line.id)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.position_ms, line.start_ms)
        self.assertEqual(page.adapter.active_line.id, line.id)
        self.window.navigation_adapter.set_route("library")
        self.assertIs(self._lyrics_page(), page)
        self.window.playback_adapter.play_next()
        self.assertEqual(page.adapter.document.track_id, self.window.playback_adapter.state.current_track.id)

    def test_browse_return_document_reuse_and_responsive_themes(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        document = page.adapter.document
        row_ids = tuple(page.lyrics_view._items)
        page.lyrics_view.eventFilter(page.lyrics_view.scroll_area.viewport(), QEvent(QEvent.Type.Wheel))
        self.assertTrue(page.lyrics_view.browsing)
        self.assertTrue(page.lyrics_view.return_button.isVisible())
        self.assertIs(page.lyrics_view.return_button.parent(), page.lyrics_view.scroll_area.viewport())
        page.lyrics_view.return_to_current()
        self.assertFalse(page.lyrics_view.browsing)
        self.assertFalse(page.lyrics_view.return_button.isVisible())
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.assertEqual(self.window.theme.mode, mode)
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(page.adapter.document, document)
            self.assertEqual(tuple(page.lyrics_view._items), row_ids)
            self.assertFalse(page.lyrics_view.scroll_area.horizontalScrollBar().isVisible())

    def test_lyrics_view_surface_backgrounds_and_segment_color_roles(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        self.window.playback_adapter.seek(3_000)
        active = page.lyrics_view._items[page.adapter.active_line.id]
        inactive = next(item for item_id, item in page.lyrics_view._items.items() if item_id != active.line.id)
        for mode in ("dark", "light"):
            self.window.set_theme(mode)
            expected = QColor(self.window.theme.colors.content_background).name().lower()
            for surface in (
                page.lyrics_view,
                page.lyrics_view.scroll_area,
                page.lyrics_view.scroll_area.viewport(),
                page.lyrics_view.content,
            ):
                self.assertEqual(surface.palette().color(QPalette.ColorRole.Window).name().lower(), expected)
                self.assertEqual(surface.palette().color(QPalette.ColorRole.Base).name().lower(), expected)
            active_roles = active.color_roles()
            inactive_roles = inactive.color_roles()
            self.assertEqual(active_roles["background"], self.window.theme.colors.content_background)
            self.assertEqual(active_roles["played_segment"], self.window.theme.colors.accent)
            self.assertEqual(active_roles["active_unplayed"], self.window.theme.colors.secondary_text)
            self.assertEqual(inactive_roles["inactive_line"], self.window.theme.colors.subtle_text)
            self.assertGreaterEqual(_contrast_ratio(inactive_roles["inactive_line"], active_roles["background"]), 3.0)
            self.assertGreaterEqual(_contrast_ratio(active_roles["active_unplayed"], active_roles["background"]), 3.0)

    def test_state_view_and_legacy_imports(self) -> None:
        page = self._lyrics_page()
        self._play_library_track()
        page.adapter.load_mock_scenario("failed")
        self.assertIs(page.content_stack.currentWidget(), page.state_view)
        self.assertTrue(page.state_view.retry_button.isVisible())
        page.adapter.load_mock_scenario("instrumental")
        self.assertIs(page.content_stack.currentWidget(), page.state_view)
        self.assertIn("纯音乐", page.state_view.title_label.text())
        legacy_main = importlib.import_module("main")
        legacy_window = importlib.import_module("app.ui.main_window")
        self.assertTrue(callable(legacy_main.main))
        self.assertTrue(hasattr(legacy_window, "MainWindow"))


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


if __name__ == "__main__":
    unittest.main()
