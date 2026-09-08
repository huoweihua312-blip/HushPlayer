"""Regression checks for bounded covers, safe reads, and live list updates."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from app.services.library_repository import LibraryRepository
from app.ui_v2.adapters.legacy_settings_bridge import (
    LegacySettingsBridge, SettingsBridgeError, load_settings_document, write_settings_document,
)
from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter, PlaylistTrackAdapter
from app.ui_v2.adapters.real_library_adapter import RealLibraryAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track_table_model import PLAYING_ROLE, TrackColumn
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from app.ui_v2.widgets.pixmap_cache import PixmapCache
from app.ui_v2.widgets.track_table import TrackTable


class StabilityOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_damaged_settings_cannot_be_overwritten_by_any_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for raw in (b"{", b"[]", b"null", b"\xff", b"[" * 2000 + b"]" * 2000):
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    bridge = LegacySettingsBridge(path)
                    with self.assertLogs(level="WARNING"):
                        snapshot = bridge.read_snapshot()
                    failures = []
                    bridge.save_failed.connect(failures.append)
                    with self.assertRaises(SettingsBridgeError):
                        bridge.save_snapshot(snapshot.with_updates({"appearance_mode": "light"}))
                    with self.assertRaises(SettingsBridgeError):
                        write_settings_document(path, {"volume": 70})
                    self.assertTrue(failures)
                    self.assertEqual(path.read_bytes(), raw)
                    self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_settings_recheck_at_save_and_recover_after_external_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            bridge = LegacySettingsBridge(path)
            bridge.save_snapshot(bridge.read_snapshot().with_updates({"legacy_key": {"keep": 1}}))
            snapshot = bridge.read_snapshot()
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(SettingsBridgeError):
                bridge.save_snapshot(snapshot)
            path.write_text(json.dumps(snapshot.to_dict()), encoding="utf-8")
            bridge.save_snapshot(bridge.read_snapshot().with_updates({"appearance_mode": "light"}))
            self.assertEqual(load_settings_document(path)["legacy_key"], {"keep": 1})

    def test_unreadable_settings_are_protected_and_defaults_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            first = load_settings_document(path)
            first["music_scan_folders"].append("memory-only")
            self.assertEqual(load_settings_document(path)["music_scan_folders"], [])
            with patch.object(Path, "read_text", side_effect=PermissionError("fixture")):
                with self.assertRaises(SettingsBridgeError):
                    write_settings_document(path, {})
            self.assertFalse(path.exists())

    def test_bad_library_and_stats_entries_do_not_discard_valid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "fixture.mp3"
            audio.write_bytes(b"fixture")
            library = root / "library.json"
            stats = root / "stats.json"
            library.write_text(json.dumps([
                {"path": str(audio), "title": "正常一", "extra": 7},
                "bad-record", {"path": []}, {"path": 123},
                {"path": str(audio), "added_at": "bad"},
                {"path": str(audio), "title": "正常二", "duration": "NaN"},
            ]), encoding="utf-8")
            stats.write_text(json.dumps({
                str(audio): {"play_count": 8},
                str(root / "bad.mp3"): {"play_count": "bad"},
                str(root / "also-bad.mp3"): [],
            }), encoding="utf-8")
            before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (library, stats)}
            repository = LibraryRepository(library, root / "playlists.json", stats)
            with self.assertLogs(level="WARNING"):
                snapshot = repository.load_snapshot()
            self.assertEqual(snapshot.library.status, "loaded")
            self.assertEqual([track["title"] for track in snapshot.library.tracks], ["正常一", "正常二"])
            self.assertEqual(snapshot.library.tracks[0]["extra"], 7)
            self.assertIn("3 条", snapshot.library.warning)
            self.assertEqual(snapshot.song_stats[str(audio.resolve())]["play_count"], 8)
            data = RealLibraryAdapter.map_snapshot(snapshot, {})
            self.assertEqual(len(data.tracks), 2)
            self.assertIsNone(data.tracks[1].duration_ms)
            self.assertEqual(data.load_warning, snapshot.library.warning)
            self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before})

    def test_corrupt_library_document_still_reports_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "library.json"
            repository = LibraryRepository(path, root / "playlists.json", root / "stats.json")
            for content in ("[", '{"wrong": 1}'):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(repository.load_snapshot().library.status, "error")
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_pixmap_budget_lru_replacement_and_oversized_images(self) -> None:
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor("red"))
        cost = 100 * ((pixmap.depth() + 7) // 8)
        cache = PixmapCache(cost * 2, 2)
        cache.put("a", pixmap)
        cache.put("b", pixmap)
        self.assertIsNotNone(cache.get("a"))
        cache.put("c", pixmap)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.used_bytes, cost * 2)
        cache.put("a", pixmap)
        self.assertEqual(cache.used_bytes, cost * 2)
        cache.put("huge", QPixmap(100, 100))
        self.assertIsNone(cache.get("huge"))
        self.assertIsNotNone(cache.get("a"))
        cache.clear()
        self.assertEqual(cache.used_bytes, 0)

    def test_replacing_cover_at_same_path_refreshes_scaled_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cover.png"
            pixmap = QPixmap(20, 20)
            pixmap.fill(QColor("red"))
            self.assertTrue(pixmap.save(str(path)))
            track = replace(create_mock_tracks(1)[0], artwork_path=str(path), artwork_data=b"")
            first = artwork_pixmap_for_track(track, 10, 10)
            stamp = path.stat().st_mtime_ns
            pixmap.fill(QColor("blue"))
            self.assertTrue(pixmap.save(str(path)))
            os.utime(path, ns=(stamp + 2_000_000_000, stamp + 2_000_000_000))
            second = artwork_pixmap_for_track(track, 10, 10)
            self.assertEqual(first.toImage().pixelColor(0, 0), QColor("red"))
            self.assertEqual(second.toImage().pixelColor(0, 0), QColor("blue"))

    def test_scaled_cover_hit_does_not_decode_an_evicted_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cover.png"
            pixmap = QPixmap(20, 20)
            pixmap.fill(QColor("green"))
            self.assertTrue(pixmap.save(str(path)))
            track = replace(create_mock_tracks(1)[0], artwork_path=str(path), artwork_data=b"")
            with patch("app.ui_v2.widgets.artwork_thumbnail._ARTWORK_SOURCE_CACHE", PixmapCache(1, 1)):
                first = artwork_pixmap_for_track(track, 10, 10)
                with patch.object(QPixmap, "load", side_effect=AssertionError("unexpected decode")):
                    second = artwork_pixmap_for_track(track, 10, 10)
                self.assertEqual(first.cacheKey(), second.cacheKey())

    def test_runtime_sort_preserves_selection_and_paused_playback(self) -> None:
        tracks = [replace(track, duration_ms=index * 1000 + 1000) for index, track in enumerate(create_mock_tracks(3))]
        adapter = LibraryAdapter(tracks)
        adapter.set_sort(TrackColumn.DURATION, Qt.SortOrder.AscendingOrder)
        table = TrackTable(adapter, get_theme("dark"))
        try:
            table.selectRow(0)
            adapter.set_playing_track(tracks[1].id)
            table.set_playback_state(tracks[1].id, False)
            plays = []
            table.play_requested.connect(plays.append)
            adapter.collection.update_runtime_track(replace(tracks[0], duration_ms=9000))
            self.assertEqual([track.duration_ms for track in adapter.tracks()], [2000, 3000, 9000])
            self.assertEqual(table.model.track_at(table.currentIndex().row()).id, tracks[0].id)
            self.assertTrue(table.selectionModel().isSelected(table.currentIndex()))
            playing_index = table.model.index_for_track(tracks[1].id)
            self.assertTrue(table.model.data(playing_index, PLAYING_ROLE))
            self.assertFalse(table.model._playing_active)
            self.assertEqual(plays, [])
            self.assertEqual(adapter.playing_track_id, tracks[1].id)
        finally:
            table.deleteLater()
            self.app.processEvents()

    def test_search_cache_invalidates_on_update_and_collection_reload(self) -> None:
        track = replace(create_mock_tracks(1)[0], title="OldTitle", artist="Artist", album="Album")
        adapter = LibraryAdapter([track])
        adapter.set_query("oldtitle")
        self.assertEqual(len(adapter.tracks()), 1)
        adapter.collection.update_runtime_track(replace(track, title="NewTitle"))
        self.assertEqual(adapter.tracks(), ())
        adapter.set_query("NEWTITLE")
        self.assertEqual(len(adapter.tracks()), 1)
        adapter.collection.set_tracks([track])
        self.assertEqual(adapter.tracks(), ())

    def test_unrelated_runtime_update_does_not_reset_table(self) -> None:
        adapter = LibraryAdapter(create_mock_tracks(3))
        resets, updates = [], []
        adapter.tracks_reset.connect(resets.append)
        adapter.track_updated.connect(updates.append)
        track = adapter.tracks()[0]
        adapter.collection.update_runtime_track(replace(track, artwork_key="new-cover"))
        self.assertEqual(resets, [])
        self.assertEqual(len(updates), 1)

    def test_playlist_source_order_keeps_update_index_current(self) -> None:
        adapter = LibraryAdapter(create_mock_tracks(3))
        playlists = PlaylistAdapter(adapter.collection)
        playlist = playlists.create_playlist("fixture")
        playlists.add_tracks(playlist.id, [track.id for track in adapter.tracks()])
        view = PlaylistTrackAdapter(adapter.collection, playlists)
        view._preserve_source_order = True
        view.set_playlist(playlist.id)
        before = [track.id for track in view.tracks()]
        target = view.tracks()[0]
        adapter.collection.update_runtime_track(replace(target, artwork_key="new-cover"))
        self.assertEqual([track.id for track in view.tracks()], before)
        self.assertEqual(view.tracks()[0].artwork_key, "new-cover")


if __name__ == "__main__":
    unittest.main()
