"""Reusable controls for the settings centre.

The controls here are intentionally small and composable: a settings page is
just a series of :class:`SettingsCard` sections, each holding :class:`SettingRow`
items whose trailing widget is one of the controls below.
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core.theme import Metrics, css_rgba, qcolor, rgba, theme
from .common import IconButton, TextButton

__all__ = [
    "SettingsCard",
    "SettingRow",
    "ToggleSwitch",
    "SettingCombo",
    "SettingSlider",
    "SettingField",
    "ThemePicker",
    "FolderEditor",
    "SegmentedPicker",
]


def _label(text: str, *, size: float = 10.0, weight: int = 400, alpha: float = 1.0) -> QLabel:
    label = QLabel(text)
    label.setFont(theme().font(size, weight))
    label.setStyleSheet(f"color: {css_rgba(theme().palette.text, alpha)};")
    label.setWordWrap(True)
    return label


class SettingsCard(QFrame):
    """A rounded panel grouping related settings."""

    def __init__(self, title: str = "", description: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self._title = title
        self._description = description
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 14)
        self._layout.setSpacing(4)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        self._title_label = _label(title, size=11.6, weight=700)
        self._desc_label = _label(description, size=9.2, alpha=0.55)
        if title:
            self._layout.addWidget(self._title_label)
            self._layout.addSpacing(2)
        if description:
            self._layout.addWidget(self._desc_label)
        if title or description:
            self._layout.addSpacing(8)
        self._layout.addLayout(self._body)
        self.refresh_theme()

    def add(self, widget: QWidget) -> None:
        self._body.addWidget(widget)

    def add_row(self, row: "SettingRow") -> "SettingRow":
        self._body.addWidget(row)
        return row

    def set_title(self, title: str) -> None:
        self._title = title
        self._title_label.setText(title)

    def refresh_theme(self) -> None:
        palette = theme().palette
        self.setStyleSheet(
            f"""
            #SettingsCard {{
                background: {palette.surface};
                border: 1px solid {palette.border};
                border-radius: {Metrics.radius_lg}px;
            }}
            """
        )
        self._title_label.setStyleSheet(f"color: {palette.text};")
        self._desc_label.setStyleSheet(f"color: {css_rgba(palette.text, 0.55)};")


class SettingRow(QWidget):
    """One setting line: title + optional description on the left, control right."""

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        control: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._description = description
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(16)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.title_label = _label(title, size=10.0, weight=500)
        self.title_label.setWordWrap(False)
        self.desc_label = _label(description, size=8.8, alpha=0.5)
        text_box.addWidget(self.title_label)
        if description:
            text_box.addWidget(self.desc_label)
        layout.addLayout(text_box, 1)
        self.control = control
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignVCenter)
        self._separator = description != ""

    def add_control(self, control: QWidget) -> None:
        self.control = control
        self.layout().addWidget(control, 0, Qt.AlignVCenter)

    def refresh_theme(self) -> None:
        palette = theme().palette
        self.title_label.setStyleSheet(f"color: {css_rgba(palette.text, 0.94)};")
        self.desc_label.setStyleSheet(f"color: {css_rgba(palette.text, 0.5)};")


class ToggleSwitch(QAbstractButton):
    """iOS-style switch used for every boolean setting."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._slide)

    def _on_anim(self, value) -> None:
        self._pos = float(value)
        self.update()

    def _slide(self, checked: bool) -> None:
        if theme().reduce_motion:
            self._pos = 1.0 if checked else 0.0
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(1, 2, self.width() - 2, self.height() - 4)
        off = qcolor(mix_color(palette.text, 0.18) if palette.is_dark else mix_color(palette.text, 0.16))
        brush = QColor(off)
        accent = qcolor(palette.accent)
        brush = QColor(
            int(off.red() + (accent.red() - off.red()) * self._pos),
            int(off.green() + (accent.green() - off.green()) * self._pos),
            int(off.blue() + (accent.blue() - off.blue()) * self._pos),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(brush)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        knob = rect.height() - 4
        x = rect.left() + 2 + (rect.width() - knob - 4) * self._pos
        knob_rect = QRectF(x, rect.top() + 2, knob, knob)
        painter.setBrush(qcolor("#FFFFFF"))
        painter.drawEllipse(knob_rect)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(rgba(accent, 0.55), 1.4))
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), rect.height() / 2 + 2, rect.height() / 2 + 2)
        painter.end()


def mix_color(color: str, lighten: float) -> str:
    c = qcolor(color)
    target = 255 if theme().palette.is_dark else 0
    ratio = lighten
    return QColor(
        int(c.red() + (target - c.red()) * ratio),
        int(c.green() + (target - c.green()) * ratio),
        int(c.blue() + (target - c.blue()) * ratio),
    ).name()


