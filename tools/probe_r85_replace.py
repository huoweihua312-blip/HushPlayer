"""Measure the replace-source search against the real runtime."""

from __future__ import annotations

import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(ROOT / "artifacts" / "qa" / "r85" / "data"))
os.environ.setdefault("HUSHPLAYER_NO_CLOSE_PROMPT", "1")
os.environ.setdefault("HUSHPLAYER_MUTEX_SUFFIX", "r85")
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.model.track import Track  # noqa: E402
from hushplayer.online import models as online_models  # noqa: E402
from hushplayer.services.source_replace import SourceReplaceSearch  # noqa: E402


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    hush = HushApp(app)
    hush.start()
    client = hush.client
    client.ensure_started()

    # wait for the runtime to report its sources
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not client.sources:
        app.processEvents()
        time.sleep(0.05)
    sources = [s for s in online_models.build_sources(client.sources) if s.can_play]
    print("sources", len(sources))
    if not sources:
        hush.shutdown()
        return 1

    track = Track(
        id="online:probe:demo",
        kind="online",
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        source_id=sources[0].id,
        source_name=sources[0].label,
        remote_id="demo",
    )

    loop = QEventLoop()
    result: dict = {}

    def done(candidates, errors) -> None:
        result["candidates"] = candidates
        result["errors"] = errors
        result["elapsed"] = time.monotonic() - started
        loop.quit()

    started = time.monotonic()
    search = SourceReplaceSearch(client, track, sources, done, timeout_ms=12_000)
    search.start()
    QTimer.singleShot(30_000, loop.quit)
    loop.exec()

    candidates = result.get("candidates", [])
    print(
        "elapsed=%.2fs candidates=%d errors=%d"
        % (result.get("elapsed", -1), len(candidates), len(result.get("errors", [])))
    )
    for cand in candidates[:5]:
        print(" ", cand.source_name, cand.title, cand.artist, cand.score)
    hush.shutdown()
    return 0 if candidates else 2


if __name__ == "__main__":
    raise SystemExit(main())
