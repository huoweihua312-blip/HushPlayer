"""版本更新检查。

设计原则（与用户要求一致）：
- 不自动下载、不静默安装，只做「检查 + 告知 + 打开下载页」；
- 更新源是可配置的 JSON 清单，默认留空；未配置时明确告知而不是假装成功；
- 网络请求在后台线程执行，不阻塞 UI；
- 结果可诊断（日志里记录 URL、状态码、解析错误）。

清单格式（HTTP GET，UTF-8 JSON）::

    {
      "version": "1.1.0",
      "url": "https://example.com/HushPlayer-1.1.0-win64.zip",
      "notes": "本次更新内容……",
      "published_at": "2026-02-01",
      "minimum": "1.0.0"
    }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

import requests
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core.logging_setup import get_logger
from ..core.settings import settings
from ..version import VERSION

log = get_logger("services.updater")

DEFAULT_MANIFEST_URL = ""
REQUEST_TIMEOUT = (6, 12)
USER_AGENT = f"HushPlayer/{VERSION} (Windows; update check)"

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    version: str
    url: str = ""
    notes: str = ""
    published_at: str = ""
    minimum: str = ""

    @property
    def available(self) -> bool:
        return compare_versions(self.version, self.current) > 0

    @property
    def published_text(self) -> str:
        if not self.published_at:
            return ""
        return self.published_at[:10]


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.search(str(text or ""))
    if not match:
        return (0, 0, 0)
    parts = [int(group) if group else 0 for group in match.groups()]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def compare_versions(left: str, right: str) -> int:
    """返回 1 / 0 / -1，语义与 ``left - right`` 一致。"""
    a, b = parse_version(left), parse_version(right)
    return (a > b) - (a < b)


def manifest_url() -> str:
    configured = str(settings().get("update.manifest_url", DEFAULT_MANIFEST_URL) or "").strip()
    return configured


class _CheckJob(QRunnable):
    def __init__(self, url: str, service: "UpdateService") -> None:
        super().__init__()
        self._url = url
        self._service = service

    def run(self) -> None:  # pragma: no cover - 线程内执行
        service = self._service
        try:
            response = requests.get(
                self._url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"服务器返回 HTTP {response.status_code}")
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"更新清单不是合法 JSON：{exc}") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("更新清单格式不正确")
            version = str(payload.get("version", "")).strip()
            if not version:
                raise RuntimeError("更新清单缺少 version 字段")
            info = UpdateInfo(
                current=VERSION,
                version=version,
                url=str(payload.get("url") or payload.get("download_url") or ""),
                notes=str(payload.get("notes") or payload.get("changelog") or ""),
                published_at=str(payload.get("published_at") or payload.get("date") or ""),
                minimum=str(payload.get("minimum") or ""),
            )
            log.info(
                "更新检查完成：远端=%s 本地=%s 可用=%s",
                info.version,
                info.current,
                info.available,
            )
            service._finish(info)
        except Exception as exc:  # noqa: BLE001
            log.warning("更新检查失败：%s（%s）", exc, self._url)
            service._fail(str(exc))


class UpdateService(QObject):
    """异步检查更新，只报告结果，不执行安装。"""

    checked = Signal(object)   # UpdateInfo
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def check_async(self) -> bool:
        if self._running:
            return False
        url = manifest_url()
        if not url:
            self.failed.emit("尚未配置更新源（settings: update.manifest_url）")
            return False
        self._running = True
        self._pool.start(_CheckJob(url, self))
        return True

    # ----------------------------------------------------------------- 内部
    def _finish(self, info: UpdateInfo) -> None:
        self._running = False
        self.checked.emit(info)

    def _fail(self, message: str) -> None:
        self._running = False
        self.failed.emit(message)

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(1500)


def check_on_start_enabled() -> bool:
    return bool(settings().get("update.check_on_start", True)) and bool(manifest_url())


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
