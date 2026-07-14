from __future__ import annotations

import random
from collections.abc import Iterable

from app.models.playback_queue_item import PlaybackQueueItem


class PlaybackQueue:
    """Mixed local/remote context queue with stable shuffle history."""

    VALID_MODES = {"sequence", "list_loop", "single_loop", "shuffle"}

    def __init__(self, randomizer: random.Random | None = None) -> None:
        self.items: list[PlaybackQueueItem] = []
        self.current_index = -1
        self._random = randomizer or random.Random()
        self._shuffle_history: list[str] = []
        self._shuffle_cursor = -1
        self._shuffle_remaining: list[str] = []

    @property
    def current_item(self) -> PlaybackQueueItem | None:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    @property
    def current_identity(self) -> str:
        item = self.current_item
        return item.stable_identity if item is not None else ""

    @property
    def shuffle_history(self) -> tuple[str, ...]:
        return tuple(self._shuffle_history)

    def clear(self) -> None:
        self.items = []
        self.current_index = -1
        self._reset_shuffle("")

    def replace(
        self,
        values: Iterable[PlaybackQueueItem],
        current_identity: str = "",
    ) -> None:
        unique: list[PlaybackQueueItem] = []
        seen: set[str] = set()
        for value in values:
            item = PlaybackQueueItem.from_value(value)
            identity = item.stable_identity
            if not identity or identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
        self.items = unique
        self.current_index = self.index_for_identity(current_identity)
        if self.current_index < 0 and self.items:
            self.current_index = 0
        self._reset_shuffle(self.current_identity)

    def index_for_identity(self, identity: str) -> int:
        identity = str(identity or "")
        for index, item in enumerate(self.items):
            if item.stable_identity == identity:
                return index
        return -1

    def set_current_identity(self, identity: str) -> bool:
        index = self.index_for_identity(identity)
        if index < 0:
            return False
        self.current_index = index
        self._sync_shuffle_identity(identity)
        return True

    def set_current_index(self, index: int) -> bool:
        if index < 0 or index >= len(self.items):
            return False
        self.current_index = index
        self._sync_shuffle_identity(self.current_identity)
        return True

    def next_index(self, mode: str, direction: int = 1) -> int | None:
        if not self.items:
            return None
        if self.current_index < 0:
            self.current_index = 0
        mode = mode if mode in self.VALID_MODES else "list_loop"
        if mode == "single_loop":
            return self.current_index
        if mode == "shuffle":
            return self._shuffle_index(direction)

        step = 1 if direction >= 0 else -1
        target = self.current_index + step
        if 0 <= target < len(self.items):
            self.current_index = target
            return target
        if mode == "list_loop":
            self.current_index = 0 if step > 0 else len(self.items) - 1
            return self.current_index
        return None

    def _reset_shuffle(self, current_identity: str) -> None:
        self._shuffle_history = [current_identity] if current_identity else []
        self._shuffle_cursor = 0 if current_identity else -1
        self._shuffle_remaining = [
            item.stable_identity
            for item in self.items
            if item.stable_identity != current_identity
        ]
        self._random.shuffle(self._shuffle_remaining)

    def _sync_shuffle_identity(self, identity: str) -> None:
        if not identity:
            return
        if (
            0 <= self._shuffle_cursor < len(self._shuffle_history)
            and self._shuffle_history[self._shuffle_cursor] == identity
        ):
            return
        if identity in self._shuffle_history:
            self._shuffle_cursor = self._shuffle_history.index(identity)
            return
        self._shuffle_history = self._shuffle_history[: self._shuffle_cursor + 1]
        self._shuffle_history.append(identity)
        self._shuffle_cursor = len(self._shuffle_history) - 1
        self._shuffle_remaining = [
            value for value in self._shuffle_remaining if value != identity
        ]

    def _shuffle_index(self, direction: int) -> int | None:
        current_identity = self.current_identity
        self._sync_shuffle_identity(current_identity)

        if direction < 0:
            if self._shuffle_cursor <= 0:
                return None
            self._shuffle_cursor -= 1
            identity = self._shuffle_history[self._shuffle_cursor]
            index = self.index_for_identity(identity)
            if index >= 0:
                self.current_index = index
                return index
            return None

        if self._shuffle_cursor + 1 < len(self._shuffle_history):
            self._shuffle_cursor += 1
            identity = self._shuffle_history[self._shuffle_cursor]
        else:
            if not self._shuffle_remaining:
                if len(self.items) <= 1:
                    return self.current_index
                self._shuffle_remaining = [
                    item.stable_identity
                    for item in self.items
                    if item.stable_identity != current_identity
                ]
                self._random.shuffle(self._shuffle_remaining)
            identity = self._shuffle_remaining.pop()
            self._shuffle_history = self._shuffle_history[: self._shuffle_cursor + 1]
            self._shuffle_history.append(identity)
            self._shuffle_cursor += 1

        index = self.index_for_identity(identity)
        if index < 0:
            return None
        self.current_index = index
        return index
