"""日志与崩溃诊断。

* 日志写入 ``<data>/logs/hushplayer.log``，5MB 轮转保留 5 份。
* 额外记录 ``faulthandler`` 输出到 ``crash.log``，用于诊断原生崩溃。
* UI 层通过 :func:`log_exception` 把异常写入日志并保留完整堆栈。
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import traceback
from pathlib import Path

from . import paths

_LOGGER_NAME = "hushplayer"
_configured = False


class _SafeRotatingHandler(logging.handlers.RotatingFileHandler):
    def handleError(self, record):  # pragma: no cover - 磁盘异常时不应崩溃
        pass


def setup_logging(level: int | str = logging.INFO, *, console: bool = True) -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    paths.ensure_dirs()
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = paths.logs_dir() / "hushplayer.log"
    try:
        file_handler = _SafeRotatingHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass

    if console:
        stream = logging.StreamHandler(stream=sys.stderr)
        stream.setFormatter(fmt)
        stream.setLevel(logging.WARNING if not os.environ.get("HUSHPLAYER_DEBUG") else logging.DEBUG)
        logger.addHandler(stream)

    try:
        crash = open(paths.logs_dir() / "crash.log", "a", encoding="utf-8")
        faulthandler.enable(file=crash, all_threads=True)
        _crash_file = crash  # noqa: F841 - 保持文件句柄存活
    except OSError:
        pass

    _configured = True
    logger.info("=" * 78)
    logger.info(
        "HushPlayer 启动 | python=%s | platform=%s | frozen=%s | data=%s",
        platform.python_version(),
        platform.platform(),
        paths.is_frozen(),
        paths.data_dir(),
    )
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def log_fields(**fields: object) -> str:
    """统一 ``key=value`` 日志字段，缺省字段直接省略（不打印 None）。"""
    return " ".join(f"{key}={value}" for key, value in fields.items() if value not in (None, ""))


def log_exception(message: str, exc: BaseException | None = None) -> str:
    logger = get_logger("crash")
    detail = "".join(traceback.format_exception(exc)) if exc is not None else traceback.format_exc()
    logger.error("%s\n%s", message, detail)
    return detail


def recent_log_text(max_chars: int = 12000) -> str:
    path = paths.logs_dir() / "hushplayer.log"
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(日志不可用)"
    return text[-max_chars:]
