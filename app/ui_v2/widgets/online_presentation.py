"""Presentation helpers scoped to the online and import experience."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QCheckBox
from app.ui_v2.theme.tokens import Theme


def style_action(button, theme: Theme, *, primary=False, danger=False) -> None:
    c = theme.colors
    kind = button.metaObject().className()
    foreground = c.text_on_accent if primary else c.danger if danger else c.secondary_text
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    button.setStyleSheet(
        f"{kind} {{ min-height: 34px; padding: 0 12px; border: 1px solid transparent; "
        f"border-radius: 5px; background: {c.primary_button_fill if primary else 'transparent'}; "
        f"color: {foreground}; font-size: 13px; font-weight: 400; }}"
        f"{kind}:hover {{ background: {c.primary_button_fill if primary else c.hover_background}; }}"
        f"{kind}:focus {{ border-color: {c.focus_ring}; }}"
        f"{kind}:disabled {{ color: {c.disabled_text}; "
        f"background: {c.surface_secondary if primary else 'transparent'}; }}"
    )


def style_caption(label, theme: Theme, *, subtle=False) -> None:
    label.setStyleSheet(
        f"color: {theme.colors.subtle_text if subtle else theme.colors.secondary_text}; "
        "font-size: 13px; font-weight: 400; background: transparent; border: 0; padding: 0;"
    )


def checkbox_style(theme: Theme) -> str:
    c = theme.colors
    return (
        f"QCheckBox {{ color: {c.secondary_text}; font-size: 13px; spacing: 8px; background: transparent; }}"
        f"QCheckBox::indicator {{ width: 12px; height: 12px; border-radius: 2px; border: 1px solid {c.border_strong}; }}"
        f"QCheckBox::indicator:checked {{ background: {c.accent}; border-color: {c.accent}; }}"
        f"QCheckBox:focus {{ color: {c.primary_text}; outline: 1px solid {c.focus_ring}; }}"
        f"QCheckBox:disabled {{ color: {c.disabled_text}; }}"
        f"QCheckBox::indicator:disabled {{ background: {c.surface_pressed}; border-color: {c.border}; }}"
    )


class OnlineCheckBox(QCheckBox):
    """Compact checkbox with a visible tick and the native checkbox semantics."""

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(checkbox_style(theme))
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        self.update()

    def paintEvent(self, event) -> None:
        if not hasattr(self, "_theme"):
            return super().paintEvent(event)
        c = self._theme.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(1, self.height() / 2 - 6, 12, 12)
        painter.setPen(QPen(QColor(c.accent if self.isChecked() else c.border_strong), 1))
        painter.setBrush(QColor(c.primary_button_fill) if self.isChecked() else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 2, 2)
        if self.isChecked():
            painter.setPen(QPen(QColor(c.text_on_accent if self.isEnabled() else c.disabled_text), 1.5))
            painter.drawLine(box.left() + 2, box.top() + 6, box.left() + 5, box.top() + 9)
            painter.drawLine(box.left() + 5, box.top() + 9, box.right() - 2, box.top() + 3)
        painter.setFont(self.font())
        painter.setPen(QColor(c.secondary_text if self.isEnabled() else c.disabled_text))
        label = painter.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, max(0, self.width() - 23))
        painter.drawText(self.rect().adjusted(22, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, label)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(c.focus_ring))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
