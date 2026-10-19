"""Windows shell integration: SMTC, taskbar progress, global hotkeys."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt

from ..core.logging_setup import log_exception, get_logger
from .hotkeys import GlobalHotkeys
from .smtc import SmtcService
from .taskbar import TaskbarProgress

log = get_logger(__name__)


class MediaIntegration(QObject):
    """Keeps Windows-side affordances in sync with the Qt player."""

    def __init__(self, player, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._settings = settings
        self._window = None
        self._hwnd = 0
        self._taskbar_state = "idle"

        self.smtc = SmtcService(self)
        self.taskbar = TaskbarProgress()
        self.hotkeys: GlobalHotkeys | None = None

        player.track_changed.connect(self._on_track)
        player.state_changed.connect(self._on_state)
        player.position_changed.connect(self._on_position)
        player.duration_changed.connect(self._on_duration)

        self.smtc.play_requested.connect(player.resume, Qt.QueuedConnection)
        self.smtc.pause_requested.connect(player.pause, Qt.QueuedConnection)
        self.smtc.toggle_requested.connect(player.toggle, Qt.QueuedConnection)
        self.smtc.stop_requested.connect(player.stop, Qt.QueuedConnection)
        self.smtc.next_requested.connect(player.next, Qt.QueuedConnection)
        self.smtc.previous_requested.connect(player.previous, Qt.QueuedConnection)
        self.smtc.seek_requested.connect(player.seek, Qt.QueuedConnection)

        settings.changed.connect(self._on_setting_changed)
        self.apply_settings()

    # ------------------------------------------------------------------ wiring
    def attach_window(self, window) -> None:  # noqa: ANN001 - QWidget
        self._window = window
        try:
            self._hwnd = int(window.winId())
        except Exception:
            self._hwnd = 0
        if self.hotkeys is None and self._hwnd:
            self.hotkeys = GlobalHotkeys(self._hwnd, self)
            self.hotkeys.play_pause_requested.connect(self._player.toggle)
            self.hotkeys.next_requested.connect(self._player.next)
            self.hotkeys.previous_requested.connect(self._player.previous)
            self.hotkeys.mute_requested.connect(self._player.toggle_mute)
            self.hotkeys.show_window_requested.connect(self._window_from_tray)
        self.apply_settings()

    def _window_from_tray(self) -> None:
        window = getattr(self, "_window", None)
        if window is not None and hasattr(window, "show_from_background"):
            window.show_from_background()

    # ------------------------------------------------------------------ settings
    def apply_settings(self) -> None:
        settings = self._settings
        smtc_enabled = bool(settings.get("general.system_media_controls", True))
        if self.smtc.available:
            try:
                self.smtc._smtc.is_enabled = smtc_enabled  # noqa: SLF001
            except Exception:
                pass
        if self.hotkeys is not None:
            self.hotkeys.set_enabled(bool(settings.get("general.global_hotkeys", True)))
        if not bool(settings.get("general.taskbar_progress", True)):
            self._clear_taskbar()

    def _on_setting_changed(self, key: str, _value) -> None:
        if key.startswith("general.system_media_controls") or key in (
            "general.global_hotkeys",
            "general.taskbar_progress",
        ):
            self.apply_settings()

    # ------------------------------------------------------------------ player
    def _on_track(self, track) -> None:  # noqa: ANN001
        self.smtc.set_track(track)
        self._update_taskbar_tooltip()

    def _on_state(self, state: str) -> None:
        self.smtc.set_state(state)
        if state in ("stopped",):
            self._clear_taskbar()
        else:
            self._update_taskbar()

    def _on_position(self, position: int) -> None:
        self.smtc.set_position(position)
        self._update_taskbar()

    def _on_duration(self, duration: int) -> None:
        self.smtc.set_duration(duration)

    # ------------------------------------------------------------------ taskbar
    def _taskbar_enabled(self) -> bool:
        return bool(
            self._settings.get("general.taskbar_progress", True)
            and self.taskbar.available
            and self._hwnd
        )

    def _update_taskbar(self) -> None:
        if not self._taskbar_enabled():
            return
        try:
            duration = int(self._player.duration or 0)
            position = int(self._player.position or 0)
        except Exception:
            return
        if duration <= 0:
            self._clear_taskbar()
            return
        try:
            self.taskbar.set_progress(self._hwnd, min(1.0, position / duration))
        except Exception as exc:  # pragma: no cover - COM edge cases
            log_exception("更新任务栏进度失败", exc)

    def _clear_taskbar(self) -> None:
        if self.taskbar.available and self._hwnd:
            try:
                self.taskbar.clear(self._hwnd)
            except Exception:
                pass

    def _update_taskbar_tooltip(self) -> None:
        if not self._taskbar_enabled():
            return
        player = self._player
        track = getattr(player, "current", None)
        text = "HushPlayer"
        if track is not None:
            text = f"{track.title} — {track.artist}" if track.artist else track.title
        try:
            self.taskbar.set_tooltip(self._hwnd, text)
        except Exception:
            pass

    # ------------------------------------------------------------------ shutdown
    def shutdown(self) -> None:
        if self.hotkeys is not None:
            self.hotkeys.unregister()
        self._clear_taskbar()
        self.smtc.shutdown()
        self.taskbar.release()
