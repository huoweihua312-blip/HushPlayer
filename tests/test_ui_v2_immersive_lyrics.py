from __future__ import annotations

import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QSlider

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.models.lyric_line import LyricLine, LyricSegment
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.pages.lyrics_page import LyricsPage
from app.ui_v2.shell.main_window import MainWindow, ShellPresentationMode
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2
from app.ui_v2.widgets.settings_control_factory import ThemedComboBox


class UiV2ImmersiveLyricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1400, 850)
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

    def _ordinary_page(self) -> LyricsPage:
        self.window.navigation_adapter.set_route("lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, LyricsPage)
        return page

    def _immersive_page(self) -> ImmersiveLyricsPage:
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersiveLyricsPage)
        return page

    def test_routes_are_distinct_cached_pages_and_shell_hides_then_restores(self) -> None:
        ordinary = self._ordinary_page()
        ordinary.toolbar.immersive_button.click()
        self.app.processEvents()
        immersive = self.window.router.currentWidget()
        self.assertIsInstance(immersive, ImmersiveLyricsPage)
        self.assertIsNot(ordinary, immersive)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertFalse(self.window.player_bar.isVisible())
        immersive.header_back_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "lyrics")
        self.assertIs(self.window.router.currentWidget(), ordinary)
        self.assertTrue(self.window.sidebar.isVisible())
        self.assertTrue(self.window.player_bar.isVisible())
        self.assertIs(self._immersive_page(), immersive)
        immersive.show_settings_panel()
        immersive.settings_panel.exit_immersive_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "lyrics")

    def test_shared_document_line_segment_display_and_seek_state(self) -> None:
        self._play_track()
        ordinary = self._ordinary_page()
        document = self.window.lyrics_adapter.document
        immersive = self._immersive_page()
        self.assertIs(immersive.lyrics_adapter, ordinary.adapter)
        self.assertIs(immersive.document, document)
        self.assertIs(immersive.canvas.document, document)
        self.window.playback_adapter.seek(3_000)
        self.app.processEvents()
        self.assertEqual(immersive.canvas.current_index, next(index for index, line in enumerate(document.lines) if line.id == ordinary.adapter.active_line.id))
        self.assertGreaterEqual(immersive.canvas._active_segment_index, 0)
        ordinary.toolbar.translation_button.click()
        ordinary.toolbar.romanization_button.click()
        self.app.processEvents()
        self.assertFalse(immersive.canvas._translation_visible)
        self.assertTrue(immersive.canvas._romanization_visible)
        immersive.set_translation_visible(True)
        immersive.set_romanization_visible(False)
        self.app.processEvents()
        self.assertTrue(self.window.lyrics_adapter.display_options["translation"])
        self.assertFalse(self.window.lyrics_adapter.display_options["romanization"])
        line = document.lines[8]
        immersive.canvas.seek_requested.emit(line.id)
        self.assertEqual(self.window.playback_adapter.state.position_ms, line.start_ms)

    def test_v4_immersive_identity_and_left_column_controls(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        self.assertIsInstance(immersive.canvas, LyricsCanvasV2)
        identity_labels = immersive.identity.findChildren(QLabel)
        self.assertEqual(
            {label.objectName() for label in identity_labels},
            {"immersiveTrackTitle", "immersiveTrackArtist", "immersiveTrackAlbum"},
        )
        self.assertFalse(immersive.canvas.paints_line_background)
        self.assertFalse(immersive.controls.autoFillBackground())
        self.assertEqual(immersive.header_back_button.toolTip(), "返回普通页面")
        self.assertTrue(immersive.controls.play_button.styleSheet())
        self.assertEqual(len(immersive.controls.findChildren(QSlider)), 2)
        self.assertIs(immersive.controls.parentWidget(), immersive)
        self.assertEqual(immersive._content_layout.itemAt(0).widget(), immersive.identity_column)
        self.assertEqual(immersive._content_layout.itemAt(1).widget(), immersive.canvas)
        self.assertGreaterEqual(immersive.controls.geometry().top(), immersive.content_stack.geometry().bottom())
        canvas_geometry = QRect(immersive.canvas.geometry())
        immersive.controls.hide()
        self.app.processEvents()
        self.assertEqual(immersive.canvas.geometry(), canvas_geometry)
        immersive.wake_controls()

    def test_shared_playback_controls_seek_volume_and_track_updates(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        controls = immersive.controls
        self.assertIs(controls._adapter, self.window.playback_adapter)
        controls.play_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.playback_adapter.state.is_playing)
        controls.play_button.click()
        controls.progress_slider.setValue(5_000)
        controls.progress_slider.sliderReleased.emit()
        controls.volume_slider.setValue(42)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.position_ms, 5_000)
        self.assertEqual(self.window.playback_adapter.state.volume, 42)
        first_track_id = self.window.playback_adapter.state.current_track.id
        controls.next_button.click()
        self.app.processEvents()
        self.assertNotEqual(self.window.playback_adapter.state.current_track.id, first_track_id)
        self.assertEqual(immersive.document.track_id, self.window.playback_adapter.state.current_track.id)
        self.assertEqual(controls.progress_slider.value(), self.window.playback_adapter.state.position_ms)
        controls.previous_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, first_track_id)

    def test_shared_playback_controls_mute_and_unmute_global_output(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        controls = immersive.controls
        self.window.playback_adapter.set_volume(68)
        self.app.processEvents()

        controls.volume_button.click()
        self.app.processEvents()
        self.assertTrue(self.window.playback_adapter.state.is_muted)
        self.assertEqual(controls.volume_button.toolTip(), "取消静音")
        self.assertEqual(self.window.player_bar.volume_button.toolTip(), "取消静音")
        muted_icon_key = controls.volume_button.icon().cacheKey()

        controls.volume_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.playback_adapter.state.is_muted)
        self.assertEqual(controls.volume_button.toolTip(), "静音")
        self.assertEqual(self.window.player_bar.volume_button.toolTip(), "静音")
        self.assertNotEqual(controls.volume_button.icon().cacheKey(), muted_icon_key)

    def test_options_survive_route_track_resize_and_reuse_core_widgets(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        panel = immersive.settings_panel
        core_ids = (id(immersive.canvas), id(immersive.identity), id(immersive.controls), id(panel), id(immersive.background))
        panel.background_combo.setCurrentIndex(panel.background_combo.findData("gradient"))
        panel.global_lyric_scale_slider.setValue(125)
        panel.active_font_slider.setValue(58)
        panel.auto_hide_check.setChecked(False)
        self.app.processEvents()
        self.assertEqual(immersive.options.background_mode, "gradient")
        self.assertEqual(immersive.options.global_font_scale, 125)
        self.assertEqual(immersive.options.active_font_size, 58)
        self.assertFalse(immersive.options.controls_auto_hide)
        effective = immersive.canvas.effective_font_sizes
        self.assertGreater(effective[0], effective[1])
        document = immersive.document
        background_generation = immersive.background.generation
        background_cache = immersive.background._cache
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(immersive.document, document)
            self.assertEqual((id(immersive.canvas), id(immersive.identity), id(immersive.controls), id(panel), id(immersive.background)), core_ids)
            self.assertEqual(immersive.background.generation, background_generation)
            self.assertIs(immersive.background._cache, background_cache)
        self.window.playback_adapter.play_next()
        self.app.processEvents()
        self.assertEqual(immersive.options.global_font_scale, 125)
        self.assertEqual(immersive.options.active_font_size, 58)
        self.window.navigation_adapter.set_route("lyrics")
        self._immersive_page()
        self.assertEqual(immersive.options.global_font_scale, 125)

    def test_fullscreen_escape_transparency_and_same_main_window(self) -> None:
        immersive = self._immersive_page()
        main_id = id(self.window)
        geometry = self.window.geometry()
        immersive.enter_fullscreen()
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.assertTrue(immersive.is_fullscreen)
        self.assertEqual(id(self.window), main_id)
        immersive.show_settings_panel()
        immersive.settings_panel.theme_combo.showPopup()
        self.app.processEvents()
        immersive._handle_escape()
        self.assertTrue(immersive.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        immersive._handle_escape()
        self.assertFalse(immersive.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        immersive._handle_escape()
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())
        self.assertEqual(self.window.geometry(), geometry)
        immersive.setFocus()
        QTest.keyClick(immersive, Qt.Key.Key_F11)
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        QTest.keyClick(immersive, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())
        immersive.set_background_mode("transparent")
        self.app.processEvents()
        self.assertEqual(id(self.window), main_id)
        self.assertTrue(self.window._immersive_transparency_enabled)
        self.assertEqual(immersive.root_background_alpha, 0)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertFalse(self.window.player_bar.isVisible())
        immersive.header_back_button.click()
        self.app.processEvents()
        self.assertFalse(self.window._immersive_transparency_enabled)

    def test_initial_transparent_option_syncs_the_existing_shell(self) -> None:
        self.window.immersive_lyrics_options.background_mode = "transparent"
        self.assertNotIn("immersive_lyrics", self.window.router._pages)
        windows_before = len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)])
        immersive = self._immersive_page()
        self.assertTrue(self.window._immersive_transparency_enabled)
        self.assertEqual(immersive.background_mode, "transparent")
        self.assertIs(immersive.parentWidget(), self.window.router)
        self.assertEqual(len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)]), windows_before)

    def test_auto_hide_and_all_five_geometry_bands(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        immersive.set_auto_hide_controls(True)
        immersive.hide_controls_preview()
        self.assertFalse(immersive.controls_visible)
        self.window.playback_adapter.pause()
        self.app.processEvents()
        self.assertTrue(immersive.controls_visible)
        immersive.show_settings_panel()
        immersive.hide_controls_preview()
        self.assertTrue(immersive.controls_visible)
        immersive.hide_settings_panel()
        expected = ((900, 600, "compact"), (1100, 700, "standard"), (1400, 850, "wide"), (1600, 900, "wide"), (1920, 1080, "ultra"))
        for width, height, band in expected:
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertEqual(immersive._layout_band, band)
            self.assertEqual(self.window.size(), QSize(width, height))
        immersive.enter_fullscreen()
        self.app.processEvents()
        self.assertTrue(immersive.is_fullscreen)
        immersive.exit_fullscreen()
        immersive.wake_controls()
        self.window.navigation_adapter.set_route("lyrics")
        self.app.processEvents()
        self.assertFalse(immersive._controls_hide_timer.isActive())

    def test_formal_page_accepts_dark_light_and_transparent_without_rebuild(self) -> None:
        immersive = self._immersive_page()
        core_ids = (id(immersive.canvas), id(immersive.controls), id(immersive.settings_panel))
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.app.processEvents()
            self.assertEqual(immersive.options.theme, mode)
            self.assertEqual(immersive._theme.mode, mode)
            self.assertEqual((id(immersive.canvas), id(immersive.controls), id(immersive.settings_panel)), core_ids)
        immersive.set_background_mode("transparent")
        self.app.processEvents()
        self.assertFalse(immersive.canvas.paints_row_background)
        self.assertFalse(immersive.lyric_protection.is_row_bound)
        self.assertEqual((id(immersive.canvas), id(immersive.controls), id(immersive.settings_panel)), core_ids)

    def test_settings_panel_allocates_content_space_and_restores_it(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        immersive.canvas.repaint()
        self.app.processEvents()
        canvas_id = id(immersive.canvas)
        closed_content = immersive.content.geometry()
        immersive.show_settings_panel()
        self.app.processEvents()
        immersive.canvas.repaint()
        self.app.processEvents()
        self.assertEqual(id(immersive.canvas), canvas_id)
        self.assertEqual(immersive.content.geometry(), closed_content)
        self.assertIs(immersive.settings_panel.parentWidget(), immersive.overlay_host)
        self.assertTrue(immersive.settings_panel.geometry().intersects(immersive.content.geometry()))
        immersive.hide_settings_panel()
        self.app.processEvents()
        self.assertEqual(immersive.content.geometry(), closed_content)
        self.assertEqual(id(immersive.canvas), canvas_id)

    def test_settings_panel_uses_opaque_theme_surfaces_and_popup(self) -> None:
        immersive = self._immersive_page()
        for mode in ("dark", "light"):
            self.window.set_theme(mode)
            immersive.show_settings_panel()
            self.app.processEvents()
            expected = QColor(immersive._theme.colors.elevated_background)
            viewport = immersive.settings_panel.scroll_area.viewport()
            actual = viewport.palette().color(QPalette.ColorRole.Base)
            self.assertEqual(actual.rgb(), expected.rgb())
            self.assertEqual(actual.alpha(), 255)
            label_color = QColor(immersive.settings_panel.title_label.palette().color(QPalette.ColorRole.WindowText))
            self.assertGreater(abs(label_color.lightness() - actual.lightness()), 30)
            popup = immersive.settings_panel.theme_combo.view()
            popup_base = popup.palette().color(QPalette.ColorRole.Base)
            self.assertEqual(popup_base.alpha(), 255)
            self.assertEqual(popup_base.rgb(), expected.rgb())

    def test_transparent_background_keeps_content_and_panel_opaque(self) -> None:
        immersive = self._immersive_page()
        core_ids = (id(immersive.canvas), id(immersive.controls), id(immersive.settings_panel), id(immersive.background))
        immersive.set_background_mode("transparent")
        immersive.set_background_opacity(30)
        first_alpha = immersive.canvas.active_text_alpha
        immersive.show_settings_panel()
        self.app.processEvents()
        self.assertEqual(immersive.content_layer_alpha, 255)
        self.assertEqual(immersive.settings_panel.surface_alpha, 255)
        self.assertEqual(immersive.canvas.active_text_alpha, first_alpha)
        immersive.set_background_opacity(70)
        self.assertEqual(immersive.canvas.active_text_alpha, first_alpha)
        self.assertEqual((id(immersive.canvas), id(immersive.controls), id(immersive.settings_panel), id(immersive.background)), core_ids)

    def test_long_active_line_wraps_to_two_lines_without_elision_and_keeps_segments(self) -> None:
        immersive = self._immersive_page()
        canvas = immersive.canvas
        words = ("we", "follow", "the", "quiet", "lights", "beyond", "the", "city", "where", "morning", "finds", "us")
        text = " ".join(words)
        segments = tuple(
            LyricSegment(word, index * 300, (index + 1) * 300, "word")
            for index, word in enumerate(words)
        )
        line = LyricLine("long-active", 0, 4_000, text, segments=segments)
        canvas.set_document(LyricsDocument("long", "Long", "Artist", "mock", (line,)))
        canvas.set_active_line(line)
        canvas.set_active_segment(line, len(segments) - 1, 1.0)
        canvas.set_max_text_width(480)
        canvas.resize(520, 500)
        canvas.show()
        canvas.repaint()
        self.app.processEvents()
        metrics = canvas.last_metrics
        self.assertLessEqual(metrics["active_line_count"], 2)
        self.assertEqual(metrics["active_line_elided"], 0)
        self.assertEqual(metrics["active_highlight_line_count"], metrics["active_line_count"])

    def test_immersive_highlight_interpolates_and_stops_when_paused(self) -> None:
        immersive = self._immersive_page()
        canvas = immersive.canvas
        segments = tuple(
            LyricSegment(character, index * 240, (index + 1) * 240, "character")
            for index, character in enumerate("逐字高亮")
        )
        line = LyricLine("smooth-highlight", 0, 960, "逐字高亮", segments=segments)
        canvas.set_document(LyricsDocument("smooth", "Smooth", "Artist", "mock", (line,)))
        canvas.set_active_line(line)
        canvas.set_active_segment(line, 1, 0.35)
        canvas.set_playback_active(True)
        self.assertTrue(canvas._highlight_timer.isActive())
        self.assertEqual(canvas._highlight_timer.interval(), 16)
        self.assertGreater(canvas._highlight_character_progress(line), 1.0)
        canvas.set_playback_active(False)
        self.assertFalse(canvas._highlight_timer.isActive())

    def test_external_position_updates_do_not_reset_smooth_highlight_clock(self) -> None:
        immersive = self._immersive_page()
        canvas = immersive.canvas
        segments = tuple(
            LyricSegment(character, index * 240, (index + 1) * 240, "character")
            for index, character in enumerate("连续高亮")
        )
        line = LyricLine("external-clock", 0, 960, "连续高亮", segments=segments)
        canvas.set_document(LyricsDocument("clock", "Clock", "Artist", "mock", (line,)))
        canvas.set_active_line(line)
        canvas.set_active_segment(line, 0, 0.0)
        canvas.set_playback_active(True)
        QTest.qWait(130)
        elapsed_before_update = canvas._playback_clock.elapsed()
        canvas.set_playback_position(130)
        elapsed_after_update = canvas._playback_clock.elapsed()
        self.assertGreater(elapsed_after_update, max(20, elapsed_before_update // 2))
        canvas.set_playback_active(False)

    def test_active_segment_updates_do_not_snap_playing_highlight(self) -> None:
        immersive = self._immersive_page()
        canvas = immersive.canvas
        segments = tuple(
            LyricSegment(character, index * 240, (index + 1) * 240, "character")
            for index, character in enumerate("连续绘制")
        )
        line = LyricLine("segment-sync", 0, 960, "连续绘制", segments=segments)
        canvas.set_document(LyricsDocument("segment", "Segment", "Artist", "mock", (line,)))
        canvas.set_active_line(line)
        canvas.set_active_segment(line, 0, 0.0)
        canvas.set_playback_active(True)
        QTest.qWait(150)
        elapsed_before_signal = canvas._playback_clock.elapsed()
        canvas.set_active_segment(line, 0, 0.0)
        elapsed_after_signal = canvas._playback_clock.elapsed()
        self.assertGreater(elapsed_after_signal, max(30, elapsed_before_signal // 2))
        canvas.set_playback_active(False)

    def test_highlight_progress_maps_to_real_glyph_widths(self) -> None:
        immersive = self._immersive_page()
        canvas = immersive.canvas
        segments = tuple(
            LyricSegment(value, index * 400, (index + 1) * 400, "character")
            for index, value in enumerate(("W", "中", "i"))
        )
        line = LyricLine("glyph-widths", 0, 1_200, "W中i", segments=segments)
        canvas.set_document(LyricsDocument("glyphs", "Glyphs", "Artist", "mock", (line,)))
        canvas.set_active_line(line)
        canvas.set_active_segment(line, 1, 0.5)
        canvas.resize(520, 320)
        canvas.show()
        self.app.processEvents()

        font = canvas._font(canvas.effective_font_sizes[0], canvas._active_weight())
        metrics = canvas._wrapped_line_ranges(font, line.text, 480)
        self.assertEqual("".join(value for value, _start, _end in metrics), line.text)
        progress = canvas._highlight_character_progress(line)
        self.assertEqual(progress, 1.5)
        first_glyph = canvas._font(canvas.effective_font_sizes[0], canvas._active_weight())
        first_width = canvas.fontMetrics().horizontalAdvance("W")
        self.assertGreater(first_width, 0)
        self.assertGreater(
            canvas.fontMetrics().horizontalAdvance("W中") - first_width,
            0,
        )
        self.assertEqual(first_glyph.family(), font.family())

    def test_unplayable_track_suppresses_default_lyrics_with_warning(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        current = self.window.playback_adapter.state.current_track
        self.assertIsNotNone(current)
        unavailable = replace(
            current,
            source_type="online",
            availability="unavailable",
            is_missing=True,
        )
        self.window.lyrics_adapter.set_track(unavailable)
        self.app.processEvents()
        self.assertIsNone(self.window.lyrics_adapter.document)
        self.assertEqual(self.window.lyrics_adapter.state.phase, "playback_unavailable")
        self.assertEqual(immersive.lyrics_state_view.title_label.text(), "歌曲无法播放")
        self.assertIn("暂不显示默认歌词", immersive.lyrics_state_view.detail_label.text())

        self.window.lyrics_adapter.set_track(current)
        self.window.lyrics_adapter.set_playback_status("error", "当前无法播放这首歌曲")
        self.app.processEvents()
        self.assertIsNone(self.window.lyrics_adapter.document)
        self.assertEqual(self.window.lyrics_adapter.state.phase, "playback_unavailable")

    def test_immersive_empty_state_uses_full_content_geometry_and_restores(self) -> None:
        immersive = self._immersive_page()
        self.window.playback_adapter.clear()
        self.app.processEvents()
        self.assertFalse(immersive.identity_column.isVisible())
        self.assertFalse(immersive.canvas.isVisible())
        self.assertTrue(immersive.lyrics_state_view.isVisible())
        self.assertEqual(immersive.lyrics_state_view.geometry(), immersive.content.rect())

        self._play_track()
        self.app.processEvents()
        self.assertTrue(immersive.identity_column.isVisible())
        self.assertEqual(immersive.lyrics_state_view.geometry(), immersive.canvas.geometry())

    def test_large_immersive_layout_keeps_identity_inset_and_canvas_width(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        for width, height in ((1200, 800), (1600, 900), (2048, 1152)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertLessEqual(immersive.identity_column.maximumWidth(), 560)
            self.assertGreater(immersive.canvas.width(), 600)
            self.assertGreaterEqual(immersive.identity_column.geometry().x(), 0)

    def test_identity_title_uses_at_most_two_lines_and_compact_sheet_has_no_overlap(self) -> None:
        immersive = self._immersive_page()
        title = "A long quiet title that belongs on two natural lines before it ever elides"
        immersive.identity.title_label.set_full_text(title)
        immersive.identity.resize(300, 500)
        immersive.identity.title_label.resize(280, immersive.identity.title_label.minimumHeight())
        self.app.processEvents()
        self.assertLessEqual(immersive.identity.title_label.line_count, 2)
        self.assertEqual(immersive.identity.title_label.toolTip(), title)
        core_ids = (id(immersive.canvas), id(immersive.identity), id(immersive.controls), id(immersive.settings_panel))
        self.window.resize(900, 600)
        immersive.show_settings_panel()
        self.app.processEvents()
        self.assertTrue(immersive.content.isVisible())
        self.assertGreaterEqual(immersive.settings_panel.width(), 310)
        self.assertTrue(immersive.controls.isVisible())
        self.assertEqual((id(immersive.canvas), id(immersive.identity), id(immersive.controls), id(immersive.settings_panel)), core_ids)

    def test_presentation_mode_removes_shell_columns_and_restores_them_without_drift(self) -> None:
        main_id = id(self.window)
        normal_geometry = self.window.geometry()
        for _ in range(5):
            immersive = self._immersive_page()
            self.app.processEvents()
            self.assertEqual(self.window.presentation_mode, ShellPresentationMode.IMMERSIVE)
            self.assertFalse(self.window.sidebar.isVisible())
            self.assertFalse(self.window.sidebar_container.isVisible())
            self.assertFalse(self.window.player_bar_container.isVisible())
            self.assertEqual(self.window.sidebar_container.maximumWidth(), 0)
            self.assertEqual(self.window._body_layout.itemAt(0).geometry().width(), 0)
            page_origin = immersive.mapTo(self.window.root, QPoint(0, 0))
            self.assertEqual(QRect(page_origin, immersive.size()), self.window.root.contentsRect())
            immersive.enter_fullscreen()
            self.app.processEvents()
            self.assertTrue(self.window.isFullScreen())
            self.assertEqual(self.window.presentation_mode, ShellPresentationMode.IMMERSIVE_FULLSCREEN)
            immersive.exit_fullscreen()
            self.app.processEvents()
            self.assertFalse(self.window.isFullScreen())
            self.assertEqual(self.window.presentation_mode, ShellPresentationMode.IMMERSIVE)
            immersive.header_back_button.click()
            self.app.processEvents()
            self.assertEqual(self.window.presentation_mode, ShellPresentationMode.NORMAL)
            self.assertTrue(self.window.sidebar_container.isVisible())
            self.assertTrue(self.window.player_bar_container.isVisible())
            self.assertGreater(self.window._body_layout.itemAt(0).geometry().width(), 0)
            self.assertEqual(id(self.window), main_id)
        self.assertEqual(self.window.geometry(), normal_geometry)

    def test_transparency_chain_uses_existing_window_and_restores_normal_shell(self) -> None:
        immersive = self._immersive_page()
        window_id = id(self.window)
        geometry = self.window.geometry()
        top_levels = len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)])
        self.assertTrue(self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        immersive.set_background_mode("transparent")
        immersive.set_background_opacity(0)
        self.app.processEvents()
        debug = self.window.transparency_debug_state
        self.assertTrue(self.window._immersive_transparency_enabled)
        self.assertTrue(debug["main_translucent"])
        self.assertFalse(debug["central_auto_fill"])
        self.assertEqual(debug["root_window_alpha"], 0)
        self.assertEqual(debug["body_window_alpha"], 0)
        self.assertEqual(debug["content_window_alpha"], 0)
        self.assertEqual(immersive.content_layer_alpha, 255)
        self.assertEqual(id(self.window), window_id)
        self.assertEqual(len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)]), top_levels)
        immersive.set_background_mode("artwork")
        self.app.processEvents()
        self.assertFalse(self.window._immersive_transparency_enabled)
        self.assertEqual(id(self.window), window_id)
        self.assertEqual(self.window.geometry(), geometry)
        immersive.header_back_button.click()
        self.app.processEvents()
        self.assertFalse(self.window._immersive_transparency_enabled)
        self.assertEqual(self.window.presentation_mode, ShellPresentationMode.NORMAL)

    def test_transparency_mode_reuses_one_visible_main_window_across_ten_switches(self) -> None:
        immersive = self._immersive_page()
        main_id = id(self.window)
        geometry = self.window.geometry()
        top_levels = len(
            [widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)]
        )
        core_ids = (
            id(immersive.canvas),
            id(immersive.identity),
            id(immersive.controls),
            id(immersive.settings_panel),
        )
        for _ in range(10):
            immersive.set_background_mode("transparent")
            immersive.set_background_opacity(0)
            self.app.processEvents()
            self.assertTrue(self.window.isVisible())
            self.assertEqual(id(self.window), main_id)
            self.assertEqual(self.window.geometry(), geometry)
            self.assertEqual(
                len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)]),
                top_levels,
            )
            immersive.set_background_mode("artwork")
            self.app.processEvents()
            self.assertTrue(self.window.isVisible())
            self.assertEqual(self.window.geometry(), geometry)
            self.assertEqual(
                (id(immersive.canvas), id(immersive.identity), id(immersive.controls), id(immersive.settings_panel)),
                core_ids,
            )

    def test_panel_uses_themed_combo_and_disclosure_controls(self) -> None:
        immersive = self._immersive_page()
        panel = immersive.settings_panel
        panel.show()
        self.app.processEvents()
        for combo in (panel.theme_combo, panel.background_combo, panel.weight_combo, panel.text_protection_combo):
            self.assertIsInstance(combo, ThemedComboBox)
            self.assertTrue(combo.native_arrow_suppressed)
            self.assertGreaterEqual(combo.arrow_hit_width, 32)
            self.assertIn("down-arrow { image: none", combo.styleSheet())
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
            self.app.processEvents()
            self.assertTrue(combo.popup_open)
            self.assertTrue(combo.view().isVisible())
            QTest.keyClick(combo, Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertFalse(combo.popup_open)
        disclosure = panel.advanced_disclosure
        self.assertTrue(disclosure.uses_v2_chevron)
        self.assertGreaterEqual(disclosure.minimumHeight(), 32)
        self.assertFalse(panel.advanced_content.isVisible())
        disclosure.click()
        self.app.processEvents()
        self.assertTrue(disclosure.isChecked())
        self.assertTrue(panel.advanced_content.isVisible())
        panel.set_reduce_motion(True)
        disclosure.click()
        self.app.processEvents()
        self.assertFalse(disclosure.isChecked())
        self.assertFalse(panel.advanced_content.isVisible())


if __name__ == "__main__":
    unittest.main()
