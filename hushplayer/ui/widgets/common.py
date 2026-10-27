"""Shared custom-painted widgets and small painting helpers.

The UI is drawn by hand on top of Qt Widgets: this keeps the visual language
consistent (radii, hover states, typography) and avoids fighting native styles.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QAbstractButton, QLabel, QSizePolicy, QWidget

from ...core import icons
from ...core.theme import css_rgba, qcolor, rgba, theme


def elide(text: str, font: QFont, width: int, mode: Qt.TextElideMode = Qt.ElideRight) -> str:
    if width <= 0:
        return ""
    metrics = QFontMetrics(font)
    return metrics.elidedText(text or "", mode, width)


def paint_rounded_pixmap(
    painter: QPainter,
    rect: QRectF,
    pixmap: QPixmap | None,
    radius: float,
    *,
    border: QColor | None = None,
    placeholder_color: str | None = None,
    fallback_icon: str = "music_note",
) -> None:
    """Draw ``pixmap`` cropped to ``rect`` with rounded corners."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if pixmap is None or pixmap.isNull():
        base = placeholder_color or theme().palette.surface_alt
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, qcolor(base))
        gradient.setColorAt(1.0, mix_safe(base, theme().palette.surface_hover, 0.45))
        painter.fillPath(path, gradient)
        icon_size = int(min(rect.width(), rect.height()) * 0.34)
        if icon_size >= 12:
            target = QRectF(
                rect.center().x() - icon_size / 2,
                rect.center().y() - icon_size / 2,
                icon_size,
                icon_size,
            )
            icons.draw(
                painter,
                fallback_icon,
                target,
                rgba(theme().palette.text_secondary, 0.55),
            )
    else:
        painter.setClipPath(path)
        dpr = pixmap.devicePixelRatio() or 1.0
        target_w = max(1, int(round(rect.width() * dpr)))
        target_h = max(1, int(round(rect.height() * dpr)))
        scaled = pixmap
        if pixmap.width() != target_w or pixmap.height() != target_h:
            scaled = pixmap.scaled(
                target_w,
                target_h,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
        logical_w = scaled.width() / (scaled.devicePixelRatio() or 1.0)
        logical_h = scaled.height() / (scaled.devicePixelRatio() or 1.0)
        x = rect.x() + (rect.width() - logical_w) / 2
        y = rect.y() + (rect.height() - logical_h) / 2
        painter.drawPixmap(QPointF(x, y), scaled)
    if border is not None and border.alpha() > 0:
        painter.setClipping(False)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.restore()


def paint_badge(
    painter: QPainter,
    rect: QRectF,
    text: str,
    source: str = "",
    *,
    tone: str = "",
) -> None:
    """Draw the small rounded source badge used in track rows."""
    palette = theme().palette
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    tone = {"accent": palette.accent, "danger": palette.danger, "success": palette.success}.get(
        tone, tone
    )
    base = tone or palette.text
    fill = rgba(base, 0.09 if palette.is_dark else 0.06)
    foreground = rgba(base, 0.62)
    painter.setPen(QPen(rgba(base, 0.12), 1.0))
    painter.setBrush(fill)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), rect.height() / 2, rect.height() / 2)
    font = theme().font(7.2, 600)
    painter.setFont(font)
    painter.setPen(QPen(foreground))
    painter.drawText(rect, int(Qt.AlignCenter), text)
    painter.restore()


def mix_safe(first: str | QColor, second: str | QColor, t: float) -> QColor:
    from ...core.theme import mix

    return mix(first, second, t)


def apply_shadow(widget: QWidget, *, blur: int = 28, y: int = 6, alpha: float = 0.30) -> None:
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QColor(0, 0, 0, int(255 * alpha)))
    widget.setGraphicsEffect(effect)


class HoverAnimation:
    """Tiny helper that animates an attribute between 0 and 1 on hover."""

    def __init__(self, widget: QWidget, duration: int = 120) -> None:
        self.value = 0.0
        self._widget = widget
        self._anim = QVariantAnimation(widget)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_value)

    def _on_value(self, value: object) -> None:
        self.value = float(value)  # type: ignore[arg-type]
        self._widget.update()

    def to(self, target: float) -> None:
        target = max(0.0, min(1.0, target))
        self._anim.stop()
        if theme().reduce_motion:
            self._on_value(target)
            return
        self._anim.setStartValue(self.value)
        self._anim.setEndValue(target)
        self._anim.start()


