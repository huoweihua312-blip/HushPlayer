"""Probe every registered source: search, lyrics, playback, download.

Usage:  .venv\\Scripts\\python.exe tools\\probe_sources.py [keyword]
Results are printed as a compact table and written to tools/_source_probe.txt.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from hushplayer.core import paths  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.online.client import OnlineSourceClient  # noqa: E402
from hushplayer.online.models import build_sources, runtime_track, tracks_from_items  # noqa: E402

OUT: list[str] = []


def out(text: str) -> None:
    print(text)
    OUT.append(text)


def main() -> int:
    paths.ensure_dirs()
    setup_logging(console=False)
    app = QCoreApplication(sys.argv)
    keyword = sys.argv[1] if len(sys.argv) > 1 else "周杰伦 晴天"
    client = OnlineSourceClient()
    report: dict[str, dict] = {}

    def finish(code: int = 0) -> None:
        client.stop()
        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "_source_probe.txt"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("\n".join(OUT))
        app.quit()
        sys.exit(code)

    def step_search(sources, index: int) -> None:
        if index >= len(sources):
            summarise(sources)
            return
        src = sources[index]
        started = time.monotonic()
        info = report.setdefault(src.id, {"name": src.name, "platform": src.platform})

        def done(response) -> None:
            elapsed = time.monotonic() - started
            if not response.get("ok"):
                info["search"] = f"FAIL: {response.get('error')}"
                out(f"[{src.name}] 搜索失败 {elapsed:.1f}s: {response.get('error')}")
                step_search(sources, index + 1)
                return
            tracks = tracks_from_items(response.get("data") or [], source=src)
            info["search"] = f"ok {len(tracks)} items {elapsed:.1f}s"
            if not tracks:
                out(f"[{src.name}] 搜索无结果 {elapsed:.1f}s")
                step_search(sources, index + 1)
                return
            sample = tracks[0]
            info["sample"] = f"{sample.title} / {sample.artist} / {sample.duration_text}"
            info["cover"] = bool(sample.artwork_url)
            out(f"[{src.name}] 搜索 {len(tracks)} 首 {elapsed:.1f}s -> {info['sample']}")
            probe_lyric(src, sample, lambda: probe_playback(src, sample, lambda: step_search(sources, index + 1)))

        client.search(src.id, keyword, 1, done)

    def probe_lyric(src, track, next_step) -> None:
        started = time.monotonic()

        def done(response) -> None:
            elapsed = time.monotonic() - started
            info = report[src.id]
            if not response.get("ok"):
                info["lyric"] = f"FAIL: {response.get('error')}"
                out(f"    歌词失败 {elapsed:.1f}s: {response.get('error')}")
                next_step()
                return
            data = response.get("data") or {}
            raw = str(data.get("rawLrc") or "")
            timed = data.get("hasTimedLyrics") or data.get("timed")
            info["lyric"] = f"ok {len(raw)} chars {elapsed:.1f}s"
            head = raw.splitlines()[0][:70] if raw else ""
            out(f"    歌词 {len(raw)} 字符 {elapsed:.1f}s timed={timed} :: {head}")
            if not raw:
                out(f"    (歌词键: {sorted(data.keys())})")
            next_step()

        client.get_lyric(src.id, track.raw, done)

    def probe_playback(src, track, next_step) -> None:
        started = time.monotonic()

        def done(response) -> None:
            elapsed = time.monotonic() - started
            info = report[src.id]
            if not response.get("ok"):
                info["playback"] = f"FAIL: {response.get('error')}"
                out(f"    播放解析失败 {elapsed:.1f}s: {str(response.get('error'))[:120]}")
                next_step()
                return
            data = response.get("data") or {}
            url = str(data.get("url") or "")
            info["playback"] = f"ok {elapsed:.1f}s {data.get('quality')}"
            out(f"    播放 {elapsed:.1f}s {str(data.get('url'))[:80]}")
            probe_download(src, track, next_step)

        client.resolve_playback(src.id, runtime_track(track), done)

    def probe_download(src, track, next_step) -> None:
        started = time.monotonic()

        def done(response) -> None:
            elapsed = time.monotonic() - started
            info = report[src.id]
            if not response.get("ok"):
                info["download"] = f"FAIL: {str(response.get('error'))[:80]}"
                out(f"    下载解析失败 {elapsed:.1f}s: {str(response.get('error'))[:100]}")
                next_step()
                return
            data = response.get("data") or {}
            info["download"] = f"ok {elapsed:.1f}s"
            info["filename"] = str(data.get("filename") or "")
            out(f"    下载 {elapsed:.1f}s file={info['filename']}")
            next_step()

        client.resolve_download(src.id, runtime_track(track), done)

    def on_sources(response) -> None:
        if not response.get("ok"):
            out(f"listSources 失败: {response.get('error')}")
            finish(1)
            return
        sources = [s for s in build_sources(response.get("data") or []) if s.enabled]
        out(f"关键词: {keyword!r}  音源: {len(sources)}")
        step_search(sources, 0)

    def summarise(sources) -> None:
        out("\n==== 汇总 ====")
        for src in sources:
            info = report.get(src.id, {})
            caps = src.capabilities
            out(
                f"{src.name:<10} play={str(caps.get('playback')):<5} dl={str(caps.get('download')):<5} "
                f"| 搜索: {info.get('search','-')}"
            )
            out(f"{'':<10} 歌词: {info.get('lyric','-')}")
            out(f"{'':<10} 播放: {info.get('playback','-')}")
            out(f"{'':<10} 下载: {info.get('download','-')}")
        finish(0)

    QTimer.singleShot(100, lambda: client.request("listSources", {}, on_sources))
    QTimer.singleShot(300000, lambda: (out("TIMEOUT"), summarise([s for s in build_sources(client.sources)])))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
