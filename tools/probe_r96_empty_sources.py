"""空音源首启探针：确认新用户没有任何插件时能正常进「在线音源」页。

运行：``QT_QPA_PLATFORM=offscreen python tools/probe_r96_empty_sources.py``
输出：``artifacts/qa/r96/empty_sources.png``
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts" / "qa" / "r96"
DATA = BASE / "data"

if DATA.exists():
    shutil.rmtree(DATA)
DATA.mkdir(parents=True, exist_ok=True)

os.environ["HUSHPLAYER_DATA_DIR"] = str(DATA)
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.online import source_migration  # noqa: E402

# 模拟全新用户：开发机仓库里仍有旧插件目录，这里关掉迁移来源。
source_migration.legacy_roots = lambda: []  # type: ignore[assignment]
from hushplayer.ui.pages.settings import SECTIONS, SettingsPage  # noqa: E402


def pump(ms: int) -> None:
    app = QApplication.instance()
    deadline = ms
    while deadline > 0:
        app.processEvents()
        app.thread().msleep(30)
        deadline -= 30


def main() -> int:
    qt = QApplication.instance() or QApplication([])
    app = HushApp(qt)
    app.start()
    pump(1200)

    app.window.navigate("settings")
    pump(600)

    page = app.window.findChild(SettingsPage)
    assert page is not None, "找不到设置页"
    index = [key for key, _label, _icon in SECTIONS].index("online")
    page._nav.set_current(index)
    page._show_section(index)
    pump(1200)

    sources = app.player.sources
    registry = DATA / "sources" / "source_registry.json"
    print("sources:", len(sources))
    print("registry exists:", registry.is_file())
    print("registry:", registry.read_text(encoding="utf-8") if registry.is_file() else "-")

    app.window.resize(1280, 820)
    pump(800)
    BASE.mkdir(parents=True, exist_ok=True)
    target = BASE / "empty_sources.png"
    app.window.grab().save(str(target))
    print("saved", target)

    app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
