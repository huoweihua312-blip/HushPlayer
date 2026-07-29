"""Lightweight painted lyric row; segments do not create child widgets."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.theme.tokens import Theme


class LyricLineItem(QWidget):
    clicked = Signal(str)

    def __init__(self, line: LyricLine, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.line = line
        self._theme = theme
        self._active = False
        self._segment_index = -1
        self._segment_progress = 0.0
        self._show_translation = True
        self._show_romanization = False
        self._font_scale = 1.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_display_options(self, options: dict[str, object]) -> None:
        translation = bool(options.get("translation", True))
        romanization = bool(options.get("romanization", False))
        scale = float(options.get("font_scale", 1.0))
        if (translation, romanization, scale) == (
            self._show_translation,
            self._show_romanization,
            self._font_scale,
        ):
            return
        self._show_translation = translation
        self._show_romanization = romanization
        self._font_scale = scale
        self.updateGeometry()
        self.update()

    def set_active(self, active: bool, segment_index: int = -1, progress: float = 0.0) -> None:
        changed = (active, segment_index, progress) != (
            self._active,
            self._segment_index,
            self._segment_progress,
        )
        self._active = active
        self._segment_index = segment_index
        self._segment_progress = progress
        if changed:
            self.updateGeometry()
            self.update()

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        available = max(120, width - 24)
        height = self._text_height(self.line.text, self._main_font(), available)
        if self._show_translation and self.line.translation:
            height += 4 + self._text_height(self.line.translation, self._secondary_font(), available)
        if self._show_romanization and self.line.romanization:
            height += 2 + self._text_height(self.line.romanization, self._secondary_font(), available)
        return height + 20

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def sizeHint(self):  # noqa: N802
        width = max(240, self.width())
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):  # noqa: N802
        return QSize(120, self.heightForWidth(120))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.line.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self.rect().adjusted(12, 8, -12, -8)
        main_color = QColor(
            self._theme.colors.primary_text if self._active else self._theme.colors.secondary_text
        )
        if self.line.is_instrumental:
            main_color = QColor(self._theme.colors.secondary_text)
        y = rect.top()
        main_rect = rect
        main_height = self._text_height(self.line.text, self._main_font(), rect.width())
        main_rect.setHeight(main_height)
        if self._active:
            # A short marker is deliberately local to the first text line; it is
            # not a row selection surface and never spans the lyric width.
            painter.fillRect(rect.left() - 7, rect.top() + 4, 3, min(20, max(8, main_height - 8)), QColor(self._theme.colors.accent))
        self._draw_wrapped(painter, main_rect, self.line.text, self._main_font(), main_color)
        if self._active and self.line.segments:
            prefix = self._highlight_prefix()
            if prefix:
                self._draw_wrapped(
                    painter,
                    main_rect,
                    prefix,
                    self._main_font(),
                    QColor(self._theme.colors.accent),
                )
        y += main_height
        if self._show_translation and self.line.translation:
            y += 4
            height = self._text_height(self.line.translation, self._secondary_font(), rect.width())
            sub_rect = rect
            sub_rect.setTop(y)
            sub_rect.setHeight(height)
            translation_color = self._theme.colors.secondary_text if self._active else self._theme.colors.subtle_text
            self._draw_wrapped(painter, sub_rect, self.line.translation, self._secondary_font(), QColor(translation_color))
            y += height
        if self._show_romanization and self.line.romanization:
            y += 2
            height = self._text_height(self.line.romanization, self._secondary_font(), rect.width())
            sub_rect = rect
            sub_rect.setTop(y)
            sub_rect.setHeight(height)
            romanization_color = self._theme.colors.secondary_text if self._active else self._theme.colors.subtle_text
            self._draw_wrapped(painter, sub_rect, self.line.romanization, self._secondary_font(), QColor(romanization_color))

    def _highlight_prefix(self) -> str:
        if self._segment_index < 0:
            return ""
        completed = "".join(segment.text for segment in self.line.segments[: self._segment_index])
        current = self.line.segments[min(self._segment_index, len(self.line.segments) - 1)].text
        visible = round(len(current) * self._segment_progress)
        return completed + current[:visible]

    def color_roles(self) -> dict[str, str]:
        """Expose the four painted colors for focused visual-regression tests."""
        return {
            "background": self._theme.colors.content_background,
            "row_background": "transparent",
            "played_segment": self._theme.colors.accent,
            "active_unplayed": self._theme.colors.primary_text,
            "inactive_line": self._theme.colors.secondary_text,
            "secondary_text": self._theme.colors.secondary_text if self._active else self._theme.colors.subtle_text,
        }

    def _main_font(self) -> QFont:
        font = QFont(self.font())
        emphasis = 1.16 if self._active else 1.0
        font.setPointSizeF(self._theme.fonts.body * self._font_scale * emphasis)
        font.setWeight(QFont.Weight.DemiBold if self._active else QFont.Weight.Normal)
        return font

    def _secondary_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(self._theme.fonts.secondary * self._font_scale)
        return font

    @staticmethod
    def _text_height(text: str, font: QFont, width: int) -> int:
        metrics = QFontMetrics(font)
        return max(metrics.height(), metrics.boundingRect(0, 0, max(1, width), 10_000, int(Qt.TextFlag.TextWordWrap), text).height())

    @staticmethod
    def _draw_wrapped(painter: QPainter, rect, text: str, font: QFont, color: QColor) -> None:
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), text)
