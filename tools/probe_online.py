"""Manual probe: start the online runtime and run a live search.

Usage:  .venv\\Scripts\\python.exe tools\\probe_online.py [keyword]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from hushplayer.core import paths  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.online.client import OnlineSourceClient  # noqa: E402
from hushplayer.online.models import build_sources, tracks_from_items  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    setup_logging(console=True)
    app = QCoreApplication(sys.argv)
    keyword = sys.argv[1] if len(sys.argv) > 1 else "周杰伦"

    client = OnlineSourceClient()
    state = {"sources": [], "done": 0, "errors": 0}

    def finish(code: int = 0) -> None:
        client.stop()
        app.quit()
        sys.exit(code)

    def on_sources(response):
        if not response.get("ok"):
            print("listSources failed:", response.get("error"))
            state["errors"] += 1
            finish(1)
            return
        sources = build_sources(response.get("data") or [])
        state["sources"] = sources
        print(f"音源数量: {len(sources)}")
        for src in sources:
            caps = src.capabilities
            print(
                f"  - {src.name:<12} id={src.id:<28} platform={src.platform:<8} "
                f"play={caps.get('playback')} dl={caps.get('download')} "
                f"lyric={caps.get('lyrics')} problem={src.problem or '-'}"
            )
        playable = [s for s in sources if s.can_play]
        if not playable:
            print("没有可播放音源")
            finish(1)
            return
        target = playable[0]
        print(f"\n用 {target.name} 搜索: {keyword!r}")

        def on_search(response):
            if not response.get("ok"):
                print("search failed:", response.get("error"))
                finish(1)
                return
            items = response.get("data") or []
            tracks = tracks_from_items(items, source=target)
            print(f"结果条数: {len(tracks)}")
            for t in tracks[:8]:
                print(f"  {t.title} / {t.artist} / {t.album} / {t.duration_text} / {t.artwork_url[:60]}")
            if tracks:
                first = tracks[0]
                print("\nresolvePlayback...")

                def on_resolve(resp):
                    if not resp.get("ok"):
                        print("resolve failed:", resp.get("error"))
                        finish(1)
                        return
                    data = resp.get("data") or {}
                    print("  url:", str(data.get("url"))[:110])
                    print("  mime:", data.get("mimeType"), "quality:", data.get("quality"))
                    print("  headers:", sorted((data.get("headers") or {}).keys()))
                    print("  expiresAt:", data.get("expiresAt"))
                    finish(0)

                from hushplayer.online.models import runtime_track

                client.resolve_playback(
                    first.source_id, runtime_track(first), on_resolve, quality="standard"
                )
            else:
                finish(0)

        client.search(target.id, keyword, 1, on_search)

    QTimer.singleShot(100, lambda: client.request("listSources", {}, on_sources))
    QTimer.singleShot(90000, lambda: (print("TIMEOUT"), finish(2)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
