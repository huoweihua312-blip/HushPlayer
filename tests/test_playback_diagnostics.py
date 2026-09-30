from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.services.playback_diagnostics import PlaybackDiagnostics


class PlaybackDiagnosticsTests(unittest.TestCase):
    def test_records_bounded_json_event_and_redacts_urls(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            diagnostics = PlaybackDiagnostics(Path(root))
            diagnostics.record(
                "remote_track_state_received",
                identity="remote_abc123",
                detail="source https://example.invalid/audio.mp3?token=secret",
                removed_ids=["remote_old"],
            )

            path = Path(root) / "playback-diagnostics.log"
            event = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(event["prefix"], "[PLAYBACK-DIAG]")
        self.assertEqual(event["event"], "remote_track_state_received")
        self.assertEqual(event["identity"], "remote_abc123")
        self.assertNotIn("secret", event["detail"])
        self.assertEqual(event["removed_ids"], ["remote_old"])

    def test_disabled_diagnostics_do_not_create_a_file(self) -> None:
        diagnostics = PlaybackDiagnostics(None)
        diagnostics.record("ignored", value="safe")
        self.assertIsNone(diagnostics.path)


if __name__ == "__main__":
    unittest.main()
