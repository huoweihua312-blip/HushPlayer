from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.playback_session_store import PlaybackSession, PlaybackSessionStore


class PlaybackSessionStoreTests(unittest.TestCase):
    def test_round_trip_normalizes_duplicate_and_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-session-") as directory:
            path = Path(directory) / "playback_session.json"
            store = PlaybackSessionStore(path)
            session = PlaybackSession.create(
                current_identity=" local:first ",
                queue_identities=("local:first", "", "local:first", "local:second"),
                position_ms="4200",
                route="lyrics",
            )

            self.assertTrue(store.save(session))
            loaded = store.load()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.current_identity, "local:first")
            self.assertEqual(loaded.queue_identities, ("local:first", "local:second"))
            self.assertEqual(loaded.position_ms, 4_200)
            self.assertEqual(loaded.route, "lyrics")
            self.assertFalse(tuple(path.parent.glob("*.tmp")))

    def test_missing_corrupt_and_unknown_versions_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-session-") as directory:
            path = Path(directory) / "playback_session.json"
            store = PlaybackSessionStore(path)
            self.assertIsNone(store.load())

            path.write_text("{broken", encoding="utf-8")
            self.assertIsNone(store.load())

            path.write_text('{"version": 99}', encoding="utf-8")
            self.assertIsNone(store.load())


if __name__ == "__main__":
    unittest.main()
