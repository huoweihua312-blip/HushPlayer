"""Shared self-painted lyrics canvas for the V2 ordinary and immersive pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QToolButton, QWidget

from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.tokens import Theme


def _with_alpha(value: str, alpha: int) -> QColor:
    color = QColor(value)
    color.setAlpha(max(0, min(255, alpha)))
    return color


@dataclass(frozen=True, slots=True)
class ResponsiveLyricsMetrics:
    """Logical-pixel typography derived from viewport size and user scale."""

    active_font_size: int
    normal_font_size: int
    translation_font_size: int
    romanization_font_size: int
    line_spacing: int
    section_spacing: int
    lyrics_max_width: int
    top_safe_area: int
    bottom_safe_area: int
    device_pixel_ratio: float

    @classmethod
    def for_viewport(
        cls,
        width: int,
        height: int,
        device_pixel_ratio: float,
        user_scale: int,
        *,
        translation_visible: bool,
        romanization_visible: bool,
        density: float = 1.0,
    ) -> "ResponsiveLyricsMetrics":
        logical_width = max(1, int(width))
        logical_height = max(1, int(height))
        width_progress = max(0.0, min(1.0, (logical_width - 900) / 1020))
        height_progress = max(0.0, min(1.0, (logical_height - 600) / 480))
        progress = width_progress * 0.64 + height_progress * 0.36
        beyond = max(0.0, min(1.0, (logical_width - 1920) / 640))
        scale = max(0.75, min(1.60, user_scale / 100)) * max(0.92, min(1.08, density))
        active_base = 34 + 20 * progress + 4 * beyond
        normal_base = 22 + 15 * progress + 3 * beyond
        translation_base = 15 + 7 * progress + beyond
        romanization_base = 14 + 5 * progress + beyond
        active = max(24, min(64, round(active_base * scale)))
        normal = max(17, min(40, round(normal_base * scale)))
        translation = max(12, min(28, round(translation_base * scale)))
        romanization = max(12, min(24, round(romanization_base * scale)))
        max_width = max(640, min(980, round(logical_width * 0.78)))
        line_spacing = max(5, round(active * 0.18))
        section_spacing = max(14, round(active * (0.42 + (0.06 if translation_visible or romanization_visible else 0.0))))
        return cls(
            active,
            normal,
            translation,
            romanization,
            line_spacing,
            section_spacing,
            max_width,
            max(12, round(logical_height * 0.04)),
            max(66, round(logical_height * 0.10)),
            float(device_pixel_ratio),
        )


class LyricsCanvasV2(QWidget):
    """Paint one coherent lyric surface without allocating widgets per line.

    The adapter remains the source of truth for line and segment timing.  This
    widget only draws the state it receives and reports clicks back as line ids.
    """

    seek_requested = Signal(str)
    browsing_changed = Signal(bool)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._document: LyricsDocument | None = None
        self._active_line: LyricLine | None = None
        self._active_segment_index = -1
        self._active_segment_progress = 0.0
        self._translation_visible = True
        self._romanization_visible = False
        self._mode = "ordinary"
        self._global_scale = 100
        self._base_sizes = (42, 27, 19, 16)
        self._font_weight = "Semibold"
        self._inactive_opacity = 74
        self._text_protection = "轻微阴影"
        self._max_text_width = 820
        self._responsive_scale = 1.0
        self._ordinary_viewport: tuple[int, int, float] | None = None
        self._ordinary_metrics: ResponsiveLyricsMetrics | None = None
        self._browse_anchor = -1
        self._line_rects: dict[str, QRect] = {}
        self._last_metrics: dict[str, int] = {}
        self.setObjectName("lyricsCanvasV2")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(260)
        self.return_button = QToolButton(self)
        self.return_button.setText("回到当前歌词")
        self.return_button.setObjectName("returnToCurrentLyrics")
        self.return_button.setVisible(False)
        self.return_button.clicked.connect(self.return_to_current)
        self.set_theme(theme)

    @property
    def document(self) -> LyricsDocument | None:
        return self._document

    @property
    def canvas(self) -> "LyricsCanvasV2":
        """Compatibility accessor for callers that previously used a surface wrapper."""
        return self

    @property
    def current_index(self) -> int:
        return self._active_index()

    @property
    def browsing(self) -> bool:
        return self._browse_anchor >= 0

    @property
    def paints_line_background(self) -> bool:
        return False

    @property
    def paints_row_background(self) -> bool:
        return False

    @property
    def effective_font_sizes(self) -> tuple[int, int, int, int]:
        if self._mode == "ordinary" and self._ordinary_metrics is not None:
            metrics = self._ordinary_metrics
            return (
                metrics.active_font_size,
                metrics.normal_font_size,
                metrics.translation_font_size,
                metrics.romanization_font_size,
            )
        scale = self._global_scale / 100 * self._responsive_scale
        active, normal, translation, romanization = self._base_sizes
        if self._mode == "ordinary":
            active_bounds, normal_bounds = (34, 48), (22, 32)
        else:
            active_bounds, normal_bounds = (54, 64), (29, 38)
        return (
            max(active_bounds[0], min(active_bounds[1], round(active * scale))),
            max(normal_bounds[0], min(normal_bounds[1], round(normal * scale))),
            max(14 if self._mode == "ordinary" else 18, min(26, round(translation * scale))),
            max(13 if self._mode == "ordinary" else 15, min(22, round(romanization * scale))),
        )

    @property
    def last_metrics(self) -> dict[str, int]:
        return dict(self._last_metrics)

    @property
    def responsive_metrics(self) -> ResponsiveLyricsMetrics | None:
        return self._ordinary_metrics

    @property
    def active_text_alpha(self) -> int:
        """The background layer never changes the alpha of lyric content."""
        return 255

    def inactive_alpha_for_distance(self, distance: int) -> int:
        baseline = max(32, min(92, self._inactive_opacity)) / 100
        if distance <= 1:
            return round(255 * max(0.68, baseline))
        if distance == 2:
            return round(255 * max(0.48, baseline * 0.76))
        if distance == 3:
            return round(255 * max(0.36, baseline * 0.55))
        return round(255 * max(0.32, baseline * 0.45))

    @staticmethod
    def inactive_scale_for_distance(distance: int) -> float:
        if distance <= 1:
            return 1.0
        if distance == 2:
            return 0.92
        if distance == 3:
            return 0.84
        return 0.78

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.return_button.setStyleSheet(
            "QToolButton { border: 0; border-radius: 6px; padding: 6px 9px; "
            f"background: {theme.colors.elevated_background}; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ background: {theme.colors.hover_background}; color: {theme.colors.primary_text}; }}"
        )
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = "immersive" if mode == "immersive" else "ordinary"
        self._refresh_ordinary_metrics()
        self.update()

    def set_document(self, document: LyricsDocument | None) -> None:
        self._document = document
        self._browse_anchor = -1
        self.return_button.setVisible(False)
        self.update()

    def set_active_line(self, line: LyricLine | None) -> None:
        self._active_line = line
        if not self.browsing:
            self.update()

    def set_active_segment(self, line: LyricLine, index: int, progress: float) -> None:
        if self._active_line is None or line.id == self._active_line.id:
            self._active_line = line
            self._active_segment_index = int(index)
            self._active_segment_progress = max(0.0, min(1.0, float(progress)))
            if not self.browsing:
                self.update()

    def set_display_options(self, options: dict[str, object], *, update_font_scale: bool = True) -> None:
        self._translation_visible = bool(options.get("translation", True))
        self._romanization_visible = bool(options.get("romanization", False))
        if update_font_scale:
            self.set_adapter_font_scale(float(options.get("font_scale", 1.0)))
        else:
            self._refresh_ordinary_metrics()
        self.update()

    def set_adapter_font_scale(self, value: float) -> None:
        self._global_scale = max(75, min(160, round(float(value) * 100)))
        self._refresh_ordinary_metrics()

    def set_global_scale(self, value: int) -> None:
        self._global_scale = max(75, min(160, int(value)))
        self._refresh_ordinary_metrics()
        self.update()

    def set_font_sizes(self, active: int, normal: int, translation: int, romanization: int) -> None:
        self._base_sizes = (
            max(28, min(72, int(active))),
            max(18, min(52, int(normal))),
            max(11, min(30, int(translation))),
            max(11, min(30, int(romanization))),
        )
        self.update()

    def set_font_weight(self, value: str) -> None:
        self._font_weight = str(value)
        self.update()

    def set_inactive_opacity(self, value: int) -> None:
        self._inactive_opacity = max(32, min(92, int(value)))
        self.update()

    def set_text_protection(self, value: str) -> None:
        self._text_protection = str(value)
        self.update()

    def set_max_text_width(self, value: int) -> None:
        self._max_text_width = max(360, min(920, int(value)))
        self.update()

    def set_responsive_scale(self, value: float) -> None:
        self._responsive_scale = max(0.72, min(1.12, float(value)))
        self.update()

    def set_ordinary_viewport(self, width: int, height: int, device_pixel_ratio: float = 1.0) -> None:
        self._ordinary_viewport = (max(1, int(width)), max(1, int(height)), max(1.0, float(device_pixel_ratio)))
        self._refresh_ordinary_metrics()
        self.update()

    def _refresh_ordinary_metrics(self) -> None:
        if self._mode != "ordinary" or self._ordinary_viewport is None:
            return
        width, height, ratio = self._ordinary_viewport
        self._ordinary_metrics = ResponsiveLyricsMetrics.for_viewport(
            width,
            height,
            ratio,
            self._global_scale,
            translation_visible=self._translation_visible,
            romanization_visible=self._romanization_visible,
        )

    def return_to_current(self) -> None:
        if self._browse_anchor < 0:
            return
        self._browse_anchor = -1
        self.return_button.setVisible(False)
        self.browsing_changed.emit(False)
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._document is None or not self._document.lines:
            event.ignore()
            return
        anchor = self._browse_anchor if self.browsing else self._active_index()
        delta = event.angleDelta().y()
        step = -1 if delta > 0 else 1
        self._browse_anchor = max(0, min(len(self._document.lines) - 1, anchor + step))
        self.return_button.setVisible(True)
        self.browsing_changed.emit(True)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            for line_id, rect in self._line_rects.items():
                if rect.contains(event.position().toPoint()):
                    self.seek_requested.emit(line_id)
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.return_button.adjustSize()
        self.return_button.move(
            max(8, self.width() - self.return_button.width() - 12),
            max(8, self.height() - self.return_button.height() - 12),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        self._line_rects.clear()
        document = self._document
        if document is None or not document.lines:
            return
        active_index = self._browse_anchor if self.browsing else self._active_index()
        active_index = max(0, min(len(document.lines) - 1, active_index))
        # At the compact ordinary height, five contextual rows preserve the
        # current lyric's anchor without forcing the whole group against the
        # top edge. Wider ordinary and immersive canvases retain more context.
        radius = 2 if self._mode == "ordinary" and self.height() < 460 else 3 if self._mode == "ordinary" else 4
        first = max(0, active_index - radius)
        last = min(len(document.lines), active_index + radius + 1)
        visible = tuple(enumerate(document.lines[first:last], start=first))
        sizes = self.effective_font_sizes
        text_width = min(self._max_text_width, max(240, self.width() - 40))
        heights = [self._line_height(line, index == active_index, abs(index - active_index), sizes) for index, line in visible]
        active_offset = next(offset for offset, (index, _line) in enumerate(visible) if index == active_index)
        active_line = visible[active_offset][1]
        active_font, active_lines = self._line_font_and_lines(
            active_line,
            True,
            0,
            sizes,
            text_width,
        )
        active_text_height = self._text_rect(
            0,
            0,
            text_width,
            active_font,
            active_line.text,
            5,
            lines=active_lines,
        ).height()
        # Anchor the current lyric itself, not its subtitle and following gap.
        # This keeps the primary lyric in the visual 45% band as subtitles grow.
        active_center = sum(heights[:active_offset]) + active_text_height // 2
        target_fraction = 0.45 if self._mode == "ordinary" else 0.48
        ordinary_metrics = self._ordinary_metrics if self._mode == "ordinary" else None
        top_safe = ordinary_metrics.top_safe_area if ordinary_metrics is not None else 12
        bottom_safe = ordinary_metrics.bottom_safe_area if ordinary_metrics is not None else 12
        target_center = top_safe + round((self.height() - top_safe - bottom_safe) * target_fraction)
        total_height = sum(heights)
        y = max(top_safe, min(max(top_safe, self.height() - total_height - bottom_safe), target_center - active_center))
        x = max(20, (self.width() - text_width) // 2)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        active_line_count = 0
        active_font_size = sizes[0]
        active_highlight_line_count = 0
        for (index, line), height in zip(visible, heights):
            is_active = index == active_index
            distance = abs(index - active_index)
            font, lines = self._line_font_and_lines(line, is_active, distance, sizes, text_width)
            rect = self._text_rect(x, y, text_width, font, line.text, 5, lines=lines)
            self._line_rects[line.id] = rect
            if is_active:
                active_line_count = len(lines)
                active_font_size = font.pixelSize()
                active_highlight_line_count = self._draw_active_line(painter, rect, line, font, lines)
            else:
                self._draw_text(
                    painter,
                    rect,
                    line.text,
                    font,
                    _with_alpha(self._theme.colors.primary_text, self.inactive_alpha_for_distance(distance)),
                    shadow=False,
                    lines=lines,
                )
            y += rect.height() + self._line_spacing()
            if is_active and self._translation_visible and line.translation:
                sub_font = self._font(sizes[2], QFont.Weight.Medium)
                sub_rect = self._text_rect(x, y, text_width, sub_font, line.translation, 3)
                self._draw_text(painter, sub_rect, line.translation, sub_font, _with_alpha(self._theme.colors.secondary_text, 230), shadow=False)
                y += sub_rect.height() + 2
            if is_active and self._romanization_visible and line.romanization:
                roman_font = self._font(sizes[3], QFont.Weight.Normal)
                roman_rect = self._text_rect(x, y, text_width, roman_font, line.romanization, 3)
                self._draw_text(painter, roman_rect, line.romanization, roman_font, _with_alpha(self._theme.colors.subtle_text, 226), shadow=False)
                y += roman_rect.height() + 2
            y += self._section_spacing()
        painter.end()
        self._last_metrics = {
            "active": active_font_size,
            "normal": sizes[1],
            "translation": sizes[2],
            "romanization": sizes[3],
            "text_width": text_width,
            "line_spacing": self._line_spacing(),
            "section_spacing": self._section_spacing(),
            "active_line_count": active_line_count,
            "active_highlight_line_count": active_highlight_line_count,
            "active_line_elided": 0,
        }

    def _active_index(self) -> int:
        if self._document is None or not self._document.lines:
            return 0
        if self._active_line is None:
            return 0
        for index, line in enumerate(self._document.lines):
            if line.id == self._active_line.id:
                return index
        return 0

    def _line_height(self, line: LyricLine, active: bool, distance: int, sizes: tuple[int, int, int, int]) -> int:
        width = min(self._max_text_width, max(240, self.width() - 40))
        font, lines = self._line_font_and_lines(line, active, distance, sizes, width)
        main_height = self._text_rect(0, 0, width, font, line.text, 5, lines=lines).height()
        result = main_height + self._line_spacing()
        if active and self._translation_visible and line.translation:
            result += self._text_rect(0, 0, width, self._font(sizes[2], QFont.Weight.Medium), line.translation, 3).height() + 2
        if active and self._romanization_visible and line.romanization:
            result += self._text_rect(0, 0, width, self._font(sizes[3], QFont.Weight.Normal), line.romanization, 3).height() + 2
        return result + self._section_spacing()

    def _line_spacing(self) -> int:
        if self._mode == "ordinary" and self._ordinary_metrics is not None:
            return self._ordinary_metrics.line_spacing
        return max(4, round(7 * self._responsive_scale))

    def _section_spacing(self) -> int:
        if self._mode == "ordinary" and self._ordinary_metrics is not None:
            return self._ordinary_metrics.section_spacing
        return max(10, round((17 if self._mode == "ordinary" else 19) * self._responsive_scale))

    def _font(self, size: int, weight: QFont.Weight) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(1, int(size)))
        font.setWeight(weight)
        return font

    def _active_weight(self) -> QFont.Weight:
        values = {
            "Regular": QFont.Weight.Normal,
            "Medium": QFont.Weight.Medium,
            "Semibold": QFont.Weight.DemiBold,
            "Bold": QFont.Weight.Bold,
        }
        return values.get(self._font_weight, QFont.Weight.DemiBold)

    def _line_font_and_lines(
        self,
        line: LyricLine,
        active: bool,
        distance: int,
        sizes: tuple[int, int, int, int],
        width: int,
    ) -> tuple[QFont, list[str]]:
        if not active:
            font = self._font(max(12, round(sizes[1] * self.inactive_scale_for_distance(distance))), QFont.Weight.Medium)
            return font, self._wrapped_lines(font, line.text, width)
        size = sizes[0]
        # The immersive active line remains large in normal cases.  Only a
        # genuinely long line reduces its size enough to fit two full lines;
        # it is never replaced with an ellipsis.
        # A long live lyric is preferable to an ellipsis.  The normal visual
        # range remains unchanged; this emergency floor is reached only when
        # two full lines still cannot contain the source text.
        minimum = 12 if self._mode == "immersive" else 22
        while True:
            font = self._font(size, self._active_weight())
            lines = self._wrapped_lines(font, line.text, width)
            if len(lines) <= 2 or size <= minimum:
                return font, lines
            size = max(minimum, size - 2)

    @staticmethod
    def _wrapped_lines(font: QFont, text: str, width: int) -> list[str]:
        """Wrap deterministically without allowing Qt to ellipsize active text."""
        if not text:
            return [""]
        metrics = QFontMetrics(font)
        available = max(1, int(width))
        lines: list[str] = []
        paragraphs = text.split("\n")
        for paragraph_index, paragraph in enumerate(paragraphs):
            current = ""
            # Whitespace-terminated words preserve natural English breaks;
            # unspaced Chinese text still reaches the character fallback below.
            for token in re.findall(r"\S+\s*|\s+", paragraph):
                candidate = current + token
                if current and metrics.horizontalAdvance(candidate) > available:
                    lines.append(current.rstrip())
                    current = token.lstrip()
                else:
                    current = candidate
                while current and metrics.horizontalAdvance(current) > available:
                    fragment = ""
                    for character in current:
                        if fragment and metrics.horizontalAdvance(fragment + character) > available:
                            break
                        fragment += character
                    if not fragment:
                        fragment, current = current[:1], current[1:]
                    else:
                        current = current[len(fragment) :].lstrip()
                    lines.append(fragment.rstrip())
            if current or not lines:
                lines.append(current.rstrip())
            if paragraph_index < len(paragraphs) - 1 and not lines[-1]:
                lines.append("")
        return lines or [""]

    def _text_rect(
        self,
        x: int,
        y: int,
        width: int,
        font: QFont,
        text: str,
        padding: int,
        *,
        lines: list[str] | None = None,
    ) -> QRect:
        count = len(lines if lines is not None else self._wrapped_lines(font, text, width))
        height = max(QFontMetrics(font).height() + padding * 2, QFontMetrics(font).height() * count + padding * 2)
        return QRect(x, y, width, height)

    def _draw_active_line(self, painter: QPainter, rect: QRect, line: LyricLine, font: QFont, lines: list[str]) -> int:
        base = _with_alpha(self._theme.colors.primary_text, 255)
        self._draw_text(
            painter,
            rect,
            line.text,
            font,
            base,
            shadow=self._mode == "immersive" and self._text_protection != "无",
            lines=lines,
        )
        prefix = self._segment_prefix(line)
        if not prefix:
            return 0
        remaining = len(prefix)
        drawn = 0
        metrics = QFontMetrics(font)
        line_height = metrics.height()
        start_y = rect.y() + max(0, (rect.height() - line_height * len(lines)) // 2)
        painter.setFont(font)
        painter.setPen(_with_alpha(self._theme.colors.accent, 255))
        for index, wrapped in enumerate(lines):
            if remaining <= 0:
                break
            fragment = wrapped[:remaining]
            if fragment:
                painter.drawText(QRect(rect.x(), start_y + index * line_height, rect.width(), line_height), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), fragment)
                drawn += 1
            remaining -= len(wrapped)
        return drawn

    def _segment_prefix(self, line: LyricLine) -> str:
        if not line.segments:
            return ""
        if line.id != (self._active_line.id if self._active_line else ""):
            return ""
        completed = max(0, self._active_segment_index)
        count = min(len(line.segments), completed + 1)
        texts = [segment.text for segment in line.segments[:count]]
        if texts and self._active_segment_progress < 0.2:
            texts = texts[:-1]
        separator = " " if line.segments[0].segment_type == "word" else ""
        return separator.join(texts)

    def _draw_text(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        font: QFont,
        color: QColor,
        *,
        shadow: bool,
        lines: list[str] | None = None,
    ) -> None:
        painter.setFont(font)
        wrapped = lines if lines is not None else self._wrapped_lines(font, text, rect.width())
        metrics = QFontMetrics(font)
        line_height = metrics.height()
        start_y = rect.y() + max(0, (rect.height() - line_height * len(wrapped)) // 2)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if shadow:
            shadow_color = _with_alpha("#101820" if self._theme.mode == "dark" else "#ffffff", 44)
            painter.setPen(QPen(shadow_color, 1.0))
            for index, value in enumerate(wrapped):
                painter.drawText(QRect(rect.x(), start_y + index * line_height + 1, rect.width(), line_height), flags, value)
        painter.setPen(color)
        for index, value in enumerate(wrapped):
            painter.drawText(QRect(rect.x(), start_y + index * line_height, rect.width(), line_height), flags, value)
