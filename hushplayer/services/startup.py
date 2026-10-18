"""开机自启（用户级、可撤销，不写注册表）。

实现方式：在 ``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup``
放一个 ``HushPlayer.cmd`` 启动脚本；关闭时删除该文件。
不改注册表、不需要管理员权限，用户也可以在「启动」文件夹里自行删除。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..core.logging_setup import get_logger
from ..core.paths import is_frozen

log = get_logger("services.startup")

SCRIPT_NAME = "HushPlayer.cmd"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def script_path() -> Path:
    return startup_dir() / SCRIPT_NAME


def is_enabled() -> bool:
    try:
        return script_path().is_file()
    except OSError:
        return False


def launch_command() -> str:
    if is_frozen():
        import sys

        return f'"{sys.executable}"'
    return f'"{_python()}" -m hushplayer'


def _python() -> str:
    import sys

    return sys.executable


def set_enabled(enabled: bool, *, executable: str | None = None) -> tuple[bool, str]:
    """启用/禁用开机自启。返回 (是否成功, 说明)。"""
    target = script_path()
    try:
        if enabled:
            startup_dir().mkdir(parents=True, exist_ok=True)
            command = executable or launch_command()
            content = f'@echo off\r\nstart "" {command}\r\n'
            target.write_text(content, encoding="utf-8")
            log.info("已写入开机启动脚本：%s", target)
            return True, str(target)
        if target.is_file():
            target.unlink()
            log.info("已删除开机启动脚本：%s", target)
        return True, str(target)
    except OSError as exc:
        log.warning("设置开机自启失败：%s", exc)
        return False, str(exc)
