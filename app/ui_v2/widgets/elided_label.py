"""A QLabel that keeps full text available through a tooltip."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    def __init__(self, parent: QWidget | None = None, *, max_lines: int = 1) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._max_lines = max(1, int(max_lines))
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(self._max_lines > 1)
        if self._max_lines > 1:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_text()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        available = max(0, self.contentsRect().width())
        metrics = QFontMetrics(self.font())
        if self._max_lines == 1:
            self.setText(metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available))
            return

        if not self._full_text:
            self.setText("")
            return
        remaining = self._full_text.strip()
        lines: list[str] = []
        for line_index in range(self._max_lines):
            if not remaining:
                break
            if line_index == self._max_lines - 1:
                lines.append(metrics.elidedText(remaining, Qt.TextElideMode.ElideRight, available))
                break
            low, high, best = 1, len(remaining), 1
            while low <= high:
                middle = (low + high) // 2
                if metrics.horizontalAdvance(remaining[:middle]) <= available:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            # Prefer a word boundary for Latin titles so a normal title does
            # not split in the middle of a word merely because two lines are
            # available.  CJK titles naturally fall back to character breaks.
            boundary = remaining.rfind(" ", 0, best + 1)
            if boundary > 0:
                best = boundary
            lines.append(remaining[:best].rstrip())
            remaining = remaining[best:].lstrip()
        self.setText("\n".join(lines))
        line_height = metrics.lineSpacing()
        self.setMinimumHeight(line_height * min(self._max_lines, max(1, len(lines))) + 2)
        self.setMaximumHeight(line_height * self._max_lines + 4)
