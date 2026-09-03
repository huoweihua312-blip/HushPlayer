"""Cross-process coordination for the HushPlayer desktop application."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.core.version import APP_NAME


DEFAULT_SINGLE_INSTANCE_NAME = f"{APP_NAME}.SingleInstance"
DEFAULT_SINGLE_INSTANCE_LOCK_PATH = (
    Path(tempfile.gettempdir()) / APP_NAME / "single-instance.lock"
)


class SingleInstanceCoordinator(QObject):
    """Keep one desktop process and notify it when another launch is attempted."""

    activation_requested = Signal()

    def __init__(
        self,
        *,
        name: str = DEFAULT_SINGLE_INSTANCE_NAME,
        lock_path: str | Path = DEFAULT_SINGLE_INSTANCE_LOCK_PATH,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("单实例名称不能为空。")

        self._name = normalized_name
        self._is_primary = False
        self._pending_activation = False
        self._lock_path = Path(lock_path)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(self._lock_path))
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_new_connection)
        self._claim_or_notify()

    @property
    def is_primary(self) -> bool:
        return self._is_primary

    @property
    def has_pending_activation(self) -> bool:
        return self._pending_activation

    def _claim_or_notify(self) -> None:
        if not self._lock.tryLock(0):
            self._notify_existing_instance()
            return

        self._is_primary = True
        if self._server.listen(self._name):
            return

        if self._notify_existing_instance():
            self.close()
            return

        # A crashed process can leave the local-server name behind on some
        # platforms. Only remove it after a failed connection probe, then
        # retry the claim. If the retry also fails, stay secondary so that a
        # launch failure cannot create a second playback process.
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name):
            self.close()

    def _notify_existing_instance(self) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self._name)
        if not socket.waitForConnected(250):
            socket.deleteLater()
            return False

        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        socket.deleteLater()
        return True

    def _handle_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._pending_activation = True
            self.activation_requested.emit()
            socket.disconnectFromServer()
            socket.deleteLater()

    def close(self) -> None:
        """Release the local server owned by this process."""

        if not self._is_primary:
            return
        self._server.close()
        QLocalServer.removeServer(self._name)
        self._lock.unlock()
        self._is_primary = False
