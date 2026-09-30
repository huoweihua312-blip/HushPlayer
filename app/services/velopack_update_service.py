"""Opt-in Velopack update controller for the migration prototype."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.services.velopack_runtime import create_update_manager


_LOGGER = logging.getLogger(__name__)


def _progress_values(args: tuple[object, ...]) -> tuple[int, int]:
    """Best-effort conversion across Velopack Python callback versions."""

    if len(args) >= 2:
        try:
            return max(0, int(args[0])), max(0, int(args[1]))
        except (TypeError, ValueError):
            pass
    if len(args) == 1:
        value = args[0]
        for names in (
            ("downloaded_bytes", "total_bytes"),
            ("DownloadedBytes", "TotalBytes"),
            ("bytes_downloaded", "bytes_total"),
        ):
            if all(hasattr(value, name) for name in names):
                try:
                    return max(0, int(getattr(value, names[0]))), max(
                        0, int(getattr(value, names[1]))
                    )
                except (TypeError, ValueError):
                    pass
    return 0, 0


class _VelopackWorker(QObject):
    check_requested = Signal()
    download_requested = Signal(object)
    apply_requested = Signal(object)

    update_available = Signal(object)
    no_update = Signal()
    failed = Signal(str)
    download_started = Signal()
    download_progress = Signal(int, int)
    ready = Signal(object)
    applying = Signal()

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source
        self.manager: Any | None = None
        self.check_requested.connect(self.check)
        self.download_requested.connect(self.download)
        self.apply_requested.connect(self.apply)

    @Slot()
    def check(self) -> None:
        try:
            manager = create_update_manager(self.source)
            if manager is None:
                raise RuntimeError("当前安装包没有包含 Velopack Python 运行模块。")
            self.manager = manager
            update = manager.check_for_updates()
            if update is None:
                self.no_update.emit()
            else:
                self.update_available.emit(update)
        except Exception as error:  # pragma: no cover - native wrapper errors vary
            _LOGGER.exception("Velopack update check failed.")
            self.failed.emit(str(error))

    @Slot(object)
    def download(self, update: object) -> None:
        try:
            if self.manager is None:
                raise RuntimeError("更新管理器尚未初始化。")
            self.download_started.emit()

            def on_progress(*args: object) -> None:
                received, total = _progress_values(tuple(args))
                self.download_progress.emit(received, total)

            self.manager.download_updates(update, on_progress)
            self.ready.emit(update)
        except Exception as error:  # pragma: no cover - native wrapper errors vary
            _LOGGER.exception("Velopack update download failed.")
            self.failed.emit(str(error))

    @Slot(object)
    def apply(self, update: object) -> None:
        try:
            if self.manager is None:
                raise RuntimeError("更新管理器尚未初始化。")
            self.applying.emit()
            self.manager.apply_updates_and_restart(update)
        except Exception as error:  # pragma: no cover - native wrapper errors vary
            _LOGGER.exception("Velopack update apply failed.")
            self.failed.emit(str(error))


class VelopackUpdateService(QObject):
    """Keep blocking Velopack calls away from the Qt UI thread."""

    checkStarted = Signal()
    updateAvailable = Signal(object)
    noUpdate = Signal()
    failed = Signal(str)
    downloadStarted = Signal()
    downloadProgress = Signal(int, int)
    updateReady = Signal(object)
    applying = Signal()

    def __init__(self, source: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.source = str(source or "").strip()
        if not self.source:
            raise ValueError("Velopack 更新源不能为空。")
        self._active = False
        self._applying = False
        self._closed = False
        self._thread = QThread(self)
        self._worker = _VelopackWorker(self.source)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self._worker.update_available.connect(self._on_update_available)
        self._worker.no_update.connect(self._on_no_update)
        self._worker.failed.connect(self._on_failed)
        self._worker.download_started.connect(self._on_download_started)
        self._worker.download_progress.connect(self.downloadProgress)
        self._worker.ready.connect(self._on_ready)
        self._worker.applying.connect(self._on_applying)
        self._thread.start()

    @property
    def is_active(self) -> bool:
        return self._active

    def check_for_updates(self) -> bool:
        if self._closed or self._active or self._applying:
            return False
        self._active = True
        self.checkStarted.emit()
        self._worker.check_requested.emit()
        return True

    def download_update(self, update: object) -> bool:
        if self._closed or self._active or self._applying:
            return False
        self._active = True
        self._worker.download_requested.emit(update)
        return True

    def apply_update(self, update: object) -> bool:
        if self._closed or self._active or self._applying:
            return False
        self._active = True
        self._applying = True
        self._worker.apply_requested.emit(update)
        return True

    @Slot(object)
    def _on_update_available(self, update: object) -> None:
        self._active = False
        self.updateAvailable.emit(update)

    @Slot()
    def _on_no_update(self) -> None:
        self._active = False
        self.noUpdate.emit()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._active = False
        self._applying = False
        self.failed.emit(str(message or "Velopack 更新失败。"))

    @Slot()
    def _on_download_started(self) -> None:
        self.downloadStarted.emit()

    @Slot(object)
    def _on_ready(self, update: object) -> None:
        self._active = False
        self.updateReady.emit(update)

    @Slot()
    def _on_applying(self) -> None:
        self.applying.emit()

    def shutdown(self) -> None:
        if self._closed or self._applying:
            return
        self._closed = True
        self._thread.quit()
        self._thread.wait(2_000)
