from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QPointF, QObject, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QSlider

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.pages.lyrics_page import LyricsPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2, ResponsiveLyricsMetrics


class FakeLyricsService(QObject):
    statusChanged = Signal(int, str, str)
    lyricsReady = Signal(int, str, dict)

    def __init__(self) -> None:
        super().__init__()
        self.generation = 0
        self.requests = []
        self.cancel_count = 0

    def request_lyrics(self, item) -> int:
        self.generation += 1
        self.requests.append(item)
        return self.generation

    def cancel(self) -> None:
        self.cancel_count += 1


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

    def test_formal_adapter_loads_actual_local_lrc_instead_of_mock_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-v2-lyrics-") as root:
            song_path = Path(root) / "actual-song.mp3"
            lyric_path = song_path.with_suffix(".lrc")
            song_path.write_bytes(b"fixture")
            lyric_path.write_text(
                "[00:00.00]真实第一行\n[00:02.00]真实第二行\n",
                encoding="utf-8",
            )
            service = FakeLyricsService()
            adapter = LyricsAdapter(lyrics_service=service)
            track = replace(
                self.track,
                source_id="local",
                source_name="本地音乐",
                source_type="local",
                local_path=str(song_path),
                duration_ms=5_000,
            )

            adapter.set_track(track)

            self.assertEqual(service.requests, [])
            self.assertEqual(adapter.state.phase, "ready")
            self.assertEqual(
                [line.text for line in adapter.document.lines],
                ["真实第一行", "真实第二行"],
            )
            self.assertNotIn("雾落在清晨的海岸", adapter.document.lines[0].text)
            self.assertEqual(adapter.document.lines[0].segments[0].text, "真")

    def test_formal_adapter_rejects_stale_online_lyrics_by_identity_and_generation(self) -> None:
        service = FakeLyricsService()
        adapter = LyricsAdapter(lyrics_service=service)
        first = replace(
            self.track,
            source_type="online",
            source_id="fixture",
            source_name="Fixture",
            stable_identity="remote:fixture:first",
            remote_identity="first",
            remote_track_id="first",
            remote_payload={"id": "first"},
        )
        second = replace(
            first,
            id="second",
            stable_identity="remote:fixture:second",
            remote_identity="second",
            remote_track_id="second",
            remote_payload={"id": "second"},
        )

        adapter.set_track(first)
        first_generation = service.generation
        adapter.set_track(second)
        second_generation = service.generation
        service.lyricsReady.emit(
            first_generation,
            first.stable_identity,
            {"text": "过期歌词", "source": "stale"},
        )
        self.assertIsNone(adapter.document)
        service.lyricsReady.emit(
            second_generation,
            second.stable_identity,
            {
                "text": "[00:00.00]真实在线歌词",
                "source": "Fixture",
            },
        )

        self.assertEqual(adapter.state.phase, "ready")
        self.assertEqual(adapter.document.lines[0].text, "真实在线歌词")
        self.assertNotIn("雾落在清晨的海岸", adapter.document.lines[0].text)


