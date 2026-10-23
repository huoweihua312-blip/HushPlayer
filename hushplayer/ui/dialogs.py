"""Self-drawn dialogs.

Windows' native message boxes ignore the app palette (light caption on a dark
app, blue system text, square corners).  Everything the player asks the user is
therefore rendered with the same primitives as the rest of the UI: rounded
card, 11pt/600 title, 9.6pt body and our own buttons.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.icons import draw as draw_icon
from ..core.theme import rgba, theme
from .widgets.common import IconButton, TextButton

_CARD_BG = "surface"
_RADIUS = 14
_PAD = 22
_GAP = 14

_KIND_ICONS = {
    "info": ("info", "accent"),
    "question": ("info", "accent"),
    "warning": ("warning", "warning"),
    "error": ("warning", "danger"),
    "success": ("check", "success"),
}


class _Caption(QWidget):
    """Drag handle + title + close button."""

    def __init__(self, title: str, dialog: "CardDialog") -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._title = title
        self.setFixedHeight(theme().scaled(46, factor=0.7))
        self.close_button = IconButton(
            "close", size=26, icon_size=14, tooltip="关闭", parent=self
        )
        self.close_button.clicked.connect(dialog.reject)
        self._drag: QPoint | None = None

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, theme().scaled(46, factor=0.7))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.close_button.move(self.width() - self.close_button.width() - 10, (self.height() - self.close_button.height()) // 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = theme().palette
        font = theme().font(11.0, 600)
        painter.setFont(font)
        painter.setPen(QColor(palette.text))
        rect = self.rect().adjusted(_PAD, 0, -self.close_button.width() - 18, 0)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, self._title)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self._dialog.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self._dialog.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None


class CardDialog(QDialog):
    """Frameless, masked card dialog used for every in-app prompt."""

    def __init__(self, parent: QWidget | None, title: str, *, width: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setObjectName("HushDialogRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._base_width = theme().scaled(width or 420, factor=0.8)
        self._card = QWidget(self)
        self._card.setObjectName("HushDialogCard")
        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.caption = _Caption(title, self)
        layout.addWidget(self.caption)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(_PAD, 0, _PAD, 0)
        self.body.setSpacing(_GAP)
        layout.addLayout(self.body)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(_PAD, 6, _PAD, _PAD)
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        layout.addLayout(self.footer)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self._apply_theme()

    # ------------------------------------------------------------------ theme
    def _apply_theme(self) -> None:
        palette = theme().palette
        bg = getattr(palette, _CARD_BG, palette.surface)
        self._card.setStyleSheet(
            f"""
            QWidget#HushDialogCard {{
                background: {bg};
                border: 1px solid {rgba(palette.text, 0.12).name(QColor.HexArgb)};
                border-radius: {theme().scaled(_RADIUS, factor=0.6)}px;
            }}
            """
        )
        self._card.setAttribute(Qt.WA_StyledBackground, True)
        self._sync_mask()

    def _sync_mask(self) -> None:
        radius = theme().scaled(_RADIUS, factor=0.6)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        self.setMask(path.toFillPolygon().toPolygon())
        self._card.setGeometry(self.rect())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_mask()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_mask()
        if self.parentWidget() is not None and not self.pos().isNull():
            return
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        geo = parent.window().frameGeometry()
        self.move(
            geo.center().x() - self.width() // 2,
            max(geo.top() + 40, geo.center().y() - self.height() // 2),
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    # ----------------------------------------------------------------- helpers
    def add_text(self, text: str, *, detail: str = "", kind: str = "info") -> None:
        row = QHBoxLayout()
        row.setSpacing(12)
        icon_name, tone = _KIND_ICONS.get(kind, _KIND_ICONS["info"])
        icon_host = _IconBadge(icon_name, tone, 34)
        row.addWidget(icon_host, 0, Qt.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            f"color:{rgba(theme().palette.text, 0.86).name(QColor.HexArgb)};"
            f"font-size:{theme().px(9.6)}px;"
        )
        row.addWidget(label, 1)
        self.body.addLayout(row)
        if detail:
            box = QPlainTextEdit(detail)
            box.setReadOnly(True)
            box.setMaximumHeight(theme().scaled(170, factor=0.8))
            box.setStyleSheet(
                f"QPlainTextEdit{{background:{rgba(theme().palette.text, 0.05).name(QColor.HexArgb)};"
                f"border:1px solid {rgba(theme().palette.text, 0.10).name(QColor.HexArgb)};"
                f"border-radius:8px;color:{rgba(theme().palette.text, 0.72).name(QColor.HexArgb)};"
                f"font-size:{theme().px(8.8)}px;padding:8px;}}"
            )
            self.body.addWidget(box)

    def add_button(self, text: str, *, key: str, accent: bool = False) -> TextButton:
        button = TextButton(text, size=32, accent=accent)
        button.clicked.connect(lambda: self.done(hash(key) & 0x7FFFFFFF))
        button.setProperty("dialog_key", key)
        self.footer.addWidget(button)
        return button

    def selected(self) -> str:
        value = self.result()
        return _NAMES[value - 1] if 1 <= value <= len(_NAMES) else ""

    def button_for(self, name: str) -> TextButton | None:
        for i in range(self.footer.count()):
            widget = self.footer.itemAt(i).widget()
            if isinstance(widget, TextButton) and getattr(widget, "dialog_name", None) == name:
                return widget
        return None

    def add_named_button(self, text: str, *, name: str, accent: bool = False) -> TextButton:
        button = TextButton(text, size=32, accent=accent)
        button.dialog_name = name
        button.clicked.connect(lambda: self.done(_NAMES.index(name) + 1 if name in _NAMES else 0))
        self.footer.addWidget(button)
        return button


class _IconBadge(QWidget):
    def __init__(self, icon_name: str, tone: str, size: int) -> None:
        super().__init__()
        self._icon = icon_name
        self._tone = tone
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = theme().palette
        colour = {
            "accent": palette.accent,
            "warning": palette.warning,
            "danger": palette.danger,
            "success": palette.success,
        }.get(self._tone, palette.accent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(colour, 0.14))
        painter.drawEllipse(self.rect())
        side = int(self.width() * 0.52)
        rect = QRectF(
            (self.width() - side) / 2, (self.height() - side) / 2, side, side
        )
        draw_icon(painter, self._icon, rect, colour, 1.0)
        painter.end()


class MessageDialog(CardDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        text: str,
        *,
        kind: str = "info",
        detail: str = "",
        buttons: Sequence[tuple[str, str]] = (("ok", "好的"),),
        accent: str = "ok",
    ) -> None:
        super().__init__(parent, title)
        self.add_text(text, detail=detail, kind=kind)
        for name, label in buttons:
            self.add_named_button(label, name=name, accent=name == accent)
        self.setTabOrder(self.caption, self.caption)
        self.adjustSize()
        self.setFixedWidth(max(self._base_width, self.sizeHint().width()))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            primary = self.footer.itemAt(self.footer.count() - 1).widget()
            if isinstance(primary, TextButton):
                primary.click()
                return
        super().keyPressEvent(event)


class TextInputDialog(CardDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        label: str,
        *,
        text: str = "",
        placeholder: str = "",
        ok_text: str = "确定",
        cancel_text: str = "取消",
    ) -> None:
        super().__init__(parent, title)
        self.add_text(label, kind="info")
        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMinimumHeight(theme().scaled(34, factor=0.8))
        self.edit.setStyleSheet(
            f"QLineEdit{{background:{rgba(theme().palette.text, 0.05).name(QColor.HexArgb)};"
            f"border:1px solid {rgba(theme().palette.text, 0.14).name(QColor.HexArgb)};"
            f"border-radius:9px;padding:0 12px;color:{theme().palette.text};"
            f"font-size:{theme().px(9.8)}px; selection-background-color:{theme().palette.accent};}}"
            f"QLineEdit:focus{{border-color:{theme().palette.accent};}}"
        )
        self.body.addWidget(self.edit)
        self.add_named_button(cancel_text, name="cancel")
        self.add_named_button(ok_text, name="ok", accent=True)
        self.edit.returnPressed.connect(lambda: self.done(_NAMES.index("ok") + 1))
        self.setFixedWidth(self._base_width)

    def value(self) -> str:
        return self.edit.text().strip()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.edit.setFocus()
        self.edit.selectAll()


_NAMES = ["cancel", "ok", "alternate", "proceed", "export"]


# --------------------------------------------------------------------- public
def notify(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    kind: str = "info",
    detail: str = "",
    ok_text: str = "好的",
) -> None:
    dialog = MessageDialog(
        parent,
        title,
        text,
        kind=kind,
        detail=detail,
        buttons=(("ok", ok_text),),
    )
    dialog.exec()


def confirm(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_text: str = "确定",
    cancel_text: str = "取消",
    kind: str = "question",
) -> bool:
    dialog = MessageDialog(
        parent,
        title,
        text,
        kind=kind,
        buttons=(("cancel", cancel_text), ("ok", ok_text)),
    )
    dialog.exec()
    return dialog.selected() == "ok"


def choose(
    parent: QWidget | None,
    title: str,
    text: str,
    options: Sequence[tuple[str, str]],
    *,
    kind: str = "warning",
    accent: str = "",
) -> str | None:
    """Show one dialog with several labelled choices; returns the chosen key."""
    dialog = MessageDialog(
        parent,
        title,
        text,
        kind=kind,
        buttons=options,
        accent=accent,
    )
    dialog.exec()
    chosen = dialog.selected()
    return chosen or None


def ask_text(
    parent: QWidget | None,
    title: str,
    label: str,
    *,
    text: str = "",
    placeholder: str = "",
    ok_text: str = "确定",
    cancel_text: str = "取消",
) -> tuple[str, bool]:
    dialog = TextInputDialog(
        parent,
        title,
        label,
        text=text,
        placeholder=placeholder,
        ok_text=ok_text,
        cancel_text=cancel_text,
    )
    dialog.exec()
    return dialog.value(), dialog.selected() == "ok"


__all__ = ["CardDialog", "MessageDialog", "TextInputDialog", "ask_text", "choose", "confirm", "notify"]
