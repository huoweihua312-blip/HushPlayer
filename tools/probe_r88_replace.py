"""截图：替换来源对话框（含增量状态、时长提示）。

离屏渲染，不弹真窗口；用假数据直接喂给对话框的渲染函数。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(ROOT / "artifacts" / "qa" / "_r88" / "data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.core.fonts import load_bundled_fonts  # noqa: E402
from hushplayer.core import theme as theme_mod  # noqa: E402
from hushplayer.model.track import Track  # noqa: E402
from hushplayer.services.source_replace import SourceCandidate  # noqa: E402

OUT = ROOT / "artifacts" / "qa" / "_r88"


def candidate(remote_id: str, source: tuple[str, str], *, title="家书", artist="加木", album="羲和",
              duration=242_000, score=100, note="") -> SourceCandidate:
    return SourceCandidate(
        source_id=source[0], source_name=source[1], remote_id=remote_id,
        title=title, artist=artist, album=album, duration_ms=duration,
        artwork_url="", score=score, raw={}, note=note,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()

    from hushplayer.ui.track_source_dialog import TrackSourceDialog

    track = Track(id="online:kw:abc", kind="online", title="家书", artist="加木", album="羲和",
                  duration_ms=242_000, source_id="kw", source_name="酷我", remote_id="abc")

    for mode in ("light", "dark"):
        theme_mod.theme().apply(mode=mode)
        dialog = TrackSourceDialog(None, track)
        dialog.show()
        app.processEvents()

        partial = [
            candidate("wy1", ("wy", "网易音乐")),
            candidate("kg1", ("kg", "酷狗"), duration=258_000, score=96, note="时长与原曲差 16 秒，请确认版本"),
            candidate("qq1", ("qq", "QQ音乐"), duration=239_000, score=91),
        ]
        dialog._on_update(partial, ["酷我：Request failed with status code 404"], 3, 4)
        app.processEvents()
        dialog.grab().save(str(OUT / f"replace_partial_{mode}.png"))

        dialog._on_finished(partial, ["酷我：Request failed with status code 404"])
        app.processEvents()
        dialog.grab().save(str(OUT / f"replace_done_{mode}.png"))
        print(mode, "status:", dialog.status.text())
        dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
