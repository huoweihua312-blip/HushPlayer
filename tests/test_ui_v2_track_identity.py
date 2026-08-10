from __future__ import annotations

import os
import unittest
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import Track
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.theme.tokens import LIGHT_THEME
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.track_display import (
    format_track_metadata,
    present_track_identity_values,
)


def _track(
    *,
    title: str = "夜航",
    artist: str = "林澈",
    album: str = "夜间选集",
    availability: str = "available",
) -> Track:
    return Track(
        id="identity-test",
        title=title,
        artist=artist,
        album=album,
        duration_ms=180_000,
        source_id="fixture",
        source_name="Fixture Source",
        source_type="online",
        added_at=datetime(2026, 8, 9),
        is_favorite=False,
        is_missing=availability != "available",
        is_loading=False,
        artwork_path=None,
        stable_identity="fixture:identity-test",
        availability=availability,
        remote_identity="fixture:identity-test",
        remote_track_id="identity-test",
    )


class TrackIdentityPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_metadata_combinations_use_only_artist_and_album(self) -> None:
        self.assertEqual(format_track_metadata("123", "专辑"), "123 · 专辑")
        self.assertEqual(format_track_metadata("123", ""), "123")
        self.assertEqual(format_track_metadata("", "专辑"), "专辑")
        self.assertEqual(format_track_metadata("", ""), "未知艺人")

    def test_unavailable_status_is_independent_from_metadata(self) -> None:
        identity = present_track_identity_values(
            "Умри если меня не любишь",
            "123",
            "",
            is_online=True,
            availability="unavailable",
            playback_status="unavailable",
            playback_detail="暂时无法播放这首在线歌曲",
        )
        self.assertEqual(identity.title, "Умри если меня не любишь")
        self.assertEqual(identity.metadata, "123")
        self.assertEqual(identity.availability.label, "暂不可播放")
        self.assertEqual(identity.availability.tooltip, "暂时无法播放这首在线歌曲")
        self.assertNotIn("暂时无法播放", identity.metadata)

    def test_resolving_and_error_have_separate_status_text(self) -> None:
        for status, label in (("resolving", "准备播放"), ("buffering", "缓冲中"), ("error", "播放失败")):
            identity = present_track_identity_values(
                "长标题用于 Unicode elide 验证",
                "Artist",
                "Album",
                is_online=True,
                playback_status=status,
                playback_detail="状态说明",
            )
            self.assertEqual(identity.metadata, "Artist · Album")
            self.assertEqual(identity.availability.label, label)
            self.assertEqual(identity.availability.tooltip, "状态说明")

    def test_elided_label_uses_actual_width_and_keeps_full_tooltip(self) -> None:
        label = ElidedLabel()
        label.setFont(label.font())
        label.setFixedWidth(220)
        full_title = "Умри если меня не любишь · 长标题用于高分辨率显示验证"
        label.set_full_text(full_title)
        label.show()
        self.app.processEvents()
        expected = QFontMetrics(label.font()).elidedText(
            full_title,
            Qt.TextElideMode.ElideRight,
            label.contentsRect().width(),
        )
        self.assertEqual(label.text(), expected)
        self.assertEqual(label.full_text, full_title)
        self.assertEqual(label.toolTip(), full_title)

    def test_player_bar_status_does_not_pollute_metadata(self) -> None:
        adapter = PlaybackAdapter(timer_enabled=False)
        bar = PlayerBar(adapter, LIGHT_THEME)
        track = _track(artist="123", album="")
        adapter.set_queue((track,))
        adapter.play_track(track.id)
        bar._on_playback_status_changed("unavailable", "暂时无法播放这首在线歌曲")
        self.assertEqual(bar.artist_label.full_text, "123")
        self.assertIn("暂时无法播放这首在线歌曲", bar.artist_label.toolTip())
        self.assertNotIn("暂时无法播放", bar.artist_label.full_text)
        bar.deleteLater()
        adapter.deleteLater()

    def test_player_bar_identity_width_expands_with_shell_width(self) -> None:
        adapter = PlaybackAdapter(timer_enabled=False)
        bar = PlayerBar(adapter, LIGHT_THEME)
        widths = []
        for width in (900, 1200, 1600):
            bar.resize(width, LIGHT_THEME.metrics.player_bar_height)
            bar.set_compact(width < 1000)
            self.app.processEvents()
            widths.append(bar.metadata.width())
        self.assertGreaterEqual(widths[0], 118)
        self.assertGreaterEqual(widths[1], widths[0])
        self.assertGreaterEqual(widths[2], widths[1])
        bar.deleteLater()
        adapter.deleteLater()

    def test_online_track_conversion_preserves_availability_for_presentation(self) -> None:
        remote = OnlineTrack(
            id="online:fixture:blocked",
            source_id="fixture",
            source_name="Fixture Source",
            title="在线歌曲",
            artist="123",
            album="",
            duration_ms=None,
            artwork_key="fixture",
            quality="标准",
            stable_identity="fixture:blocked",
            is_favorite=False,
            is_downloaded=False,
            is_cached=False,
            availability="unavailable",
            explicit=False,
            result_rank=0,
        )
        self.assertEqual(remote.as_track().availability, "unavailable")


if __name__ == "__main__":
    unittest.main()