class IconButton(QAbstractButton):
    """Square icon button with a soft hover background and optional toggle."""

    def __init__(
        self,
        icon_name: str,
        *,
        size: int = 32,
        icon_size: int = 18,
        tooltip: str = "",
        checkable: bool = False,
        color: str = "",
        hover_color: str = "",
        checked_color: str = "",
        bg: bool = True,
        radius: int = -1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._color = color
        self._hover_color = hover_color
        self._checked_color = checked_color
        self._bg = bg
        self._radius = radius
        self._hover = HoverAnimation(self, 120)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.StrongFocus)
        if tooltip:
            self.setToolTip(tooltip)
            # Screen readers and tooling both use this; keep it in sync with the
            # visible hint instead of leaving the button anonymous.
            self.setAccessibleName(tooltip.split(" (")[0].strip() or icon_name)

    def set_icon(self, name: str) -> None:
        if name != self._icon_name:
            self._icon_name = name
            self.update()

    def set_icon_size(self, size: int) -> None:
        self._icon_size = size
        self.update()

    def sizeHint(self) -> QSize:
        return self.size()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover.to(0.0)
        super().leaveEvent(event)

    def _current_color(self) -> QColor:
        palette = theme().palette
        if self.isChecked() and self._checked_color:
            return qcolor(self._checked_color)
        base = self._color or palette.text_secondary
        if self._hover_color and self._hover.value > 0:
            return mix_safe(base, self._hover_color, self._hover.value)
        hovered = mix_safe(base, palette.text, 0.55)
        return mix_safe(base, hovered, self._hover.value)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        radius = self._radius if self._radius >= 0 else min(rect.width(), rect.height()) / 2.6
        if self._bg and self._hover.value > 0.01 and self.isEnabled():
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(theme().palette.text, 0.07 * self._hover.value))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        target = QRectF(0, 0, self._icon_size, self._icon_size)
        target.moveCenter(rect.center())
        icons.draw(painter, self._icon_name, target, self._current_color())
        if self.isCheckable() and self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme().palette.accent))
            painter.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 2.5), 2.2, 2.2)
        if self.hasFocus():
            # Keyboard users need to see where Tab landed; the frameless window
            # paints everything itself, so native focus rings never show up.
            painter.setPen(QPen(rgba(theme().palette.accent, 0.75), 1.4))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1.2, 1.2, -1.2, -1.2), radius, radius)
        painter.end()


