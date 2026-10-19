"""版本与构建信息。"""

from __future__ import annotations

APP_NAME = "HushPlayer"
APP_ID = "com.hushplayer.desktop"
VERSION = "1.0.28"
BUILD_CHANNEL = "stable"
VERSION_TUPLE = tuple(int(part) for part in VERSION.split("."))

__version__ = VERSION


def version_string() -> str:
    return VERSION
