"""Application-level close, background playback, and tray behavior."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

from app.ui_v2.adapters.legacy_settings_bridge import (
    load_settings_document,
    write_settings_document,
)


CLOSE_BEHAVIOR_ASK = "ask"
CLOSE_BEHAVIOR_EXIT = "exit"
CLOSE_BEHAVIOR_TRAY = "tray"
CLOSE_BEHAVIORS = frozenset(
    {CLOSE_BEHAVIOR_ASK, CLOSE_BEHAVIOR_EXIT, CLOSE_BEHAVIOR_TRAY}
)

CloseDecision = tuple[str, bool] | None
DecisionProvider = Callable[[QWidget], CloseDecision]


class CloseBehaviorController(QObject):
    """Keep the main window alive in the tray without stopping playback."""

    hidden_to_tray = Signal()
    restored_from_tray = Signal()
    desktop_lyrics_unlock_requested = Signal()
    exiting = Signal()
    preference_save_failed = Signal(str)

    def __init__(
        self,
        app: QApplication,
        settings_path: Path | str,
        *,
        icon: QIcon | None = None,
        parent: QObject | None = None,
        tray_available: bool | None = None,
        decision_provider: DecisionProvider | None = None,
    ) -> None:
        super().__init__(parent or app)
        self._app = app
        self._settings_path = Path(settings_path)
        self._window_ref: weakref.ReferenceType[QWidget] | None = None
        self._tray_available_override = tray_available
        self._decision_provider = decision_provider
        self._allow_next_close = False
        self._window_hidden_to_tray = False
        self._desktop_lyrics_locked = False

        tray_icon = icon or app.windowIcon()
        self.tray_icon = QSystemTrayIcon(tray_icon, self)
        self.tray_icon.setToolTip("HushPlayer")
        self.tray_menu = QMenu()
        self.desktop_lyrics_unlock_action = QAction("解锁桌面歌词", self.tray_menu)
        self.desktop_lyrics_unlock_action.setVisible(False)
        self.open_action = QAction("打开 HushPlayer", self.tray_menu)
        self.exit_action = QAction("退出 HushPlayer", self.tray_menu)
        self.tray_menu.addAction(self.desktop_lyrics_unlock_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.open_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.desktop_lyrics_unlock_action.triggered.connect(
            lambda _checked=False: self.desktop_lyrics_unlock_requested.emit()
        )
        self.open_action.triggered.connect(self.restore_window)
        self.exit_action.triggered.connect(self.request_exit)
        self.tray_icon.activated.connect(self._on_tray_activated)

    @property
    def system_tray_available(self) -> bool:
        if self._tray_available_override is not None:
            return bool(self._tray_available_override)
        return bool(QSystemTrayIcon.isSystemTrayAvailable())

    def register_window(self, window: QWidget) -> None:
        self._window_ref = weakref.ref(window)

    def set_desktop_lyrics_locked(self, locked: bool) -> None:
        """Expose a tray unlock action while enabled lyrics remain pass-through."""

        self._desktop_lyrics_locked = bool(locked)
        self.desktop_lyrics_unlock_action.setVisible(self._desktop_lyrics_locked)
        self._sync_tray_visibility()

    def _sync_tray_visibility(self) -> None:
        should_show = self._window_hidden_to_tray or self._desktop_lyrics_locked
        if should_show:
            self.tray_icon.show()
        else:
            self.tray_icon.hide()

    def allow_next_close(self) -> None:
        """Bypass the user prompt for an intentional internal shutdown."""

        self._allow_next_close = True

    def handle_close(self, window: QWidget, event: QCloseEvent) -> bool:
        """Handle a user-requested close and return whether cleanup may run."""

        if self._allow_next_close:
            self._allow_next_close = False
            self._finish_exit(event)
            return True

        if not self.system_tray_available:
            QMessageBox.information(
                window,
                "系统托盘不可用",
                "系统托盘不可用，HushPlayer 将直接退出。",
            )
            self._finish_exit(event)
            return True

        behavior, remembered = self._read_preferences()
        if not remembered or behavior not in {
            CLOSE_BEHAVIOR_EXIT,
            CLOSE_BEHAVIOR_TRAY,
        }:
            decision = (
                self._decision_provider(window)
                if self._decision_provider is not None
                else self._ask_for_decision(window)
            )
            if decision is None:
                event.ignore()
                return False
            behavior, remember = decision
            if behavior not in {CLOSE_BEHAVIOR_EXIT, CLOSE_BEHAVIOR_TRAY}:
                event.ignore()
                return False
            self._save_preferences(behavior, remember)
        if behavior == CLOSE_BEHAVIOR_TRAY:
            self._minimize_to_tray(window, event)
            return False
        self._finish_exit(event)
        return True

    def request_exit(self) -> None:
        """Exit from the tray menu without asking the close question again."""

        window = self._window()
        if window is None:
            self._app.quit()
            return
        window.close()
        QTimer.singleShot(0, self._app.quit)

    def restore_window(self) -> None:
        window = self._window()
        if window is None:
            return
        self._window_hidden_to_tray = False
        window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()
        self._sync_tray_visibility()
        self.restored_from_tray.emit()

    def _window(self) -> QWidget | None:
        return self._window_ref() if self._window_ref is not None else None

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.restore_window()

    def _read_preferences(self) -> tuple[str, bool]:
        document = load_settings_document(self._settings_path)
        behavior = str(document.get("close_behavior") or CLOSE_BEHAVIOR_ASK).strip().casefold()
        if behavior not in CLOSE_BEHAVIORS:
            behavior = CLOSE_BEHAVIOR_ASK
        return behavior, bool(document.get("remember_close_choice", False))

    def _save_preferences(self, behavior: str, remember: bool) -> None:
        try:
            document = load_settings_document(self._settings_path)
            document["remember_close_choice"] = bool(remember)
            document["close_behavior"] = behavior if remember else CLOSE_BEHAVIOR_ASK
            write_settings_document(self._settings_path, document)
        except Exception as error:
            self.preference_save_failed.emit(str(error))

    def _ask_for_decision(self, window: QWidget) -> CloseDecision:
        dialog = QMessageBox(window)
        dialog.setWindowTitle("关闭 HushPlayer")
        dialog.setText("你希望如何处理 HushPlayer？")
        dialog.setInformativeText("最小化到托盘后，播放、队列和歌词会继续运行。")
        exit_button = dialog.addButton("直接退出", QMessageBox.ButtonRole.AcceptRole)
        tray_button = dialog.addButton("最小化到托盘", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        remember_box = QCheckBox("记住我的选择", dialog)
        dialog.setCheckBox(remember_box)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is exit_button:
            return CLOSE_BEHAVIOR_EXIT, remember_box.isChecked()
        if clicked is tray_button:
            return CLOSE_BEHAVIOR_TRAY, remember_box.isChecked()
        return None

    def _minimize_to_tray(self, window: QWidget, event: QCloseEvent) -> None:
        event.ignore()
        self._app.setQuitOnLastWindowClosed(False)
        self._window_hidden_to_tray = True
        self._sync_tray_visibility()
        window.hide()
        self.hidden_to_tray.emit()

    def _finish_exit(self, event: QCloseEvent) -> None:
        event.accept()
        self._window_hidden_to_tray = False
        self._desktop_lyrics_locked = False
        self.desktop_lyrics_unlock_action.setVisible(False)
        self.tray_icon.hide()
        self.exiting.emit()
        QTimer.singleShot(0, self._app.quit)
