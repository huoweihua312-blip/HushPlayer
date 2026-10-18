"""Focused probe: check whether flaky sources work with other keywords/tracks."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from hushplayer.core import paths  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.online.client import OnlineSourceClient  # noqa: E402
from hushplayer.online.models import build_sources, runtime_track, tracks_from_items  # noqa: E402

KEYWORDS = ["晴天", "告白气球", "Taylor Swift", "孤勇者"]
TARGETS = ["qq", "kg", "xiaomi"]


def main() -> int:
    paths.ensure_dirs()
    setup_logging(console=False)
    app = QCoreApplication(sys.argv)
    client = OnlineSourceClient()
    jobs: list[tuple[str, str]] = []

    def finish() -> None:
        client.stop()
        app.quit()

    def run_next() -> None:
        if not jobs:
            finish()
            return
        source_id, keyword = jobs.pop(0)
        def on_search(response) -> None:
            if not response.get("ok"):
                print(f"{source_id[:20]} {keyword!r}: SEARCH FAIL {response.get('error')}")
                run_next()
                return
            tracks = tracks_from_items(response.get("data") or [])
            print(f"{source_id[:20]} {keyword!r}: {len(tracks)} items")
            if not tracks:
                run_next()
                return
            track = tracks[0]
            print(f"    -> {track.title} / {track.artist} / {track.duration_text}")

            def on_play(resp) -> None:
                if not resp.get("ok"):
                    print(f"    PLAY FAIL: {str(resp.get('error'))[:100]}")
                    run_next()
                    return
                data = resp.get("data") or {}
                print(f"    PLAY OK {str(data.get('url'))[:90]} headers={sorted((data.get('headers') or {}).keys())}")
                run_next()

            client.resolve_playback(track.source_id, runtime_track(track), on_play)

        client.search(source_id, keyword, 1, on_search)

    def on_sources(response) -> None:
        sources = {s.id: s for s in build_sources(response.get("data") or [])}
        for source in sources.values():
            platform = (source.platform or "").lower()
            if platform in TARGETS:
                for keyword in KEYWORDS:
                    jobs.append((source.id, keyword))
        print(f"jobs={len(jobs)}")
        run_next()

    QTimer.singleShot(100, lambda: client.request("listSources", {}, on_sources))
    QTimer.singleShot(240000, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
