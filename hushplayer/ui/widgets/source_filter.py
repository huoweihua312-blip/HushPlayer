"""Horizontal source filter pills used by the online search page.

Mirrors the original HushPlayer search header: one pill per playback source
plus an "all sources" pill, with the result count of each source rendered as a
muted suffix after a search completes.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from ...core.theme import css_rgba, theme
from .menu import themed_menu

__all__ = ["SourceFilterBar", "HistoryChips"]


class _Pill(QPushButton):
    def __init__(self, key: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.key = key
        self._count = 0
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setFixedHeight(26)
        self._apply_style()

    def set_count(self, count: int) -> None:
        self._count = max(0, int(count))
        self._apply_style()

    def _text(self) -> str:
        base = self.property("baseLabel") or self.text()
        self.setProperty("baseLabel", base)
        return f"{base} {self._count}" if self._count else base

    def _apply_style(self) -> None:
        palette = theme().palette
        self.setText(self._text())
        checked = self.isChecked()
        # A pill's label grows when a result count is appended; Qt does not
        # recompute the size hint for a text change made in a stylesheet-only
        # update, so reserve the room explicitly or the count gets clipped.
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(self.text()) + 26)
        bg = css_rgba(palette.accent, 0.16) if checked else css_rgba(palette.text, 0.055)
        fg = palette.accent if checked else css_rgba(palette.text, 0.72)
        border = css_rgba(palette.accent, 0.55) if checked else "transparent"
        self.setStyleSheet(
            "QPushButton {"
            f" background: {bg}; color: {fg}; border: 1px solid {border};"
            " border-radius: 13px; padding: 0 12px; font-size: 9pt;"
            "}"
            f"QPushButton:hover {{ background: {css_rgba(palette.text, 0.09)}; }}"
        )


class SourceFilterBar(QWidget):
    """A row of pills; ``changed`` carries the selected source id ('' = all)."""

    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pills: dict[str, _Pill] = {}
        self._labels: dict[str, str] = {}
        self._counts: dict[str, int] = {}
        self._current = ""
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._scroll = QScrollArea(self)
        # Keep the natural width: with dozens of sources the pills must scroll
        # horizontally instead of being squeezed into unreadable slivers.
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(30)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._holder = QWidget()
        self._holder.setStyleSheet("background:transparent;")
        self._row = QHBoxLayout(self._holder)
        self._row.setContentsMargins(0, 2, 0, 2)
        self._row.setSpacing(8)
        self._row.addStretch(1)
        self._scroll.setWidget(self._holder)
        outer.addWidget(self._scroll, 1)
        # With dozens of plugins the pill row alone is not discoverable: this
        # menu always lists every source (with its result count) for filtering.
        from .common import TextButton

        self._more = TextButton("更多音源", icon_name="chevron_down", size=30)
        self._more.setToolTip("按音源筛选（全部音源都在这里）")
        self._more.clicked.connect(self._show_all_sources_menu)
        outer.addWidget(self._more, 0, Qt.AlignVCenter)

    # ------------------------------------------------------------------ api
    def set_sources(self, sources: list[tuple[str, str]]) -> None:
        """``sources`` is a list of ``(id, label)``; the all-sources pill first."""
        wanted = [("", "全部音源")] + [(str(sid), str(label)) for sid, label in sources]
        existing = list(self._pills.values())
        for pill in existing:
            pill.setParent(None)
            pill.deleteLater()
        self._pills.clear()
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._labels = {key: label for key, label in wanted}
        for key, label in wanted:
            pill = _Pill(key, label)
            pill.setProperty("baseLabel", label)
            pill.clicked.connect(lambda _=False, k=key: self.set_current(k, emit=True))
            self._pills[key] = pill
            self._row.addWidget(pill)
        self._row.addStretch(1)
        self.set_counts({})
        self.set_current(self._current if self._current in self._pills else "", emit=False)
        self._holder.adjustSize()

    def wheelEvent(self, event) -> None:  # noqa: N802
        bar = self._scroll.horizontalScrollBar()
        if bar.maximum() > 0:
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = dict(counts)
        for key, pill in self._pills.items():
            pill.set_count(counts.get(key, 0))
        # Hide sources that returned nothing, so a 64-plugin setup stays short;
        # the "more" menu still exposes every source.
        any_results = any(value > 0 for key, value in counts.items() if key)
        for index, (key, pill) in enumerate(self._pills.items()):
            if not any_results:
                pill.setVisible(index < 12 or key == self._current)
                continue
            pill.setVisible(key == "" or key == self._current or counts.get(key, 0) > 0)
        if hasattr(self, "_more"):
            # The overflow menu is pointless when every source already fits.
            hidden = [key for key, pill in self._pills.items() if not pill.isVisible()]
            self._more.setVisible(bool(hidden) or len(self._pills) > 9)
        if hasattr(self, "_holder"):
            self._holder.adjustSize()

    def _show_all_sources_menu(self) -> None:
        menu = themed_menu(self)
        for key, label in self._labels.items():
            count = self._counts.get(key, 0)
            text = f"{label}（{count}）" if count else label
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(key == self._current)
            action.triggered.connect(lambda _=False, k=key: self.set_current(k, emit=True))
        menu.exec(self._more.mapToGlobal(self._more.rect().bottomLeft()))

    def set_current(self, key: str, *, emit: bool = False) -> None:
        if key not in self._pills:
            key = ""
        if key in self._pills:
            self._pills[key].setVisible(True)
        self._current = key
        for pill_key, pill in self._pills.items():
            pill.setChecked(pill_key == key)
            pill._apply_style()
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        return self._current

    def refresh_theme(self) -> None:
        for pill in self._pills.values():
            pill._apply_style()


class HistoryChips(QWidget):
    """Recent online queries shown while the search box is empty."""

    requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self._row.addStretch(1)
        self._label = None
        self._items: list[str] = []

    def items(self) -> list[str]:
        return list(self._items)

    def set_history(self, items: list[str]) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._items = list(items)
        if not items:
            self.setVisible(False)
            return
        from .common import Chip

        label = Chip("最近搜索")
        label.setCursor(Qt.ArrowCursor)
        self._row.addWidget(label)
        for text in items[:8]:
            pill = _Pill(text, text)
            pill.setProperty("baseLabel", text)
            pill.set_checkable = False  # type: ignore[assignment]
            pill.setCheckable(False)
            pill.clicked.connect(lambda _=False, q=text: self.requested.emit(q))
            self._row.addWidget(pill)
        self._row.addStretch(1)
        self.setVisible(True)

    def refresh_theme(self) -> None:
        for child in self.findChildren(_Pill):
            child._apply_style()