class TextButton(QAbstractButton):
    """Rounded button carrying an optional icon and a label."""

    def __init__(
        self,
        text: str,
        *,
        icon_name: str = "",
        size: int = 30,
        icon_size: int = 16,
        accent: bool = False,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._accent = accent
        self._hover = HoverAnimation(self, 120)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedHeight(size)
        self._pad = 12
        self.setAccessibleName(text)
        if tooltip:
            self.setToolTip(tooltip)

    def set_text(self, text: str) -> None:
        self._text = text
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        font = theme().font(9.2, 600)
        width = QFontMetrics(font).horizontalAdvance(self._text)
        if self._icon_name:
            width += self._icon_size + 6
        return QSize(width + self._pad * 2, self.height())

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover.to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isEnabled():
            if self._accent:
                base = qcolor(palette.accent)
                fill = mix_safe(base, palette.accent_hover, self._hover.value)
                text_color = qcolor(palette.accent_text)
            else:
                base = rgba(palette.text, 0.07)
                fill = mix_safe(base, rgba(palette.text, 0.13), self._hover.value)
                text_color = qcolor(palette.text)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        else:
            text_color = rgba(palette.text, 0.38)
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.04))
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        font = theme().font(9.2, 600)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(self._text)
        total = text_width + (self._icon_size + 6 if self._icon_name else 0)
        x = rect.center().x() - total / 2
        if self._icon_name:
            icon_rect = QRectF(x, rect.center().y() - self._icon_size / 2, self._icon_size, self._icon_size)
            icons.draw(painter, self._icon_name, icon_rect, text_color)
            x += self._icon_size + 6
        painter.setPen(QPen(text_color))
        painter.drawText(
            QRectF(x, rect.y(), text_width + 2, rect.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._text,
        )
        painter.end()


class PlayButton(QAbstractButton):
    """Big circular accent play/pause button used by the player bar."""

    def __init__(self, size: int = 40, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hover = HoverAnimation(self, 130)
        self._playing = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("播放 / 暂停 (Space)")
        self.setAccessibleName("播放")

    def set_playing(self, playing: bool) -> None:
        if self._playing != playing:
            self._playing = playing
            self.setAccessibleName("暂停" if playing else "播放")
            self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover.to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        base = qcolor(palette.accent)
        fill = mix_safe(base, palette.accent_hover, self._hover.value)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        # 播放/暂停直接用图标集里同一套 24 网格字形：它本身按视觉重心设计，
        # 手绘三角形在 40px 上无论怎么补位移都容易显得偏右，切换时大小也会跳。
        icon_size = rect.width() * 0.80
        target = QRectF(0, 0, icon_size, icon_size)
        target.moveCenter(rect.center())
        if not self._playing:
            # 图标集里的三角形本身带 7% 的视觉补偿（包围盒偏右），40px 圆钮上
            # 会明显偏右；这里回拉一点，让左右留白基本相等。
            target.translate(-icon_size * 0.055, 0)
        painter.setPen(Qt.NoPen)
        icons.draw(
            painter,
            "pause" if self._playing else "play",
            target,
            qcolor(palette.accent_text),
        )
        painter.end()


class Chip(QLabel):
    """Small rounded label used for source badges and counts."""

    def __init__(
        self,
        text: str = "",
        *,
        fg: str = "",
        bg: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._fg = fg
        self._bg = bg
        self.setFont(theme().font(8.0, 600))
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.refresh()

    def set_colors(self, fg: str, bg: str) -> None:
        self._fg = fg
        self._bg = bg
        self.refresh()

    def refresh(self) -> None:
        palette = theme().palette
        fg = self._fg or palette.text_secondary
        bg = self._bg or rgba(palette.text, 0.07)
        self.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg if isinstance(bg, str) else css_rgba(palette.text, 0.07)};"
            f" border-radius: 8px; padding: 2px 8px; }}"
        )


class SectionHeader(QWidget):
    """Row with a title, optional subtitle and a trailing action area."""

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self.trailing: QWidget | None = None
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(34)

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle = subtitle
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = theme().font(12.5, 700)
        painter.setFont(font)
        painter.setPen(QPen(qcolor(palette.text)))
        metrics = QFontMetrics(font)
        painter.drawText(
            QRect(0, 0, metrics.horizontalAdvance(self._title) + 8, self.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._title,
        )
        if self._subtitle:
            painter.setFont(theme().font(9.5, 500))
            painter.setPen(QPen(rgba(palette.text_secondary, 0.9)))
            painter.drawText(
                QRect(metrics.horizontalAdvance(self._title) + 12, 0, self.width(), self.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._subtitle,
            )
        painter.end()


class Separator(QWidget):
    def __init__(self, *, vertical: bool = False, margin: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vertical = vertical
        self._margin = margin
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(theme().palette.border, 0.9))
        if self._vertical:
            painter.drawRect(QRect(0, self._margin, 1, max(0, self.height() - self._margin * 2)))
        else:
            painter.drawRect(QRect(self._margin, 0, max(0, self.width() - self._margin * 2), 1))
        painter.end()


def scroll_page(widget: QWidget, *, margin: int = 0) -> None:
    """Common page background."""
    widget.setAutoFillBackground(False)


def fade_in(widget: QWidget, duration: int = 180, *, from_value: float = 0.0) -> None:
    effect_cls = None
    try:
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect_cls = QGraphicsOpacityEffect
    except Exception:
        return
    if effect_cls is None:
        return
    effect = effect_cls(widget)
    effect.setOpacity(from_value)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(theme().duration(duration))
    animation.setStartValue(from_value)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)

    def cleanup() -> None:
        widget.setGraphicsEffect(None)

    animation.finished.connect(cleanup)
    animation.start(QPropertyAnimation.DeleteWhenStopped)
    widget._fade_animation = animation  # type: ignore[attr-defined]


def once(func: Callable[[], None]) -> Callable[[], None]:
    """Guard for one-shot callbacks."""
    done = False

    def wrapper() -> None:
        nonlocal done
        if done:
            return
        done = True
        func()

    return wrapper
