"""R89: 1.3.11 视觉证据 —— toast 合并与图标按钮焦点环。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(ROOT / "artifacts" / "qa" / "_r89" / "data"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from hushplayer.core.theme import apply_theme_to_app, theme  # noqa: E402
from hushplayer.ui.widgets.common import IconButton  # noqa: E402
from hushplayer.ui.widgets.toast import ToastHost  # noqa: E402

OUT = ROOT / "artifacts" / "qa" / "_r89"
OUT.mkdir(parents=True, exist_ok=True)


def shoot(widget: QWidget, name: str) -> None:
    widget.grab().save(str(OUT / name))
    print("saved", name, widget.size().toTuple())


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme_to_app(app, preference="light")
    for mode in ("light", "dark"):
        apply_theme_to_app(app, preference=mode)
        app.setStyleSheet(theme().qss())
        host = QWidget()
        host.resize(720, 200)
        host.show()
        host.setStyleSheet("background:#f4f4f6;" if mode == "light" else "background:#101014;")
        toast = ToastHost(host)
        toast.show_message("user_source_d22b 暂时无法播放（该源最近解析失败），正在其他音源中查找…", "info")
        toast.show_message("已切换到 网易云 音源", "info")
        toast.show_message("已通过 网易云 播放《晴天》", "info")
        app.processEvents()
        for item in toast._toasts:
            item._effect.setOpacity(1.0)
            item.show()
        app.processEvents()
        print("visible toasts:", len(toast._toasts))
        if toast._toasts:
            item = toast._toasts[0]
            item.grab().save(str(OUT / f"toast_merged_{mode}.png"))
            print("saved toast", item.size().toTuple())

        bar = QWidget()
        bar.resize(320, 90)
        bar.setStyleSheet("background:#ffffff;" if mode == "light" else "background:#101014;")
        button = IconButton("next", parent=bar, tooltip="下一首 (Ctrl+Right)", size=36)
        button.move(140, 26)
        bar.show()
        button.show()
        button.setFocus(Qt.FocusReason.TabFocusReason)
        app.processEvents()
        shoot(bar, f"focus_ring_{mode}.png")
        host.close()
        bar.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
