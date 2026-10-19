"""Search field and segmented control."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from ...core.icons import draw as draw_icon, icon as make_icon
from ...core.theme import css_rgba, qcolor, rgba, theme
from .common import HoverAnimation, IconButton


class SearchField(QWidget):
    text_changed = Signal(str)
    submitted = Signal(str)

    def __init__(
        self,
        placeholder: str = "搜索歌曲、专辑或歌手",
        *,
        width: int = 280,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._focus = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_focus_value)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(180)
        self._debounce.timeout.connect(self._emit_changed)

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName("搜索")
        self.setAccessibleName("搜索")
        self.edit.setFrame(False)
        self.edit.setStyleSheet("QLineEdit{background:transparent;border:none;padding:0;}")
        self.edit.setClearButtonEnabled(False)
        self.edit.textChanged.connect(lambda _text: self._debounce.start())
        self.edit.returnPressed.connect(self._on_submit)
        self.edit.installEventFilter(self)
        # BUG(R2-02): without a parent the clear button became its own
        # top-level window, so typing in the search box popped a small ghost
        # frame next to the window.
        self.clear_button = IconButton("close", size=20, icon_size=11, tooltip="清除", parent=self)
        self.clear_button.clicked.connect(self.clear)
        self.clear_button.setVisible(False)
        self.setFixedHeight(32)
        self.setMinimumWidth(160)
        self._preferred_width = width
        self.setCursor(Qt.IBeamCursor)
        self.setFocusPolicy(Qt.NoFocus)

    # ------------------------------------------------------------------- api
    def text(self) -> str:
        return self.edit.text()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)
        self._sync_clear()

    def clear(self) -> None:
        if not self.edit.text():
            return
        self.edit.clear()
        self._sync_clear()
        self.text_changed.emit("")

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.edit.setPlaceholderText(text)

    def focus(self) -> None:
        self.edit.setFocus(Qt.ShortcutFocusReason)
        self.edit.selectAll()

    def _on_submit(self) -> None:
        self._debounce.stop()
        self.submitted.emit(self.edit.text())

    def _emit_changed(self) -> None:
        self._sync_clear()
        self.text_changed.emit(self.edit.text())

    def _sync_clear(self) -> None:
        self.clear_button.setVisible(bool(self.edit.text()))

    def _on_focus_value(self, value) -> None:
        self._focus = float(value)
        self.update()

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.edit:
            if event.type() == event.Type.FocusIn:
                self._animate(1.0)
            elif event.type() == event.Type.FocusOut:
                self._animate(0.0)
        return super().eventFilter(watched, event)

    def _animate(self, target: float) -> None:
        if theme().reduce_motion:
            self._on_focus_value(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._focus)
        self._animation.setEndValue(target)
        self._animation.start()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.focus()
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        height = self.height()
        self.clear_button.move(self.width() - 28, (height - 20) // 2)
        left = 34
        right = self.width() - (34 if self.clear_button.isVisible() else 12)
        self.edit.setGeometry(left, 0, max(20, right - left), height)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._preferred_width, 32)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        base = rgba(palette.text, 0.05 if palette.is_dark else 0.04)
        fill = rgba(palette.text, base.alphaF() + 0.03 * self._focus)
        painter.setPen(QPen(rgba(palette.accent, 0.15 + 0.5 * self._focus), 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        icon_color = rgba(palette.accent if self._focus > 0.5 else palette.text, 0.5 + 0.35 * self._focus)
        draw_icon(painter, "search", QRectF(12, (self.height() - 15) / 2, 15, 15), icon_color)
        painter.end()
        self.edit.setStyleSheet(
            "QLineEdit{background:transparent;border:none;padding:0;color:%s;"
            "selection-background-color:%s;}"
            % (palette.text, css_rgba(palette.accent, 0.35))
        )


class SegmentedControl(QWidget):
    changed = Signal(int)

    def __init__(
        self,
        items: list[str] | None = None,
        *,
        height: int = 30,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items = list(items or [])
        self._index = 0
        self._hover = -1
        self._indicator = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_indicator)
        self.setMouseTracking(True)
        self.setFixedHeight(height)
        self.setCursor(Qt.PointingHandCursor)
        self._update_width()

    def set_items(self, items: list[str]) -> None:
        self._items = list(items)
        self._index = min(self._index, max(0, len(self._items) - 1))
        self._update_width()
        self.update()

    def set_current(self, index: int, *, emit: bool = False) -> None:
        index = max(0, min(index, len(self._items) - 1)) if self._items else 0
        if index == self._index:
            return
        self._index = index
        self._animate_indicator()
        self.update()
        if emit:
            self.changed.emit(index)

    def current(self) -> int:
        return self._index

    def _segment_width(self) -> float:
        return max(64.0, max(
            (QFontMetrics(theme().font(9.0, 600)).horizontalAdvance(item) + 34 for item in self._items),
            default=64.0,
        ))

    def _update_width(self) -> None:
        self.setFixedWidth(int(self._segment_width() * max(1, len(self._items)) + 6))

    def _on_indicator(self, value) -> None:
        self._indicator = float(value)
        self.update()

    def _animate_indicator(self) -> None:
        if theme().reduce_motion:
            self._on_indicator(float(self._index))
            return
        self._animation.stop()
        self._animation.setStartValue(self._indicator)
        self._animation.setEndValue(float(self._index))
        self._animation.start()

    def _index_at(self, x: float) -> int:
        if not self._items:
            return -1
        width = self._segment_width()
        index = int((x - 3) // width)
        return index if 0 <= index < len(self._items) else -1

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            index = self._index_at(event.position().x())
            if index >= 0:
                self.set_current(index, emit=True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position().x())
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(palette.text, 0.06))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        if not self._items:
            painter.end()
            return
        width = self._segment_width()
        indicator = QRectF(
            3 + width * self._indicator,
            3,
            width,
            rect.height() - 6,
        )
        painter.setBrush(qcolor(palette.elevated if palette.is_dark else "#FFFFFF"))
        painter.setPen(QPen(rgba(palette.text, 0.06), 1))
        painter.drawRoundedRect(indicator, indicator.height() / 2, indicator.height() / 2)
        font = theme().font(9.0, 600)
        painter.setFont(font)
        for index, item in enumerate(self._items):
            segment = QRectF(3 + width * index, 0, width, self.height())
            if index == self._index:
                color = palette.accent
            elif index == self._hover:
                color = rgba(palette.text, 0.9)
            else:
                color = rgba(palette.text, 0.55)
            painter.setPen(QPen(qcolor(color)))
            painter.drawText(segment, int(Qt.AlignCenter), item)
        painter.end()


__all__ = ["SearchField", "SegmentedControl"]
