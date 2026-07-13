from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.remote_track_store import RemoteTrackStore, RemoteTrackStoreError


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hushplayer_remote_tracks_") as temp_dir:
        root = Path(temp_dir)
        store = RemoteTrackStore(root / "remote_tracks.json")
        track = {
            "sourceId": "custom_fixture",
            "sourceUrl": "https://example.invalid/open.js",
            "id": "track-1",
            "title": "Fixture",
            "artist": "Artist",
            "album": "Album",
            "raw": {
                "id": "track-1",
                "url": "https://temporary.invalid/audio.mp3",
                "playbackUrl": "https://temporary.invalid/expiring.mp3",
            },
        }
        stable_id, record = RemoteTrackStore.build_record(track, track["sourceUrl"])
        assert stable_id == RemoteTrackStore.stable_id_for_track(track)
        assert "url" not in record["raw"]
        assert "playbackUrl" not in record["raw"]
        store.save_tracks({stable_id: record})
        assert store.load_tracks()[stable_id]["title"] == "Fixture"
        resumed_id, _ = RemoteTrackStore.build_record(
            {"id": "track-1", "title": "Fixture"},
            existing=record,
        )
        assert resumed_id == stable_id

        local_path = root / "fixture.wav"
        local_path.write_bytes(b"RIFF")
        record["local_path"] = str(local_path)
        downloaded = RemoteTrackStore.to_song_data(stable_id, record, source_available=True)
        assert downloaded["onlineStatus"] == "已下载"
        assert downloaded["path"] == str(local_path.resolve())
        local_path.unlink()
        fallback = RemoteTrackStore.to_song_data(stable_id, record, source_available=True)
        assert fallback["onlineStatus"] == "在线"
        unavailable = RemoteTrackStore.to_song_data(stable_id, record, source_available=False)
        assert unavailable["onlineStatus"] == "来源不可用"

        damaged_path = root / "damaged.json"
        damaged_path.write_text("{broken", encoding="utf-8")
        try:
            RemoteTrackStore(damaged_path).load_tracks()
        except RemoteTrackStoreError:
            pass
        else:
            raise AssertionError("damaged remote track data did not fail safely")
        assert damaged_path.read_text(encoding="utf-8") == "{broken"

        document = json.loads((root / "remote_tracks.json").read_text(encoding="utf-8"))
        assert document["version"] == 1
        assert list(document["tracks"]) == [stable_id]

    print("remote track store smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
