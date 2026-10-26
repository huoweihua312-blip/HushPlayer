"""播放队列。

核心不变量（避免「界面显示随机播放但实际顺序不一致」这类问题）：
* ``_items`` 是用户看到的队列顺序；
* ``_order`` 是实际播放顺序，元素为 track id；
* 非随机时 ``_order`` 始终等于 ``_items`` 的 id 序列；
* 开随机时 ``_order`` 以当前曲目为首，其余随机打乱，并随增删实时同步。

因此任何一次「下一首」都能在界面上被精确预告（见 ``upcoming``）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from ..core.logging_setup import get_logger
from ..model.track import Track

log = get_logger("queue")

REPEAT_MODES = ("off", "all", "one")


@dataclass
class QueueSnapshot:
    context: str = ""
    position_ms: int = 0
    shuffle: bool = False
    repeat: str = "off"


class PlayQueue(QObject):
    changed = Signal()  # 队列内容变化
    current_changed = Signal(object)  # Track | None
    mode_changed = Signal()  # 随机 / 循环

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[Track] = []
        self._order: list[str] = []
        self._pos: int = -1
        self._by_id: dict[str, Track] = {}
        self._shuffle = False
        self._repeat = "off"
        self._context = ""
        self._rng = random.Random()

    # ------------------------------------------------------------------ 查询
    @property
    def items(self) -> list[Track]:
        return list(self._items)

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> str:
        return self._repeat

    @property
    def context(self) -> str:
        return self._context

    @property
    def current(self) -> Track | None:
        if 0 <= self._pos < len(self._order):
            return self._by_id.get(self._order[self._pos])
        return None

    @property
    def current_row(self) -> int:
        """当前曲目在 ``items``（界面行）中的位置，-1 表示无。"""
        track = self.current
        if track is None:
            return -1
        for index, item in enumerate(self._items):
            if item.id == track.id:
                return index
        return -1

    @property
    def current_order_pos(self) -> int:
        return self._pos

    def row_of(self, track_id: str) -> int:
        for index, item in enumerate(self._items):
            if item.id == track_id:
                return index
        return -1

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def is_current(self, track_id: str) -> bool:
        current = self.current
        return bool(current and current.id == track_id)

    def find(self, track_id: str) -> Track | None:
        return self._by_id.get(track_id)

    def upcoming(self, limit: int = 0) -> list[Track]:
        """按实际播放顺序返回当前曲目之后将播放的曲目。"""
        result: list[Track] = []
        if not self._order or self._pos < 0:
            return result
        total = len(self._order)
        current = self.current
        current_id = current.id if current else ""
        index = self._pos
        for _ in range(total + 1):
            index += 1
            if index >= total:
                if self._repeat == "all":
                    index = 0
                else:
                    break
            track = self._by_id.get(self._order[index])
            if track is None or track.id == current_id:
                break
            result.append(track)
            if limit and len(result) >= limit:
                break
        return result

    # ------------------------------------------------------------------ 队列内容
    def set_tracks(
        self, tracks: list[Track], start_index: int = 0, context: str = ""
    ) -> None:
        self._items = [track for track in tracks if track is not None]
        self._by_id = {track.id: track for track in self._items}
        self._context = context
        if not self._items:
            self._order = []
            self._pos = -1
            self.current_changed.emit(None)
            self.changed.emit()
            return
        start_index = max(0, min(start_index, len(self._items) - 1))
        self._order = [track.id for track in self._items]
        if self._shuffle:
            picked = self._items[start_index].id
            self._reshuffle(keep_current=False)
            if picked in self._order:
                self._order.remove(picked)
                self._order.insert(0, picked)
            self._pos = 0
        else:
            self._pos = start_index
        self.changed.emit()
        self.current_changed.emit(self.current)

    def replace_track(self, track: Track) -> bool:
        """用同一 ``id`` 的新记录替换队列里的旧对象（来源替换后同步）。"""

        for index, old in enumerate(self._items):
            if old.id != track.id:
                continue
            self._items[index] = track
            self._by_id[track.id] = track
            self.changed.emit()
            if self.current is not None and self.current.id == track.id:
                self.current_changed.emit(track)
            return True
        return False

    def append(self, tracks: list[Track]) -> int:
        added = [track for track in tracks if track is not None]
        if not added:
            return 0
        for track in added:
            self._items.append(track)
            self._by_id[track.id] = track
            # 追加的歌曲一律排在播放顺序末尾：随机模式下不打乱已经预告的 upcoming
            self._order.append(track.id)
        if self._pos < 0 and self._items:
            self._pos = 0
        self.changed.emit()
        return len(added)

    def insert_next(self, tracks: list[Track]) -> int:
        """插入到当前曲目之后（“下一首播放”）。"""
        added = [track for track in tracks if track is not None]
        if not added:
            return 0
        current = self.current
        base = self.current_row
        insert_row = base + 1 if base >= 0 else len(self._items)
        for offset, track in enumerate(added):
            self._items.insert(insert_row + offset, track)
            self._by_id[track.id] = track
        if self._shuffle:
            for offset, track in enumerate(added):
                self._order.insert(self._pos + 1 + offset, track.id)
        else:
            self._order = [track.id for track in self._items]
        self._pos = self._order.index(current.id) if current and current.id in self._order else (0 if self._order else -1)
        self.changed.emit()
        return len(added)

    def remove_rows(self, rows: list[int]) -> None:
        rows = sorted({row for row in rows if 0 <= row < len(self._items)}, reverse=True)
        if not rows:
            return
        current = self.current
        current_before = current.id if current else None
        for row in rows:
            track = self._items.pop(row)
            self._by_id.pop(track.id, None)
            if track.id in self._order:
                order_index = self._order.index(track.id)
                del self._order[order_index]
                if order_index < self._pos:
                    self._pos -= 1
        if not self._items:
            self._pos = -1
        elif self._pos >= len(self._order):
            self._pos = len(self._order) - 1
        self.changed.emit()
        if current_before != (self.current.id if self.current else None):
            self.current_changed.emit(self.current)

    def remove_ids(self, track_ids: list[str]) -> int:
        rows = [self.row_of(track_id) for track_id in track_ids]
        rows = [row for row in rows if row >= 0]
        self.remove_rows(rows)
        return len(rows)

    def move_row(self, from_row: int, to_row: int) -> bool:
        if from_row == to_row:
            return False
        if not (0 <= from_row < len(self._items)):
            return False
        to_row = max(0, min(to_row, len(self._items) - 1))
        current = self.current
        track = self._items.pop(from_row)
        self._items.insert(to_row, track)
        if not self._shuffle:
            self._order = [item.id for item in self._items]
        else:
            order_from = self._order.index(track.id) if track.id in self._order else -1
            if order_from >= 0:
                self._order.pop(order_from)
                self._order.insert(max(0, min(to_row, len(self._order))), track.id)
        self._pos = self._order.index(current.id) if current and current.id in self._order else -1
        self.changed.emit()
        return True

    def clear(self) -> None:
        self._items = []
        self._by_id = {}
        self._order = []
        self._pos = -1
        self._context = ""
        self.changed.emit()
        self.current_changed.emit(None)

    def set_current_row(self, row: int) -> Track | None:
        track = self.track_at(row)
        if track is None:
            return None
        if track.id in self._order:
            self._pos = self._order.index(track.id)
        else:
            self._order.append(track.id)
            self._pos = len(self._order) - 1
        self.current_changed.emit(track)
        return track

    def set_current_track(self, track: Track) -> Track | None:
        row = self.row_of(track.id)
        if row < 0:
            self.append([track])
            row = self.row_of(track.id)
        return self.set_current_row(row)

    # ------------------------------------------------------------------ 模式
    def set_shuffle(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._shuffle:
            return
        self._shuffle = enabled
        if enabled:
            self._reshuffle(keep_current=True)
        else:
            current = self.current
            self._order = [track.id for track in self._items]
            self._pos = self._order.index(current.id) if current and current.id in self._order else -1
        self.mode_changed.emit()
        self.changed.emit()

    def set_repeat(self, mode: str) -> None:
        if mode not in REPEAT_MODES:
            mode = "off"
        if mode == self._repeat:
            return
        self._repeat = mode
        self.mode_changed.emit()
        self.changed.emit()

    def cycle_repeat(self) -> str:
        order = {"off": "all", "all": "one", "one": "off"}
        self.set_repeat(order.get(self._repeat, "off"))
        return self._repeat

    def toggle_shuffle(self) -> bool:
        self.set_shuffle(not self._shuffle)
        return self._shuffle

    def _reshuffle(self, keep_current: bool) -> None:
        current_id = self.current.id if (keep_current and self.current) else None
        ids = [track.id for track in self._items]
        if current_id and current_id in ids:
            ids.remove(current_id)
            self._rng.shuffle(ids)
            self._order = [current_id] + ids
            self._pos = 0
        else:
            self._rng.shuffle(ids)
            self._order = ids
            self._pos = 0 if ids else -1

    # ------------------------------------------------------------------ 前进/后退
    def next_track(self, *, auto: bool = False) -> Track | None:
        if not self._order:
            return None
        if auto and self._repeat == "one":
            return self.current
        if self._pos + 1 < len(self._order):
            self._pos += 1
        elif self._repeat == "all":
            if self._shuffle:
                ids = [track.id for track in self._items]
                self._rng.shuffle(ids)
                if len(ids) > 1 and self.current and ids[0] == self.current.id:
                    ids.append(ids.pop(0))
                self._order = ids
            self._pos = 0
        elif auto:
            return None
        else:
            self._pos = 0
        track = self.current
        self.current_changed.emit(track)
        return track

    def previous_track(self, *, auto: bool = False) -> Track | None:
        if not self._order:
            return None
        if auto and self._repeat == "one":
            return self.current
        if self._pos > 0:
            self._pos -= 1
        elif self._repeat == "all" or not auto:
            self._pos = len(self._order) - 1
        else:
            return None
        track = self.current
        self.current_changed.emit(track)
        return track

    # ------------------------------------------------------------------ 快照
    def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            context=self._context,
            position_ms=0,
            shuffle=self._shuffle,
            repeat=self._repeat,
        )

    def to_dict(self) -> dict:
        return {
            "context": self._context,
            "current_row": self.current_row,
            "shuffle": self._shuffle,
            "repeat": self._repeat,
            "order": list(self._order),
            "items": [track.id for track in self._items],
            "tracks": [track.to_dict() for track in self._items],
        }

    def restore(self, payload: dict, resolver=None) -> int:
        """从会话快照恢复队列。``resolver`` 用于从数据库补齐 Track。"""
        if not payload:
            return 0
        raw_tracks = payload.get("tracks") or []
        tracks: list[Track] = []
        #: 原始行号 → 恢复后的 Track。部分歌曲已不存在时，行号会整体前移，
        #: 直接按 index 取当前曲会选到别的歌；这里保留原始行的映射。
        row_map: dict[int, Track] = {}
        for raw_index, item in enumerate(raw_tracks):
            if not isinstance(item, dict):
                continue
            if resolver is not None:
                restored = resolver(item.get("id", ""))
                if restored is None:
                    # 文件已被删除 / 在线曲目已失效：恢复到队列时跳过
                    continue
                tracks.append(restored)
            else:
                tracks.append(Track.from_dict(item))
            row_map[raw_index] = tracks[-1]
        if not tracks:
            return 0
        self._items = tracks
        self._by_id = {track.id: track for track in tracks}
        self._context = payload.get("context", "")
        self._shuffle = bool(payload.get("shuffle", False))
        self._repeat = payload.get("repeat", "off")
        if self._repeat not in REPEAT_MODES:
            self._repeat = "off"
        order = [track_id for track_id in payload.get("order", []) if track_id in self._by_id]
        if not order:
            order = [track.id for track in tracks]
        self._order = order
        current = self._restored_current(payload, row_map, tracks)
        if current.id in order:
            self._pos = order.index(current.id)
        else:
            # 播放顺序里没有当前曲（旧快照缺少 order）：补到首位，别让
            # current 变成另一首歌。
            order.insert(0, current.id)
            self._order = order
            self._pos = 0
        self.changed.emit()
        self.current_changed.emit(self.current)
        return len(tracks)

    def _restored_current(self, payload: dict, row_map: dict[int, Track],
                          tracks: list[Track]) -> Track:
        """决定恢复后的当前曲：优先 current_id，其次原始行号（含漂移映射）。"""
        current_id = str(payload.get("current_id") or "")
        if current_id and current_id in self._by_id:
            return self._by_id[current_id]
        try:
            raw_row = int(payload.get("current_row", 0))
        except (TypeError, ValueError):
            raw_row = 0
        if raw_row in row_map:
            return row_map[raw_row]
        if row_map:
            # 原行对应的歌已缺失：取原始行号最近的一首，而不是把行号 clamp 到末尾。
            nearest = min(row_map, key=lambda index: (abs(index - raw_row), index))
            return row_map[nearest]
        return tracks[0]
