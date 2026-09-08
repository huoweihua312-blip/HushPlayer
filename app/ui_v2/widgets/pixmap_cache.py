"""Bounded, UI-thread-only caches for decoded and scaled cover pixmaps."""

from collections import OrderedDict
from collections.abc import Hashable

from PySide6.QtGui import QPixmap


class PixmapCache:
    """Evict least recently used images by estimated pixel bytes and count.

    The budget covers retained pixel buffers, not Qt/GPU allocation overhead
    or pixmaps still referenced by visible widgets.
    """

    def __init__(self, max_bytes: int, max_entries: int) -> None:
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, tuple[QPixmap, int]] = OrderedDict()
        self.used_bytes = 0

    def get(self, key: Hashable) -> QPixmap | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[0]

    def put(self, key: Hashable, pixmap: QPixmap) -> None:
        previous = self._entries.pop(key, None)
        if previous is not None:
            self.used_bytes -= previous[1]
        cost = pixmap.width() * pixmap.height() * max(1, (pixmap.depth() + 7) // 8)
        if pixmap.isNull() or cost > self.max_bytes or self.max_entries <= 0:
            return
        self._entries[key] = (pixmap, cost)
        self.used_bytes += cost
        while self.used_bytes > self.max_bytes or len(self._entries) > self.max_entries:
            _, (_, removed_cost) = self._entries.popitem(last=False)
            self.used_bytes -= removed_cost

    def clear(self) -> None:
        self._entries.clear()
        self.used_bytes = 0