class LyricsPageTests(unittest.TestCase):
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

    def test_v4_ordinary_structure_is_one_column_without_duplicate_player(self) -> None:
        page = self._lyrics_page()
        self.assertEqual(page.lyric_column_count, 1)
        self.assertIsInstance(page.lyrics_view, LyricsCanvasV2)
        self.assertIs(page.toolbar.parentWidget(), page._content_container)
        self.assertIs(page.content.parentWidget(), page._content_container)
        self.assertFalse(page.has_in_page_playback_controls)
        self.assertFalse(hasattr(page, "timeline"))
        self.assertFalse(hasattr(page, "side"))
        self.assertEqual(len(page.findChildren(QSlider)), 0)
        self.assertTrue(self.window.player_bar.isVisible())
        self.assertEqual(
            [button.text() for button in (page.toolbar.translation_button, page.toolbar.romanization_button, page.toolbar.more_button, page.toolbar.immersive_button)],
            ["翻译", "罗马音", "更多", "沉浸"],
        )

    def test_route_reuse_playback_sync_and_canvas_seek(self) -> None:
        page = self._lyrics_page()
        self.assertEqual(page.adapter.state.phase, "idle")
        self._play_library_track()
        self.assertEqual(page.adapter.state.phase, "ready")
        self.window.playback_adapter.advance_for_test(3_000)
        self.assertEqual(page.adapter.active_line.start_ms, 2_400)
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
        canvas_id = id(page.lyrics_view)
        event = QWheelEvent(
            QPointF(80, 80), QPointF(80, 80), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        page.lyrics_view.wheelEvent(event)
        self.assertTrue(page.lyrics_view.browsing)
        self.assertTrue(page.lyrics_view.return_button.isVisible())
        self.assertIs(page.lyrics_view.return_button.parent(), page.lyrics_view)
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
            self.assertEqual(id(page.lyrics_view), canvas_id)
            self.assertLessEqual(page._content_container.maximumWidth(), 1020)
            self.assertLessEqual(page.lyrics_view.maximumWidth(), 980)

    def test_browse_scroll_is_continuous_and_playback_follow_returns_cleanly(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        canvas = page.lyrics_view
        self.window.resize(1200, 800)
        self.app.processEvents()
        event = QWheelEvent(
            QPointF(80, 80), QPointF(80, 80), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        canvas.wheelEvent(event)
        canvas.repaint()
        self.app.processEvents()
        first_offset = canvas.last_metrics["browse_offset"]
        canvas.wheelEvent(event)
        canvas.repaint()
        self.app.processEvents()
        second_offset = canvas.last_metrics["browse_offset"]
        self.assertTrue(canvas.browsing)
        self.assertGreater(second_offset, first_offset)
        self.assertGreater(canvas.last_metrics["browse_content_height"], canvas.height())
        canvas.return_to_current()
        self.assertFalse(canvas.browsing)
        self.assertFalse(canvas.return_button.isVisible())

    def test_search_inputs_are_vertically_centered(self) -> None:
        for control in self.window.findChildren(QLineEdit):
            self.assertTrue(
                control.alignment() & Qt.AlignmentFlag.AlignVCenter,
                control.objectName() or "unnamed QLineEdit",
            )

    def test_search_inputs_use_optical_baseline_compensation(self) -> None:
        controls = self.window.findChildren(QLineEdit)
        self.assertTrue(controls)
        for control in controls:
            self.assertEqual(control.textMargins().top(), -2, control.objectName())
            self.assertEqual(control.textMargins().bottom(), 2, control.objectName())

    def test_immersive_overlay_releases_content_input_when_closed(self) -> None:
        self._play_library_track()
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        shell = self.window.router.currentWidget()
        self.assertTrue(
            shell.overlay_host.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )
        shell.show_settings_panel()
        self.app.processEvents()
        self.assertFalse(
            shell.overlay_host.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )
        shell.hide_settings_panel()
        self.app.processEvents()
        self.assertTrue(
            shell.overlay_host.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        )

    def test_immersive_volume_and_mute_controls_share_playback_state(self) -> None:
        self._play_library_track()
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        shell = self.window.router.currentWidget()
        controls = shell.controls
        adapter = self.window.playback_adapter
        adapter.set_muted(True)
        self.app.processEvents()
        self.assertTrue(adapter.state.is_muted)
        self.assertEqual(controls.volume_button.toolTip(), "取消静音")
        controls.volume_button.click()
        self.assertFalse(adapter.state.is_muted)
        adapter.set_volume(31)
        self.app.processEvents()
        self.assertEqual(controls.volume_slider.value(), 31)

    def test_distance_hierarchy_segments_and_light_readability(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        self.window.playback_adapter.seek(3_000)
        self.app.processEvents()
        self.assertFalse(page.lyrics_view.paints_line_background)
        self.assertGreater(page.lyrics_view.inactive_alpha_for_distance(1), page.lyrics_view.inactive_alpha_for_distance(2))
        self.assertGreater(page.lyrics_view.inactive_alpha_for_distance(2), page.lyrics_view.inactive_alpha_for_distance(4))
        self.assertGreater(page.lyrics_view.inactive_scale_for_distance(1), page.lyrics_view.inactive_scale_for_distance(3))
        for mode in ("dark", "light"):
            self.window.set_theme(mode)
            self.app.processEvents()
            self.assertEqual(page.lyrics_view.document, page.adapter.document)
            self.assertGreaterEqual(page.lyrics_view.inactive_alpha_for_distance(4), 80)
            self.assertGreater(page.lyrics_view._active_segment_index, -1)

    def test_ordinary_responsive_metrics_scale_continuously_without_rebuild(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        canvas = page.lyrics_view
        canvas_id = id(canvas)
        metrics_by_size = []
        for width, height in ((900, 600), (1200, 800), (1600, 900), (1920, 1080), (2048, 1113)):
            self.window.resize(width, height)
            self.app.processEvents()
            page.set_responsive_reference_width(width, height)
            metrics = canvas.responsive_metrics
            self.assertIsNotNone(metrics)
            metrics_by_size.append(metrics)
            self.assertEqual(id(canvas), canvas_id)
            self.assertLessEqual(metrics.active_font_size, 64)
            self.assertLessEqual(metrics.normal_font_size, 40)
            self.assertLessEqual(metrics.lyrics_max_width, 980)
        self.assertEqual(
            [metric.active_font_size for metric in metrics_by_size],
            sorted(metric.active_font_size for metric in metrics_by_size),
        )
        self.assertEqual(
            [metric.normal_font_size for metric in metrics_by_size],
            sorted(metric.normal_font_size for metric in metrics_by_size),
        )
        self.assertGreater(metrics_by_size[-1].line_spacing, metrics_by_size[0].line_spacing)
        self.assertGreater(metrics_by_size[-1].section_spacing, metrics_by_size[0].section_spacing)

    def test_ordinary_user_scale_and_subtitle_metrics_are_composed(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        canvas = page.lyrics_view
        sizes: dict[int, tuple[int, int, int, int]] = {}
        for scale in (75, 100, 125, 160):
            canvas.set_global_scale(scale)
            page.set_responsive_reference_width(1600, 900)
            sizes[scale] = canvas.effective_font_sizes
        self.assertLess(sizes[75][0], sizes[100][0])
        self.assertLess(sizes[100][0], sizes[125][0])
        self.assertLessEqual(sizes[125][0], sizes[160][0])
        self.assertLess(sizes[75][1], sizes[100][1])
        self.assertLess(sizes[100][1], sizes[125][1])
        expected = ResponsiveLyricsMetrics.for_viewport(
            1600,
            900,
            canvas.devicePixelRatioF(),
            100,
            translation_visible=True,
            romanization_visible=False,
        )
        self.assertEqual(
            sizes[100],
            (
                expected.active_font_size,
                expected.normal_font_size,
                expected.translation_font_size,
                expected.romanization_font_size,
            ),
        )
        canvas.set_global_scale(100)
        page.set_responsive_reference_width(1600, 900)
        before = canvas.responsive_metrics.section_spacing
        page.adapter.toggle_romanization()
        self.app.processEvents()
        self.assertGreaterEqual(canvas.responsive_metrics.section_spacing, before)

    def test_ordinary_active_line_stays_in_the_effective_viewport_band(self) -> None:
        self._play_library_track()
        page = self._lyrics_page()
        self.window.playback_adapter.seek(12_000)
        self.app.processEvents()
        canvas = page.lyrics_view
        for width, height in ((900, 600), (1200, 800), (1600, 900), (1920, 1080), (2048, 1113)):
            self.window.resize(width, height)
            self.app.processEvents()
            canvas.repaint()
            self.app.processEvents()
            active = page.adapter.active_line
            self.assertIsNotNone(active)
            metrics = canvas.responsive_metrics
            self.assertIsNotNone(metrics)
            rect = canvas._line_rects[active.id]
            target = metrics.top_safe_area + round(
                (canvas.height() - metrics.top_safe_area - metrics.bottom_safe_area) * 0.45
            )
            self.assertLessEqual(
                abs(rect.center().y() - target),
                max(8, metrics.active_font_size // 2),
                f"{width}x{height}: center={rect.center().y()} target={target} canvas={canvas.size()}",
            )

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


if __name__ == "__main__":
    unittest.main()
