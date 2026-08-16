from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.remote_track_store import RemoteTrackStore
from app.services.source_registry import SourceRegistryError, SourceRegistryManager


SOURCE_ONE_URL = "https://example.invalid/source_one.js"
SOURCE_TWO_URL = "https://example.invalid/source_two.json"
SOURCE_ONE = (
    b"module.exports = { platform: 'Open One', search: async () => [], "
    b"getMediaSource: async () => ({url: 'https://example.invalid/audio.ogg'}) };"
)
SOURCE_TWO = b'{"name":"Open Two","url":"https://example.invalid/audio-two.ogg"}'


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hushplayer_sources_") as temp_dir:
        registry = SourceRegistryManager(Path(temp_dir))
        first_candidate = registry.stage_bytes(
            SOURCE_ONE,
            "source_one.js",
            source_url=SOURCE_ONE_URL,
            content_policy="open",
            user_installed=True,
        )
        second_candidate = registry.stage_bytes(
            SOURCE_TWO,
            "source_two.json",
            source_url=SOURCE_TWO_URL,
            content_policy="open",
            user_installed=True,
        )
        first = registry.install_candidate(first_candidate, enabled=True)
        second = registry.install_candidate(second_candidate, enabled=False)
        assert len(registry.list_sources()) == 2
        assert registry.find_by_source_url(SOURCE_ONE_URL)["id"] == first["id"]
        assert registry.get_source(second["id"])["enabled"] is False

        restarted = SourceRegistryManager(Path(temp_dir))
        assert restarted.find_by_source_url(SOURCE_ONE_URL)["id"] == first["id"]
        assert restarted.set_name(first["id"], "Renamed Open Source")["name"] == "Renamed Open Source"
        assert restarted.set_enabled(first["id"], False)["enabled"] is False
        assert restarted.set_enabled(first["id"], True)["enabled"] is True

        unchanged = restarted.stage_bytes(
            SOURCE_ONE,
            "source_one.js",
            source_url=SOURCE_ONE_URL,
            content_policy="open",
            user_installed=True,
        )
        try:
            restarted.install_candidate(unchanged, enabled=True)
        except SourceRegistryError as error:
            assert "相同" in str(error)
        else:
            raise AssertionError("duplicate source installation did not fail")

        changed = restarted.stage_bytes(
            SOURCE_ONE + b"\n// fixture update",
            "source_one.js",
            source_url=SOURCE_ONE_URL,
            content_policy="open",
            user_installed=True,
        )
        updated = restarted.update_candidate(first["id"], changed)
        assert updated["id"] == first["id"]
        assert updated["sha256"] != first["sha256"]
        assert Path(updated["backupPath"]).is_file()

        removed = restarted.remove_source(first["id"])
        assert restarted.get_source(first["id"]) is None
        assert Path(removed["backupPath"]).is_file()
        assert restarted.get_source(second["id"]) is not None

        stable_id, remote_record = RemoteTrackStore.build_record(
            {
                "sourceId": first["id"],
                "id": "removed-source-track",
                "title": "Retained fixture",
                "artist": "Artist",
                "album": "Album",
            },
            source_url=SOURCE_ONE_URL,
        )
        unavailable = RemoteTrackStore.to_song_data(
            stable_id,
            remote_record,
            source_available=False,
        )
        assert unavailable["onlineStatus"] == "来源不可用"

    print("custom source management smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