class SettingCombo(QComboBox):
    """QComboBox with a sane minimum width and theme refresh."""

    def __init__(self, items: list[tuple[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(168)
        self.setCursor(Qt.PointingHandCursor)
        for label, value in items:
            self.addItem(label, value)
        self.setFont(theme().font(9.4, 500))

    def set_value(self, value: object) -> None:
        index = self.findData(value)
        self.setCurrentIndex(index if index >= 0 else 0)

    def value(self) -> object:
        return self.currentData()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = 14.0
        rect = QRectF(self.width() - 12 - size, (self.height() - size) / 2, size, size)
        from ...core import icons
        from ...core.theme import rgba, theme as _theme
        icons.draw(painter, "chevron_down", rect, rgba(_theme().palette.text_secondary, 0.9))
        painter.end()


class SettingSlider(QWidget):
    """Slider with a trailing value label; emits ``value_changed``."""

    value_changed = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float,
        *,
        suffix: str = "",
        steps: int = 100,
        formatter: Callable[[float], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._suffix = suffix
        self._formatter = formatter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, steps)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setFixedWidth(170)
        self.value_label = _label("", size=9.2, weight=500, alpha=0.7)
        self.value_label.setFixedWidth(52)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.slider)
        layout.addWidget(self.value_label)
        self._steps = steps
        self._set = False
        self.set_value(value)
        self.slider.valueChanged.connect(self._on_slider)

    def set_value(self, value: float) -> None:
        self._set = True
        ratio = (value - self._minimum) / max(1e-9, self._maximum - self._minimum)
        self.slider.setValue(int(round(ratio * self._steps)))
        self._update_label(value)
        self._set = False

    def value(self) -> float:
        ratio = self.slider.value() / self._steps
        return self._minimum + (self._maximum - self._minimum) * ratio

    def _update_label(self, value: float) -> None:
        if self._formatter is not None:
            text = self._formatter(value)
        elif self._suffix:
            text = f"{value:g}{self._suffix}"
        else:
            text = f"{value:g}"
        self.value_label.setText(text)

    def _on_slider(self, _value: int) -> None:
        value = self.value()
        self._update_label(value)
        if not self._set:
            self.value_changed.emit(value)


class SettingField(QWidget):
    """Line edit with an optional browse button (folders / files)."""

    text_changed = Signal(str)
    browse_clicked = Signal()

    def __init__(
        self,
        value: str = "",
        *,
        placeholder: str = "",
        mode: str = "folder",
        width: int = 260,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit(value)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFixedWidth(width)
        self.edit.setFont(theme().font(9.4))
        self.edit.textChanged.connect(self.text_changed)
        self.button = TextButton("浏览…", size=28)
        self.button.clicked.connect(self._browse)
        layout.addWidget(self.edit)
        layout.addWidget(self.button)

    def _browse(self) -> None:
        start = self.edit.text() or os.path.expanduser("~")
        if self._mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", start)
        if path:
            self.edit.setText(os.path.normpath(path))
        self.browse_clicked.emit()

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)


class SegmentedPicker(QWidget):
    """Small segmented control used inside settings rows."""

    changed = Signal(object)

    def __init__(self, items: list[tuple[str, object]], value: object = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items = items
        self._value = value if value is not None else (items[0][1] if items else None)
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(28)
        width = 0
        metrics = QFontMetrics(theme().font(9.2, 500))
        for label, _ in items:
            width += metrics.horizontalAdvance(label) + 26
        self.setFixedWidth(max(120, width + 6))

    def value(self) -> object:
        return self._value

    def set_value(self, value: object) -> None:
        if value != self._value:
            self._value = value
            self.update()

    def _segments(self) -> list[QRectF]:
        count = max(1, len(self._items))
        width = self.width() / count
        return [QRectF(i * width, 0, width, self.height()) for i in range(count)]

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = -1
        for index, rect in enumerate(self._segments()):
            if rect.contains(event.position()):
                hover = index
                break
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            for index, rect in enumerate(self._segments()):
                if rect.contains(event.position()) and index < len(self._items):
                    value = self._items[index][1]
                    if value != self._value:
                        self._value = value
                        self.update()
                        self.changed.emit(value)
                    break
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(qcolor(palette.border), 1))
        painter.setBrush(rgba(palette.text, 0.04))
        painter.drawRoundedRect(rect, 7, 7)
        for index, seg in enumerate(self._segments()):
            label, value = self._items[index]
            selected = value == self._value
            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(qcolor(palette.accent))
                painter.drawRoundedRect(seg.adjusted(2, 2, -2, -2), 6, 6)
            font = theme().font(9.2, 600 if selected else 500)
            painter.setFont(font)
            color = qcolor("#FFFFFF") if selected else rgba(palette.text, 0.62 if self._hover != index else 0.86)
            painter.setPen(QPen(color))
            painter.drawText(seg, int(Qt.AlignCenter), label)
        painter.end()


class ThemePicker(QWidget):
    """Three preview tiles for the theme preference (system / light / dark)."""

    changed = Signal(str)

    OPTIONS = [("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")]

    def __init__(self, value: str = "system", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = value
        self._hover = ""
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(3 * 116 + 2 * 12, 96)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value != self._value:
            self._value = value
            self.update()

    def _tiles(self) -> list[QRectF]:
        width = 116
        return [QRectF(i * (width + 12), 0, width, 96) for i in range(3)]

    def _hit(self, pos) -> str:
        for index, rect in enumerate(self._tiles()):
            if rect.contains(pos):
                return self.OPTIONS[index][0]
        return ""

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = self._hit(event.position())
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = ""
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            hit = self._hit(event.position())
            if hit and hit != self._value:
                self._value = hit
                self.update()
                self.changed.emit(hit)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for index, rect in enumerate(self._tiles()):
            key, label = self.OPTIONS[index]
            selected = key == self._value
            hovered = key == self._hover
            # Preview card: light and dark use their own palette, "system" splits.
            preview = rect.adjusted(0, 0, 0, -20)
            radius = 10.0
            painter.save()
            clip = preview.adjusted(2, 2, -2, -2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.06 if not hovered else 0.1))
            painter.drawRoundedRect(preview.adjusted(-1, -1, 1, 1), radius + 2, radius + 2)
            painter.setClipRect(clip)
            if key == "system":
                painter.fillRect(QRectF(clip.left(), clip.top(), clip.width() / 2, clip.height()), qcolor("#F4F4F7"))
                painter.fillRect(
                    QRectF(clip.left() + clip.width() / 2, clip.top(), clip.width() / 2, clip.height()),
                    qcolor("#17171C"),
                )
            else:
                painter.fillRect(clip, qcolor("#F4F4F7" if key == "light" else "#17171C"))
            # Miniature window: sidebar + content lines.
            fore = qcolor("#191920" if key == "light" else "#EDEDF2")
            accent = qcolor(palette.accent)
            painter.setBrush(rgba(fore, 0.12))
            painter.drawRoundedRect(
                QRectF(clip.left() + 8, clip.top() + 10, 22, clip.height() - 20), 4, 4
            )
            painter.setBrush(rgba(fore, 0.28))
            painter.drawRoundedRect(QRectF(clip.left() + 38, clip.top() + 12, 40, 6), 3, 3)
            painter.setBrush(rgba(fore, 0.16))
            for row in range(3):
                painter.drawRoundedRect(
                    QRectF(clip.left() + 38, clip.top() + 26 + row * 12, 52 - row * 8, 5), 2.5, 2.5
                )
            painter.setBrush(accent)
            painter.drawRoundedRect(
                QRectF(clip.left() + clip.width() - 26, clip.top() + clip.height() - 16, 14, 8), 3, 3
            )
            painter.restore()
            if selected:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(accent, 2))
                painter.drawRoundedRect(preview.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            else:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(rgba(palette.text, 0.14), 1))
                painter.drawRoundedRect(preview.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            font = theme().font(9.0, 600 if selected else 500)
            painter.setFont(font)
            painter.setPen(QPen(qcolor(palette.accent) if selected else rgba(palette.text, 0.7)))
            painter.drawText(
                QRectF(rect.left(), rect.bottom() - 18, rect.width(), 18),
                int(Qt.AlignHCenter | Qt.AlignVCenter),
                label,
            )
        painter.end()


class FolderEditor(QWidget):
    """Editable list of library scanner folders."""

    changed = Signal(list)

    def __init__(self, folders: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folders = [os.path.normpath(f) for f in folders if f]
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(4)
        self._layout.addLayout(self._rows)
        self._empty = _label("尚未添加扫描目录", size=9.2, alpha=0.5)
        self._layout.addWidget(self._empty)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        self._add = TextButton("添加文件夹…", icon_name="plus", size=28)
        self._add.clicked.connect(self._browse)
        self._scan = TextButton("立即扫描", icon_name="refresh", size=28)
        self._scan.clicked.connect(self._scan_now)
        buttons.addWidget(self._add)
        buttons.addWidget(self._scan)
        buttons.addStretch(1)
        self._layout.addLayout(buttons)
        self._rebuild()

    def folders(self) -> list[str]:
        return list(self._folders)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择音乐文件夹", os.path.expanduser("~"))
        if path:
            path = os.path.normpath(path)
            if path not in self._folders:
                self._folders.append(path)
                self._rebuild()
                self.changed.emit(self.folders())

    def _remove(self, path: str) -> None:
        if path in self._folders:
            self._folders.remove(path)
            self._rebuild()
            self.changed.emit(self.folders())

    def _scan_now(self) -> None:
        try:
            from ..context import ctx

            ctx().library.scan(self._folders, force=True)
        except Exception:  # noqa: BLE001
            pass

    def _rebuild(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for path in self._folders:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            icon = QLabel()
            from ...core import icons

            icon.setPixmap(icons.pixmap("folder", theme().palette.text_secondary, 15))
            layout.addWidget(icon)
            text = _label(path, size=9.2, alpha=0.78)
            text.setWordWrap(False)
            text.setToolTip(path)
            metrics = QFontMetrics(text.font())
            text.setText(metrics.elidedText(path, Qt.ElideMiddle, 400))
            layout.addWidget(text, 1)
            remove = IconButton("minus_circle", size=24, icon_size=15, tooltip="移除该目录")
            remove.clicked.connect(lambda _=False, p=path: self._remove(p))
            layout.addWidget(remove)
            self._rows.addWidget(row)
        self._empty.setVisible(not self._folders)
