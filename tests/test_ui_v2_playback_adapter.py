from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.playback_state import PlaybackState, RepeatMode


class UiV2PlaybackAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.tracks = [
            track
            for track in create_mock_tracks(80)
            if not track.is_missing and track.duration_ms is not None
        ][:6]
        self.adapter = PlaybackAdapter(timer_enabled=False)
        self.adapter.set_queue(self.tracks)

    def test_play_pause_previous_next_and_manual_progress(self) -> None:
        self.adapter.play_track(self.tracks[1].id)
        self.assertEqual(self.adapter.state.current_track.id, self.tracks[1].id)
        self.assertTrue(self.adapter.state.is_playing)
        self.adapter.pause()
        self.assertFalse(self.adapter.state.is_playing)
        self.adapter.play()
        self.adapter.advance_for_test(1_234)
        self.assertEqual(self.adapter.state.position_ms, 1_234)
        self.adapter.play_previous()
        self.assertEqual(self.adapter.state.current_track.id, self.tracks[0].id)
        self.adapter.play_next()
        self.assertEqual(self.adapter.state.current_track.id, self.tracks[1].id)

    def test_seek_volume_favorite_shuffle_and_repeat(self) -> None:
        self.adapter.play_track(self.tracks[0].id)
        duration = self.adapter.state.duration_ms
        self.adapter.seek(duration + 1)
        self.assertEqual(self.adapter.state.position_ms, duration)
        self.adapter.seek(-10)
        self.assertEqual(self.adapter.state.position_ms, 0)
        self.adapter.set_volume(140)
        self.assertEqual(self.adapter.state.volume, 100)
        self.adapter.set_volume(-1)
        self.assertEqual(self.adapter.state.volume, 0)
        previous_favorite = self.adapter.state.is_favorite
        self.adapter.toggle_favorite()
        self.assertNotEqual(self.adapter.state.is_favorite, previous_favorite)
        self.adapter.toggle_shuffle()
        self.assertTrue(self.adapter.state.shuffle_enabled)
        self.assertEqual(self.adapter.state.repeat_mode, RepeatMode.ALL)
        self.adapter.cycle_repeat_mode()
        self.assertEqual(self.adapter.state.repeat_mode, RepeatMode.ONE)
        self.adapter.cycle_repeat_mode()
        self.assertEqual(self.adapter.state.repeat_mode, RepeatMode.OFF)

    def test_track_end_moves_to_next_and_clear_resets_everything(self) -> None:
        self.adapter.play_track(self.tracks[0].id)
        self.adapter.advance_for_test(self.adapter.state.duration_ms)
        self.assertEqual(self.adapter.state.current_track.id, self.tracks[1].id)
        self.adapter.set_volume(18)
        self.adapter.toggle_shuffle()
        self.adapter.clear()
        self.assertEqual(self.adapter.state, PlaybackState())


if __name__ == "__main__":
    unittest.main()
