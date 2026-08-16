"""Smoke coverage for the current V2 artwork and lyrics media services."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.services.online_artwork_service import OnlineArtworkService
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.models.track import Track


def _track(path: Path) -> Track:
    return Track(
        id="fixture-track",
        title="Fixture Track",
        artist="Fixture Artist",
        album="Fixture Album",
        duration_ms=10_000,
        source_id="local",
        source_name="本地音乐",
        source_type="local",
        added_at=datetime(2026, 1, 1),
        is_favorite=False,
        is_missing=False,
        is_loading=False,
        artwork_path=None,
        stable_identity="local:fixture-track",
        local_path=str(path),
    )


def _png_bytes() -> bytes:
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("#4c8dff"))
    payload = QByteArray()
    buffer = QBuffer(payload)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    return bytes(payload)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="hushplayer_media_services_") as temp_dir:
        root = Path(temp_dir)
        audio = root / "fixture.mp3"
        audio.write_bytes(b"fixture")
        lyrics = LyricsAdapter()
        lyrics._apply_lyrics_text(
            _track(audio),
            "[00:00.00]First line\n[00:05.00]Second line\n",
            "local",
        )
        assert lyrics.state.phase == "ready"
        assert lyrics.document is not None
        assert [line.text for line in lyrics.document.lines] == ["First line", "Second line"]
        lyrics.shutdown()

        artwork_url = "https://example.invalid/cover.png"
        digest = hashlib.sha256(artwork_url.encode("utf-8")).hexdigest()
        cache_dir = root / "artwork-cache"
        (cache_dir / "online").mkdir(parents=True)
        (cache_dir / "online" / f"{digest}.img").write_bytes(_png_bytes())
        artwork = OnlineArtworkService(cache_dir)
        received: list[tuple[int, str, bytes]] = []
        artwork.imageReady.connect(lambda generation, key, data: received.append((generation, key, bytes(data))))
        generation = artwork.request("fixture-track", artwork_url)
        app.processEvents()
        assert received and received[0][0] == generation
        assert received[0][1] == "fixture-track"
        assert received[0][2]
        artwork.cancel()

    print("media service lifecycle smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
