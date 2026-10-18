"""Page scaffolding shared by every screen."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.icons import draw as draw_icon
from ...core.theme import css_rgba, Metrics, qcolor, rgba, theme
from ..widgets.common import IconButton, TextButton, apply_shadow


class PageHeader(QWidget):
    """Large page title with optional subtitle and trailing actions."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        *,
        large: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._large = large
        self.trailing = QWidget(self)
        self._trailing_layout = QHBoxLayout(self.trailing)
        self._trailing_layout.setContentsMargins(0, 0, 0, 0)
        self._trailing_layout.setSpacing(8)
        self._trailing_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setFixedHeight(72 if large else 56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def add_action(self, widget: QWidget) -> None:
        self._trailing_layout.addWidget(widget, 0, Qt.AlignVCenter)

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle = subtitle
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = max(150, min(self.width() // 2, self.trailing.sizeHint().width() + 6))
        self.trailing.setGeometry(self.width() - width, 0, width, self.height())

    def _text_width(self) -> int:
        return max(80, self.width() - self.trailing.sizeHint().width() - 22)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        title_font = theme().font(21.0 if self._large else 15.0, 700)
        metrics = QFontMetrics(title_font)
        width = self._text_width()
        title = metrics.elidedText(self._title, Qt.ElideRight, width)
        painter.setFont(title_font)
        painter.setPen(QPen(qcolor(palette.text)))
        if self._subtitle:
            painter.drawText(
                QRectF(0, 4, width, self.height() - 32),
                int(Qt.AlignLeft | Qt.AlignBottom),
                title,
            )
            sub_font = theme().font(9.4, 500)
            painter.setFont(sub_font)
            painter.setPen(QPen(rgba(palette.text, 0.5)))
            painter.drawText(
                QRectF(1, self.height() - 26, width, 18),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                QFontMetrics(sub_font).elidedText(self._subtitle, Qt.ElideRight, width),
            )
        else:
            painter.drawText(
                QRectF(0, 0, width, self.height()),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                title,
            )
        painter.end()


class Page(QWidget):
    """Base class: padded vertical layout plus lifecycle hooks."""

    route = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(Metrics.page_pad, 18, Metrics.page_pad, 10)
        self._layout.setSpacing(14)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._layout

    def on_show(self, payload: object = None) -> None:
        """Called when the page becomes visible."""

    def on_hide(self) -> None:
        """Called when the page is navigated away from."""

    def refresh_theme(self) -> None:
        self.update()

    def search(self, text: str) -> None:
        """Optional in-page filter hook."""


class ScrollPage(Page):
    """Page whose content lives inside a scroll area."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.container = QWidget()
        self.container.setAutoFillBackground(False)
        self.scroll.setWidget(self.container)
        self.body = QVBoxLayout(self.container)
        self.body.setContentsMargins(Metrics.page_pad, 0, Metrics.page_pad, 16)
        self.body.setSpacing(16)
        self._layout.addWidget(self.scroll, 1)

    def scroll_to_top(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)


class EmptyState(QWidget):
    """Centred icon + message + optional button, used for empty libraries."""

    action_clicked = Signal()

    def __init__(
        self,
        title: str = "还没有内容",
        description: str = "",
        *,
        icon_name: str = "music_note",
        action_text: str = "",
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._description = description
        self._icon = icon_name
        self._compact = compact
        self._action_text = action_text
        self.action: TextButton | None = None
        if action_text:
            self.action = TextButton(action_text, accent=True, size=32)
            self.action.setParent(self)
            self.action.clicked.connect(self.action_clicked)
        self.setMinimumHeight(150 if compact else 260)

    def set_text(self, title: str, description: str = "") -> None:
        self._title = title
        self._description = description
        self.update()

    def set_action_text(self, text: str) -> None:
        self._action_text = text
        if self.action is not None:
            self.action.set_text(text)
            self.action.setVisible(bool(text))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.action is not None:
            hint = self.action.sizeHint()
            self.action.setGeometry(
                (self.width() - hint.width()) // 2,
                int(self.height() / 2) + 58,
                hint.width(),
                hint.height(),
            )

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        center_y = self.height() / 2 - (20 if self._compact else 40)
        icon_size = 40 if self._compact else 52
        draw_icon(
            painter,
            self._icon,
            QRectF(self.width() / 2 - icon_size / 2, center_y - icon_size, icon_size, icon_size),
            rgba(palette.text, 0.16),
        )
        title_font = theme().font(11.0 if self._compact else 13.0, 600)
        painter.setFont(title_font)
        painter.setPen(QPen(rgba(palette.text, 0.62)))
        painter.drawText(
            QRectF(20, center_y + 2, self.width() - 40, 26),
            int(Qt.AlignHCenter | Qt.AlignTop),
            self._title,
        )
        if self._description:
            sub_font = theme().font(9.2, 400)
            painter.setFont(sub_font)
            painter.setPen(QPen(rgba(palette.text, 0.40)))
            painter.drawText(
                QRectF(40, center_y + 30, self.width() - 80, 40),
                int(Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap),
                self._description,
            )
        painter.end()


class Card(QFrame):
    """Rounded surface used by settings groups and detail panels."""

    def __init__(self, parent: QWidget | None = None, *, radius: int = Metrics.radius_lg) -> None:
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(rgba(palette.border, 0.9), 1))
        painter.setBrush(qcolor(palette.surface))
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class BackButton(IconButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("chevron_left", size=30, icon_size=16, tooltip="返回", parent=parent)


def hline() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    line.setStyleSheet(f"background:{css_rgba(theme().palette.border, 0.7)};")
    return line


__all__ = [
    "BackButton",
    "Card",
    "EmptyState",
    "Page",
    "PageHeader",
    "ScrollPage",
    "hline",
]

