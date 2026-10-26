"""Playback session persistence.

The queue and the current position survive a restart: the state is written to
``play_queue.json`` in the data directory (atomically) a moment after it
changes, and once more when the application quits.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from ..audio.controller import PlayerController
from ..core import paths
from ..core.logging_setup import get_logger
from ..model.track import Track
from ..store.repository import TrackRepository

log = get_logger("services.state")

STATE_VERSION = 1
POSITION_SAVE_INTERVAL_MS = 5000
SAVE_DEBOUNCE_MS = 1200
#: 拖动进度条后尽快落盘一次（不必等周期保存，也不写 100ms 一次）。
SEEK_SAVE_DELAY_MS = 800
#: 位置跳变超过这个值就认为是 seek，而不是正常的播放推进。
SEEK_JUMP_MS = 1500
#: 会话写盘失败的重试退避（毫秒）。
SAVE_RETRY_MS = (1500, 5000, 15000)


def queue_file() -> str:
    return os.path.join(str(paths.data_dir()), "play_queue.json")


class PlaybackKeeper(QObject):
    """Persist/restore the play queue and the playhead."""

    restored = Signal(str)  # context label of the restored queue

    def __init__(
        self,
        controller: PlayerController,
        tracks: TrackRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._tracks = tracks
        self._dirty = False
        self._last_saved_position = -1
        #: 上一次看到的位置，用来区分「播放推进」和「拖动/恢复」造成的跳变。
        self._last_seen_position = -1
        #: 恢复失败时不要用空队列覆盖用户上一次有效的会话文件。
        self._suppress_clear = False
        #: flush() 之后进入「已收尾」状态：退出时引擎 stop() 会把位置清零，
        #: 那之后的保存只会把用户真实进度覆盖成 0。
        self._closed = False
        #: 写盘失败后的重试计数；成功一次就清零。
        self._retry_count = 0

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.save_now)

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(SEEK_SAVE_DELAY_MS)
        self._seek_timer.timeout.connect(self.save_now)

        self._position_timer = QTimer(self)
        self._position_timer.setInterval(POSITION_SAVE_INTERVAL_MS)
        self._position_timer.timeout.connect(self._save_position_tick)

        queue = controller.queue
        queue.changed.connect(self.schedule_save)
        queue.current_changed.connect(self._on_current_changed)
        queue.mode_changed.connect(self.schedule_save)
        controller.track_started.connect(lambda _track: self.schedule_save())
        controller.state_changed.connect(self._on_state_changed)
        controller.position_changed.connect(self._on_position_changed)

    # ------------------------------------------------------------------ api
    def restore(self) -> int:
        payload = self._read()
        if not payload:
            return 0
        tracks: list[Track] = []

        def resolve(track_id: str) -> Track | None:
            if not track_id:
                return None
            try:
                track = self._tracks.get(track_id)
            except Exception:
                return None
            if track is not None:
                tracks.append(track)
            return track

        try:
            # 恢复阶段队列换 current 只摆状态：不能顺手 resolve 播放，否则
            # 音源还没起来就会失败并自动跳到别的歌。
            begin = getattr(self._controller, "begin_restore", None)
            end = getattr(self._controller, "end_restore", None)
            if begin is not None:
                begin()
            try:
                self._controller.queue.restore(payload, resolver=resolve)
            finally:
                if end is not None:
                    end()
        except Exception:
            log.exception("cannot restore play queue")
            self._suppress_clear = True
            return 0
        if not self._controller.queue.count:
            # 队列里的歌都没了：保留旧的会话文件，别让它被一次失败的恢复清掉。
            self._suppress_clear = True
            log.info("restored queue is empty; keeping the previous session file")
            return 0
        position = int(payload.get("position_ms") or 0)
        current = self._controller.queue.current
        if current is not None:
            position = min(position, max(0, current.duration_ms - 1000)) if current.duration_ms else position
        self._last_saved_position = position
        context = self._controller.queue.context
        log.info("restored queue: %d tracks at %d ms", self._controller.queue.count, position)
        self.restored.emit(context)
        return position

    def schedule_save(self) -> None:
        self._dirty = True
        if not self._save_timer.isActive():
            self._save_timer.start()

    def save_now(self) -> bool:
        """Write the session file; returns False when the disk write failed.

        A failed write keeps ``_dirty`` set and does **not** update
        ``_last_saved_position``: the next attempt must still know how much of
        the session is unsaved, otherwise a transient disk error silently loses
        the user's progress.
        """
        if self._closed:
            return False
        self._save_timer.stop()
        payload = self.payload()
        if not payload:
            if self._suppress_clear:
                return True
            self._clear()
            self._dirty = False
            return True
        self._suppress_clear = False
        # 正在尝试写的这份数据就是「待保存」状态；写失败时它必须保持脏标记。
        self._dirty = True
        if not self._write(payload):
            self._schedule_retry()
            return False
        self._retry_count = 0
        self._dirty = False
        self._last_saved_position = payload.get("position_ms", -1)
        return True

    def _schedule_retry(self) -> None:
        if self._retry_count >= len(SAVE_RETRY_MS):
            log.error("无法写入播放会话（已重试 %d 次），继续使用内存中的状态", self._retry_count)
            return
        delay = SAVE_RETRY_MS[self._retry_count]
        self._retry_count += 1
        log.warning("写入播放会话失败，%d ms 后重试（第 %d 次）", delay, self._retry_count)
        self._save_timer.start(delay)

    def payload(self) -> dict[str, Any]:
        queue = self._controller.queue
        if not queue.count:
            return {}
        data = queue.to_dict()
        data["version"] = STATE_VERSION
        data["saved_at"] = time.time()
        data["position_ms"] = int(self._controller.position)
        current = queue.current
        data["current_id"] = current.id if current is not None else ""
        return data

    def flush(self) -> None:
        """退出前的最终保存；之后引擎 stop() 触发的位置归零不得覆盖它。"""
        if self._closed:
            return
        self._position_timer.stop()
        self._save_timer.stop()
        self._seek_timer.stop()
        payload = self.payload()
        self._closed = True
        if not payload:
            if not self._suppress_clear:
                self._clear()
            return
        self._suppress_clear = False
        # 退出路径：写失败再试一次（权限突然恢复、目录刚被释放都很常见），
        # 仍失败就明确留日志，绝不假装保存成功。
        if not self._write(payload):
            if not self._write(payload):
                log.error("退出时仍无法写入播放会话，本次进度可能丢失")
                return
        self._last_saved_position = payload.get("position_ms", -1)

    # ------------------------------------------------------------- internals
    def _on_current_changed(self, _track: object) -> None:
        self.schedule_save()

    def _on_position_changed(self, position: int) -> None:
        """拖动进度后尽快保存一次；正常播放推进只走 5 秒周期保存。"""
        position = int(position)
        previous = self._last_seen_position
        self._last_seen_position = position
        if previous < 0:
            return
        if abs(position - previous) > SEEK_JUMP_MS:
            # 只在「跳变」时重启计时器：正常每 100ms 一次的位置更新不会把它
            # 无限推迟，也就不会每 100ms 写一次 JSON。
            self._seek_timer.start()

    def _on_state_changed(self, state: str) -> None:
        if state == "playing":
            if not self._position_timer.isActive():
                self._position_timer.start()
        else:
            self._position_timer.stop()
            self.save_now()

    def _save_position_tick(self) -> None:
        position = int(self._controller.position)
        if abs(position - self._last_saved_position) < 2000:
            return
        self.save_now()

    def _read(self) -> dict[str, Any]:
        path = queue_file()
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            log.info("play queue file is unreadable, starting empty")
            return {}
        if not isinstance(payload, dict):
            return {}
        if int(payload.get("version") or 0) > STATE_VERSION:
            log.info("play queue version %s is newer, ignoring", payload.get("version"))
            return {}
        return payload

    def _write(self, payload: dict[str, Any]) -> bool:
        path = queue_file()
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except OSError:
            log.exception("cannot save play queue")
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    def _clear(self) -> None:
        try:
            os.remove(queue_file())
        except OSError:
            pass


__all__ = ["PlaybackKeeper", "queue_file"]
