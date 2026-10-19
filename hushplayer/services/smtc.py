"""Windows system media transport controls (SMTC) integration.

Uses the WinRT ``MediaPlayer`` projection purely as a way to obtain a
``SystemMediaTransportControls`` instance for this process; actual audio still
plays through Qt Multimedia.  Everything degrades to a no-op when the WinRT
projection is unavailable (older Windows, missing wheels, non-Windows CI).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..core.logging_setup import log_exception, get_logger
from ..model.track import Track

log = get_logger(__name__)


def _load_winrt() -> tuple[Any, Any, Any, Any]:
    from winrt.windows.media import (  # type: ignore[import-not-found]
        MediaPlaybackStatus,
        MediaPlaybackType,
        SystemMediaTransportControlsButton,
        SystemMediaTransportControlsTimelineProperties,
    )
    from winrt.windows.media.playback import MediaPlayer  # type: ignore[import-not-found]

    return (
        MediaPlayer,
        MediaPlaybackType,
        SystemMediaTransportControlsButton,
        SystemMediaTransportControlsTimelineProperties,
    )


class SmtcService(QObject):
    """Expose HushPlayer to the Windows media overlay / hardware media keys."""

    play_requested = Signal()
    pause_requested = Signal()
    toggle_requested = Signal()
    stop_requested = Signal()
    next_requested = Signal()
    previous_requested = Signal()
    seek_requested = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._available = False
        self._player = None
        self._smtc = None
        self._timeline_cls = None
        self._status_enum = None
        self._track: Track | None = None
        self._duration_ms = 0
        self._position_ms = 0
        self._last_timeline = 0.0
        self._setup()

    # ------------------------------------------------------------------ setup
    def _setup(self) -> None:
        try:
            MediaPlayer, playback_type, button_enum, timeline_cls = _load_winrt()
            from winrt.windows.media import MediaPlaybackStatus  # type: ignore[import-not-found]

            player = MediaPlayer()
            smtc = player.system_media_transport_controls
            smtc.is_enabled = True
            for attr in (
                "is_play_enabled",
                "is_pause_enabled",
                "is_stop_enabled",
                "is_next_enabled",
                "is_previous_enabled",
            ):
                try:
                    setattr(smtc, attr, True)
                except Exception:  # pragma: no cover - projection variance
                    pass
            updater = smtc.display_updater
            updater.type = playback_type.MUSIC
            smtc.add_button_pressed(self._on_button)
        except Exception as exc:  # pragma: no cover - platform dependent
            log.info("系统媒体控制不可用：%s", exc)
            self._available = False
            return
        self._player = player
        self._smtc = smtc
        self._timeline_cls = timeline_cls
        self._button_enum = button_enum
        self._status_enum = MediaPlaybackStatus
        self._available = True
        log.info("系统媒体控制（SMTC）已启用")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------ update
    def set_track(self, track: Track | None) -> None:
        self._track = track
        self._duration_ms = track.duration_ms if track else 0
        if not self._available:
            return
        try:
            updater = self._smtc.display_updater
            props = updater.music_properties
            if track is None:
                props.title = "HushPlayer"
                props.artist = ""
                props.album_title = ""
            else:
                props.title = track.title
                props.artist = track.artist
                props.album_title = track.album
            updater.update()
            self._apply_timeline(force=True)
        except Exception as exc:  # pragma: no cover
            log_exception("更新系统媒体信息失败", exc)

    def set_state(self, state: str) -> None:
        if not self._available:
            return
        try:
            status = self._status_enum
            mapping = {
                "playing": status.PLAYING,
                "paused": status.PAUSED,
                "stopped": status.STOPPED,
                "loading": status.CHANGING,
            }
            self._smtc.playback_status = mapping.get(state, status.CLOSED)
        except Exception as exc:  # pragma: no cover
            log_exception("更新系统媒体播放状态失败", exc)

    def set_position(self, position_ms: int) -> None:
        self._position_ms = max(0, position_ms)
        self._apply_timeline()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, duration_ms)
        self._apply_timeline(force=True)

    def _apply_timeline(self, *, force: bool = False) -> None:
        if not self._available or self._timeline_cls is None:
            return
        import time

        now = time.monotonic()
        if not force and now - self._last_timeline < 1.0:
            return
        self._last_timeline = now
        try:
            timeline = self._timeline_cls()
            duration = max(self._duration_ms, self._position_ms, 1000)
            timeline.start_time = timedelta(0)
            timeline.end_time = timedelta(milliseconds=duration)
            timeline.position = timedelta(milliseconds=min(self._position_ms, duration))
            timeline.min_seek_time = timedelta(0)
            timeline.max_seek_time = timedelta(milliseconds=duration)
            self._smtc.update_timeline_properties(timeline)
        except Exception as exc:  # pragma: no cover
            log_exception("更新系统媒体时间轴失败", exc)

    # ------------------------------------------------------------------ events
    def _on_button(self, _sender, args) -> None:  # noqa: ANN001 - WinRT callback
        try:
            button = args.button
        except Exception:  # pragma: no cover
            return
        try:
            from winrt.windows.media import (  # type: ignore[import-not-found]
                SystemMediaTransportControlsButton as B,
            )

            if button == B.PLAY:
                self.play_requested.emit()
            elif button == B.PAUSE:
                self.pause_requested.emit()
            elif button == B.STOP:
                self.stop_requested.emit()
            elif button == B.NEXT:
                self.next_requested.emit()
            elif button == B.PREVIOUS:
                self.previous_requested.emit()
            elif button == B.RECORD:
                return
            else:
                self.toggle_requested.emit()
        except Exception:  # pragma: no cover
            return

    def shutdown(self) -> None:
        self._available = False
        player = self._player
        self._player = None
        self._smtc = None
        if player is not None:
            try:
                player.close()
            except Exception:
                pass


def create_paused_media_player():  # pragma: no cover - helper for tests
    MediaPlayer, *_ = _load_winrt()
    return MediaPlayer()
