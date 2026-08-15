from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from app.services.online_artwork_service import OnlineArtworkService
from app.services.library_repository import LibraryRecords, LibrarySnapshot, PlaylistRecords
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.real_library_adapter import RealLibraryAdapter
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.online_track_model import ONLINE_TRACK_ROLE, OnlineColumn, OnlineTrackModel
from app.ui_v2.models.track import Track
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.shell.immersive_player_shell import ImmersivePlayerShell
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail, artwork_pixmap_for_track
from app.ui_v2.widgets.online_result_table import OnlineResultDelegate


def _png(color: QColor) -> bytes:
    image = QImage(18, 18, QImage.Format.Format_ARGB32)
    image.fill(color)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _remote_track(track_id: str, color: QColor, *, artwork: bool = True) -> Track:
    data = _png(color) if artwork else b""
    return Track(
        id=track_id,
        title=f"Remote {track_id}",
        artist="Fixture Artist",
        album="Fixture Album",
        duration_ms=180_000,
        source_id="fixture-source",
        source_name="Fixture Source",
        source_type="online",
        added_at=datetime(2026, 8, 10, 9, 0),
        is_favorite=False,
        is_missing=False,
        is_loading=False,
        artwork_path=None,
        stable_identity=f"remote:fixture-source:{track_id}",
        artwork_key=f"https://fixture.invalid/{track_id}.png" if artwork else "",
        artwork_url=f"https://fixture.invalid/{track_id}.png" if artwork else "",
        artwork_data=data,
        remote_identity=f"remote:fixture-source:{track_id}",
        remote_track_id=track_id,
        remote_payload={
            "id": track_id,
            "sourceId": "fixture-source",
            "artwork": f"https://fixture.invalid/{track_id}.png" if artwork else "",
        },
    )


