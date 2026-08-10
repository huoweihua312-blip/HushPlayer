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

from app.ui_v2.adapters.navigation_adapter import NavigationAdapter


class UiV2NavigationAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.adapter = NavigationAdapter()

    def test_static_routes_change_current_route(self) -> None:
        routes = {item.route_id for item in self.adapter.items()}
        self.assertIn("library", routes)
        self.assertIn("online_search", routes)
        changed = []
        self.adapter.route_changed.connect(changed.append)
        self.adapter.set_route("albums")
        self.assertEqual(self.adapter.route, "albums")
        self.assertEqual(changed, ["albums"])

    def test_mock_playlist_create_rename_delete_and_current_route(self) -> None:
        original_count = len(self.adapter.playlists())
        playlist = self.adapter.create_playlist("测试歌单")
        self.assertEqual(len(self.adapter.playlists()), original_count + 1)
        self.adapter.set_route(f"playlist:{playlist.id}")
        self.assertEqual(self.adapter.current_playlist_id, playlist.id)
        self.assertTrue(self.adapter.rename_playlist(playlist.id, "重命名歌单"))
        self.assertIn("重命名歌单", [item.name for item in self.adapter.playlists()])
        self.assertTrue(self.adapter.delete_playlist(playlist.id))
        self.assertEqual(self.adapter.route, "library")
        self.assertEqual(self.adapter.current_playlist_id, "")

    def test_unknown_playlist_route_falls_back_to_library(self) -> None:
        self.adapter.set_route("playlist:does-not-exist")
        self.assertEqual(self.adapter.route, "library")


if __name__ == "__main__":
    unittest.main()
