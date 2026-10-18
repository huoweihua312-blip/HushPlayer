"""Print metadata for every fixture file (manual sanity check)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hushplayer.library.metadata import read_track  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures", "audio")


def main() -> int:
    for base, _dirs, files in os.walk(ROOT):
        for name in sorted(files):
            if not name.lower().endswith((".mp3", ".flac", ".wav", ".ogg")):
                continue
            path = os.path.join(base, name)
            try:
                track, cover, ext = read_track(path)
            except Exception as exc:
                print(f"{name[:44]:<46} SKIP {type(exc).__name__}: {exc}")
                continue
            cover_len = len(cover or b"")
            print(
                f"{name[:36]:<38} | {track.title[:22]:<24} | {track.artist[:12]:<14} | "
                f"{track.album[:16]:<18} | {track.duration_ms:>6}ms | cover={cover_len:>6}B{ext} | "
                f"{track.codec} | {track.track_no}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