class Q5B1RealInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="hushplayer-q5b1-ui-")
        self.settings_path = Path(self.temporary_directory.name) / "settings.json"
        self.window = MainWindow(data_mode="mock", settings_path=self.settings_path)
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temporary_directory.cleanup()

    def _play_track(self) -> None:
        track = next(
            track
            for track in self.window.library_collection.tracks()
            if not track.is_missing and track.duration_ms is not None
        )
        self.window.playback_adapter.set_queue((track,))
        self.window.playback_adapter.play_track(track.id)
        self.app.processEvents()

    def _immersive_shell(self, route: str = "immersive_now_playing") -> ImmersivePlayerShell:
        self.window.navigation_adapter.set_route(route)
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersivePlayerShell)
        return page

    def test_title_bar_history_and_app_shortcuts_are_real_actions(self) -> None:
        self.window.navigation_adapter.set_route("library")
        self.window.navigation_adapter.set_route("online_search")
        self.app.processEvents()

        self.assertTrue(self.window.title_bar.back_button.isEnabled())
        self.assertFalse(self.window.title_bar.forward_button.isEnabled())
        self.window.title_bar.back_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "library")
        self.assertTrue(self.window.title_bar.forward_button.isEnabled())
        self.window.title_bar.forward_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "online_search")
        self.assertEqual(self.window.previous_track_shortcut.key().toString(), "Ctrl+Alt+Left")
        self.assertEqual(self.window.play_pause_shortcut.key().toString(), "Ctrl+Alt+Space")
        self.assertEqual(self.window.next_track_shortcut.key().toString(), "Ctrl+Alt+Right")

    def test_immersive_foreground_keys_control_volume_and_progress(self) -> None:
        self._play_track()
        shell = self._immersive_shell("immersive_lyrics")
        self.window.playback_adapter.pause()
        original_volume = self.window.playback_adapter.state.volume
        self.window.playback_adapter.seek(10_000)

        QTest.keyClick(shell, Qt.Key.Key_Space)
        QTest.keyClick(shell, Qt.Key.Key_Up)
        QTest.keyClick(shell, Qt.Key.Key_Left)
        self.assertTrue(self.window.playback_adapter.state.is_playing)
        self.assertEqual(self.window.playback_adapter.state.volume, min(100, original_volume + 5))
        self.assertEqual(self.window.playback_adapter.state.position_ms, 5_000)

        QTest.keyClick(shell, Qt.Key.Key_Down)
        QTest.keyClick(shell, Qt.Key.Key_Right)
        self.assertEqual(self.window.playback_adapter.state.volume, original_volume)
        self.assertEqual(self.window.playback_adapter.state.position_ms, 10_000)

    def test_immersive_controls_wake_on_hover_and_hide_after_pointer_leaves(self) -> None:
        self._play_track()
        shell = self._immersive_shell("immersive_lyrics")
        shell._controls_hide_timer.setInterval(20)
        shell.controls.hide()
        inside = shell.controls.geometry().center()
        outside = QPoint(20, 20)

        QTest.mouseMove(shell, inside)
        self.app.processEvents()
        self.assertTrue(shell.controls.isVisible())
        self.assertFalse(shell._controls_hide_timer.isActive())

        QTest.mouseMove(shell, outside)
        self.app.processEvents()
        self.assertTrue(shell._controls_hide_timer.isActive())
        QTest.qWait(40)
        self.app.processEvents()
        self.assertFalse(shell.controls.isVisible())

    def test_queue_panel_follows_active_queue_without_reordering_playlist_view(self) -> None:
        playlist_id = "playlist-seed-1"
        persisted_order = tuple(
            track.id for track in self.window.playlist_adapter.tracks_for_playlist(playlist_id)
        )
        self.window.navigation_adapter.set_route(f"playlist:{playlist_id}")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        source_tracks = tuple(page.adapter.tracks())
        self.assertGreaterEqual(len(source_tracks), 3)
        queue = (source_tracks[2], source_tracks[0], source_tracks[1], *source_tracks[3:])

        self.window.playback_adapter.set_queue(queue)
        self.window.playback_adapter.play_track(queue[1].id)
        self.app.processEvents()

        persisted_page_order = [track.id for track in page.adapter.tracks()]
        self.assertEqual(
            persisted_page_order,
            [track.id for track in source_tracks],
        )
        self.assertEqual(
            tuple(track.id for track in self.window.playlist_adapter.tracks_for_playlist(playlist_id)),
            persisted_order,
        )

        shell = self._immersive_shell()
        shell.show_queue_panel()
        self.app.processEvents()
        expected_queue_order = [track.id for track in queue[1:]] + [queue[0].id]
        self.assertEqual(
            [track.id for track in shell.queue_panel.model._tracks],
            expected_queue_order,
        )

    def test_queue_uses_full_model_and_real_mouse_keyboard_lifecycle(self) -> None:
        base = self.window.library_collection.tracks()[0]
        tracks = tuple(
            replace(
                base,
                id=f"queue-{index}",
                title=f"Queue Track {index}",
                source_type="online",
                source_id="fixture-source",
                source_name="Fixture Source",
                is_missing=False,
                stable_identity=f"queue:fixture:{index}",
                remote_identity=f"queue:fixture:{index}",
                remote_track_id=str(index),
            )
            for index in range(27)
        )
        self.window.playback_adapter.set_queue(tracks)
        self.window.playback_adapter.play_track(tracks[0].id)
        shell = self._immersive_shell()
        shell.show_queue_panel()
        self.app.processEvents()
        panel = shell.queue_panel
        view = panel.view
        proxy = view.model()

        self.assertIsInstance(shell, ImmersiveLyricsPage)
        self.assertIs(panel.parentWidget(), shell.overlay_host)
        self.assertEqual(panel.model.rowCount(), 27)
        self.assertEqual(proxy.rowCount(), 26)
        self.assertEqual(panel.model.track_at(0).id, tracks[0].id)
        self.assertEqual(panel.model.current_id, tracks[0].id)

        first_index = proxy.index(0, 0)
        target = first_index.data(Qt.ItemDataRole.UserRole)
        row_rect = view.visualRect(first_index)
        self.assertTrue(row_rect.isValid())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center())
        self.app.processEvents()
        self.assertEqual(panel.selected_track_id, target.id)
        self.assertEqual(self.window.playback_adapter.state.current_track.id, tracks[0].id)

        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center())
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, target.id)
        self.assertEqual(self.window.playback_adapter.state.current_index, 1)
        self.assertEqual(panel.current_artwork._track.id, target.id)
        self.assertEqual(self.window.player_bar.artwork._track.id, target.id)
        self.assertEqual(shell.now_playing_page.artwork._track.id, target.id)

        enter_index = proxy.index(1, 0)
        enter_target = enter_index.data(Qt.ItemDataRole.UserRole)
        enter_rect = view.visualRect(enter_index)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=enter_rect.center())
        self.app.processEvents()
        self.assertEqual(panel.selected_track_id, enter_target.id)
        self.assertEqual(self.window.playback_adapter.state.current_track.id, target.id)
        QTest.keyClick(view, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, enter_target.id)

        scrollbar = view.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        before_scroll = scrollbar.value()
        viewport_position = view.viewport().rect().center()
        global_position = view.viewport().mapToGlobal(viewport_position)
        wheel_event = QWheelEvent(
            QPointF(viewport_position),
            QPointF(global_position),
            QPoint(0, -720),
            QPoint(0, -720),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QCoreApplication.sendEvent(view.viewport(), wheel_event)
        self.app.processEvents()
        self.assertGreater(scrollbar.value(), before_scroll)

        panel_id = id(panel)
        QTest.mouseClick(panel.close_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(panel.isVisible())
        shell.show_queue_panel()
        self.app.processEvents()
        self.assertEqual(id(shell.queue_panel), panel_id)
        self.assertEqual(shell.queue_panel.model.rowCount(), 27)

    def test_quick_settings_previews_rolls_back_and_persists_through_session(self) -> None:
        shell = self._immersive_shell("immersive_lyrics")
        self.assertIsInstance(shell, ImmersiveLyricsPage)
        shell.show_settings_panel()
        self.app.processEvents()
        panel = shell.settings_panel
        self.assertIsNotNone(panel.session)
        original_scale = shell.options.global_font_scale
        original_transparency = shell.options.background_transparency
        original_effective_size = shell.canvas.effective_font_sizes[0]

        preview_scale = min(panel.global_lyric_scale_slider.maximum(), original_scale + 12)
        panel.global_lyric_scale_slider.setValue(preview_scale)
        panel.background_transparency_slider.setValue(44)
        self.app.processEvents()
        self.assertTrue(panel.is_dirty)
        self.assertIn("immersive_lyrics_font_scale", panel.session.previewed_fields)
        self.assertIn("immersive_background_transparency", panel.session.previewed_fields)
        self.assertEqual(shell.options.global_font_scale, preview_scale)
        self.assertGreater(shell.canvas.effective_font_sizes[0], original_effective_size)
        self.assertEqual(shell.options.background_transparency, 44)
        self.assertEqual(shell.background._transparency, 44)

        QTest.mouseClick(panel.cancel_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(panel.isVisible())
        self.assertEqual(shell.options.global_font_scale, original_scale)
        self.assertEqual(shell.options.background_transparency, original_transparency)
        self.assertFalse(self.settings_path.exists())

        shell.show_settings_panel()
        self.app.processEvents()
        saved_scale = min(panel.global_lyric_scale_slider.maximum(), original_scale + 8)
        panel.global_lyric_scale_slider.setValue(saved_scale)
        self.app.processEvents()
        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertTrue(panel.isVisible())
        self.assertFalse(panel.is_dirty)
        self.assertEqual(panel.status_label.text(), "已保存")
        saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["immersive_lyrics_font_scale"], saved_scale)

        panel.close_button.click()
        self.app.processEvents()
        shell.show_settings_panel()
        self.app.processEvents()
        normalized_saved_scale = int(round(saved_scale / 5.0) * 5)
        self.assertEqual(panel.global_lyric_scale_slider.value(), normalized_saved_scale)
        self.assertEqual(shell.options.global_font_scale, normalized_saved_scale)
        panel.cancel_button.click()

    def test_floating_panels_stay_above_playback_controls(self) -> None:
        shell = self._immersive_shell()

        for width, height in ((900, 700), (1200, 800), (1600, 900)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.app.processEvents()
                controls_top = shell.controls.geometry().top()

                shell.show_queue_panel()
                self.app.processEvents()
                self.assertLess(
                    shell.queue_panel.geometry().bottom(),
                    controls_top,
                )
                shell.hide_queue_panel()

                shell.show_settings_panel()
                self.app.processEvents()
                self.assertLess(
                    shell.settings_panel.geometry().bottom(),
                    controls_top,
                )
                shell.hide_settings_panel()

    def test_custom_background_selection_activates_and_renders_image(self) -> None:
        image_path = Path(self.temporary_directory.name) / "custom-background.png"
        image = QImage(80, 60, QImage.Format.Format_ARGB32)
        image.fill(QColor("#b84f42"))
        self.assertTrue(image.save(str(image_path)))

        shell = self._immersive_shell()
        shell.show_settings_panel()
        self.app.processEvents()
        panel = shell.settings_panel
        custom_index = panel.background_combo.findData("custom")
        self.assertGreaterEqual(custom_index, 0)
        panel.custom_path_label.setText(str(image_path))
        panel.background_combo.setCurrentIndex(custom_index)
        panel.changed.emit()
        self.app.processEvents()

        self.assertEqual(shell.options.background_mode, "custom")
        self.assertEqual(shell.options.background_custom_path, str(image_path))
        self.assertTrue(shell.background.custom_image_available)
        self.assertFalse(shell.background.grab().isNull())

    def test_quick_settings_persists_each_background_visual_mode(self) -> None:
        shell = self._immersive_shell("immersive_lyrics")
        shell.show_settings_panel()
        self.app.processEvents()
        panel = shell.settings_panel

        for mode, legacy_mode in (
            ("gradient", "default"),
            ("solid", "default"),
            ("transparent", "translucent"),
        ):
            panel.background_combo.setCurrentIndex(panel.background_combo.findData(mode))
            self.app.processEvents()
            self.assertTrue(panel.is_dirty)
            self.assertEqual(shell.options.background_mode, mode)

            panel.save_button.click()
            self.app.processEvents()
            document = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.assertEqual(document["immersive_background_mode"], legacy_mode)
            self.assertEqual(document["immersive_background_visual_mode"], mode)
            self.assertFalse(panel.is_dirty)

            panel.begin_session()
            self.app.processEvents()
            self.assertEqual(panel.background_combo.currentData(), mode)


class Q5B1ArtworkPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _center_color(pixmap) -> tuple[int, int, int, int]:
        color = pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2)
        return color.getRgb()

    def test_theme_change_keeps_loaded_thumbnail_pixmap(self) -> None:
        thumbnail = ArtworkThumbnail(get_theme("dark"), size=56, clip_artwork=True)
        track = _remote_track("theme-cache", QColor(17, 201, 177))
        try:
            thumbnail.set_track(track)
            before = thumbnail._artwork_pixmap.cacheKey()
            self.assertNotEqual(before, 0)
            with patch(
                "app.ui_v2.widgets.artwork_thumbnail.artwork_pixmap_for_track",
                side_effect=AssertionError("theme changes must not reload artwork"),
            ):
                thumbnail.set_theme(get_theme("light"))
            self.assertEqual(thumbnail._artwork_pixmap.cacheKey(), before)
        finally:
            thumbnail.deleteLater()
            self.app.processEvents()

    def test_remote_identity_cache_stale_protection_and_surface_consistency(self) -> None:
        raw = {
            "id": "track-a",
            "sourceId": "fixture-source",
            "title": "封面 A",
            "artist": "Fixture Artist",
            "album": "Fixture Album",
            "artwork": "https://fixture.invalid/track-a.png",
            "duration": 180,
        }
        stable_id, record = RemoteTrackStore.build_record(raw)
        normalized = RemoteTrackStore.to_online_track(stable_id, record)
        self.assertEqual(normalized["artwork"], raw["artwork"])
        track_a = replace(
            _remote_track("track-a", QColor(17, 201, 177)),
            id=stable_id,
            stable_identity=stable_id,
            remote_identity=stable_id,
            artwork_url=raw["artwork"],
            artwork_key=raw["artwork"],
            remote_payload=normalized,
        )
        track_b = _remote_track("track-b", QColor(224, 70, 116))
        track_c = _remote_track("track-c", QColor(0, 0, 0), artwork=False)
        expected_a = self._center_color(artwork_pixmap_for_track(track_a, 56, 56))
        expected_b = self._center_color(artwork_pixmap_for_track(track_b, 46, 46))

        snapshot = LibrarySnapshot(
            library=LibraryRecords((), "empty", "", True),
            playlists=PlaylistRecords({}, "", False),
            song_stats={},
        )
        mapped = RealLibraryAdapter.map_snapshot(snapshot, {stable_id: record})
        self.assertEqual(mapped.tracks[0].artwork_url, raw["artwork"])

        with tempfile.TemporaryDirectory(prefix="hushplayer-art-cache-") as cache_dir:
            service = OnlineArtworkService(Path(cache_dir))
            image_ready: list[tuple[int, str, bytes]] = []
            service.imageReady.connect(lambda generation, key, data: image_ready.append((generation, key, data)))
            cache_path = Path(cache_dir) / "online"
            cache_path.mkdir(parents=True)
            cache_file = cache_path / (
                hashlib.sha256(track_a.artwork_url.encode("utf-8")).hexdigest() + ".img"
            )
            cache_file.write_bytes(track_a.artwork_data)
            generation = service.request(track_a.stable_identity, track_a.artwork_url)
            self.assertEqual(image_ready[-1], (generation, track_a.stable_identity, track_a.artwork_data))
            service.cancel()

        collection = LibraryCollectionAdapter((track_a, track_b, track_c))
        playlists = PlaylistAdapter(collection, seed_mock=False)
        adapter = OnlineAdapter(collection, playlists, timer_enabled=False)
        adapter._results = (
            OnlineTrack(
                id=track_a.id,
                source_id=track_a.source_id,
                source_name=track_a.source_name,
                title=track_a.title,
                artist=track_a.artist,
                album=track_a.album,
                duration_ms=track_a.duration_ms,
                artwork_key=track_a.artwork_key,
                quality="standard",
                stable_identity=track_a.stable_identity,
                is_favorite=False,
                is_downloaded=False,
                is_cached=False,
                availability="available",
                explicit=False,
                result_rank=0,
                artwork_url=track_a.artwork_url,
                raw=track_a.remote_payload,
                artwork_data=track_a.artwork_data,
            ),
        )
        adapter._publish_track(track_a)
        self.assertEqual(collection.track_for_id(track_a.id).artwork_data, track_a.artwork_data)
        remapped = adapter._map_formal_track(track_a.remote_payload, 0)
        self.assertEqual(remapped.artwork_url, track_a.artwork_url)
        self.assertEqual(remapped.artwork_data, track_a.artwork_data)
        adapter._artwork_generation = 2
        adapter._on_artwork_ready(1, track_a.id, track_b.artwork_data)
        self.assertEqual(adapter.results()[0].artwork_data, track_a.artwork_data)
        fallback = artwork_pixmap_for_track(track_c, 46, 46)
        self.assertFalse(fallback.isNull())

        window = MainWindow(data_mode="mock", settings_path=Path(tempfile.gettempdir()) / "hushplayer-q5b1-artwork-test.json")
        window.playback_adapter._timer_enabled = False
        try:
            window.resize(1200, 800)
            window.show()
            window.library_collection.upsert_track(mapped.tracks[0])
            window.playback_adapter.set_queue((mapped.tracks[0],))
            window.playback_adapter.play_track(mapped.tracks[0].id)
            window._on_online_artwork_ready(1, mapped.tracks[0].stable_identity, track_a.artwork_data)
            self.assertEqual(
                window.library_collection.track_for_id(mapped.tracks[0].id).artwork_data,
                track_a.artwork_data,
            )
            self.assertEqual(window.playback_adapter.state.current_track.artwork_data, track_a.artwork_data)
            window.playback_adapter.set_queue((track_a, track_b, track_c))
            window.playback_adapter.play_track(track_a.id)
            window.navigation_adapter.set_route("immersive_now_playing")
            self.app.processEvents()
            shell = window.router.currentWidget()
            self.assertIsInstance(shell, ImmersivePlayerShell)
            shell.show_queue_panel()
            self.app.processEvents()
            panel = shell.queue_panel
            self.assertEqual(self._center_color(window.player_bar.artwork._artwork_pixmap), expected_a)
            self.assertEqual(self._center_color(shell.now_playing_page.artwork._artwork_pixmap), expected_a)
            self.assertEqual(self._center_color(panel.current_artwork._artwork_pixmap), expected_a)

            index = panel.view.model().index(0, 0)
            self.assertEqual(index.data(Qt.ItemDataRole.UserRole).id, track_b.id)
            image = QImage(300, 62, QImage.Format.Format_ARGB32)
            image.fill(QColor("#202522"))
            option = QStyleOptionViewItem()
            option.rect = QRect(0, 0, 300, 62)
            option.font = panel.view.font()
            painter = QPainter(image)
            panel.view.itemDelegate().paint(painter, option, index)
            painter.end()
            queue_artwork = image.pixelColor(35, 34).getRgb()
            self.assertEqual(queue_artwork, expected_b)

            theme = get_theme("dark")
            search_model = OnlineTrackModel((adapter._results[0],))
            search_index = search_model.index(0, int(OnlineColumn.TITLE))
            search_image = QImage(360, 48, QImage.Format.Format_ARGB32)
            search_image.fill(QColor("#202522"))
            search_option = QStyleOptionViewItem()
            search_option.rect = QRect(0, 0, 360, 48)
            search_option.font = panel.view.font()
            search_painter = QPainter(search_image)
            OnlineResultDelegate(theme).paint(search_painter, search_option, search_index)
            search_painter.end()
            self.assertEqual(search_image.pixelColor(26, 24).getRgb(), expected_a)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
