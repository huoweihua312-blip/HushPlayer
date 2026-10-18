"""BUG-08 check: settings cards restyle when the theme changes live."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
_ROOT = os.path.abspath("artifacts/qa/theme")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.join(_ROOT, "data"))
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.core.theme import theme


def card_pixel(window) -> tuple[int, int, int]:
    """Sample the middle of the first settings card."""
    page = window.pages["settings"] if hasattr(window, "pages") else None
    if page is None:
        return (0, 0, 0)
    section = page._sections.get("general")
    if section is None:
        return (0, 0, 0)
    card = section.findChild(type(section.findChildren(object)[0])) if False else None
    img = section.grab().toImage()
    x, y = img.width() // 2, 40
    colour = img.pixelColor(x, y)
    return (colour.red(), colour.green(), colour.blue())


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    hush = HushApp(app)
    hush.start()
    hush.settings.set("appearance.theme", "dark")
    hush.apply_theme()
    hush.window.navigate("settings")
    hush.window.show()

    def shoot(name: str) -> None:
        hush.window.grab().save(os.path.join(_ROOT, f"{name}.png"))

    def to_light() -> None:
        hush.settings.set("appearance.theme", "light")
        hush.apply_theme()

    def finish() -> None:
        print("mode", theme().mode, flush=True)
        hush.shutdown()
        app.quit()

    QTimer.singleShot(900, lambda: shoot("settings_dark_live"))
    QTimer.singleShot(1300, to_light)
    QTimer.singleShot(1900, lambda: shoot("settings_light_live"))
    QTimer.singleShot(2400, finish)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
