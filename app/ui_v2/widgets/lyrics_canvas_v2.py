"""Shared self-painted lyrics canvas for the V2 ordinary and immersive pages."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolButton, QWidget

from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.icons import FLUENT_IMMERSIVE_ASSETS, fluent_immersive_interactive_icon
from app.ui_v2.theme.tokens import Theme


def _with_alpha(value: str, alpha: int) -> QColor:
    color = QColor(value)
    color.setAlpha(max(0, min(255, alpha)))
    return color


def _rgba(value: str, alpha: float) -> str:
    color = QColor(value)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha:.2f})"


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
    _POSITION_REANCHOR_TOLERANCE_MS = 750
    _POSITION_BACKWARD_REANCHOR_MS = 300

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._document: LyricsDocument | None = None
        self._active_line: LyricLine | None = None
        self._active_segment_index = -1
        self._active_segment_progress = 0.0
        self._playback_position_ms = 0
        self._playback_clock = QElapsedTimer()
        self._playback_clock.start()
        self._playback_active = False
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setInterval(16)
        self._highlight_timer.timeout.connect(self._on_highlight_tick)
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
        self._browse_offset = 0.0
        self._browse_content_height = 0
        self._line_rects: dict[str, QRect] = {}
        self._last_metrics: dict[str, int] = {}
        self.setObjectName("lyricsCanvasV2")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(260)
        self.return_button = QToolButton(self)
        self.return_button.setText("回到当前歌词")
        self.return_button.setObjectName("returnToCurrentLyrics")
        self.return_button.setIconSize(QSize(18, 18))
        self.return_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.return_button.setProperty("fluentIconFamily", "fluent_immersive")
        self.return_button.setProperty("fluentIconName", "return_current")
        self.return_button.setProperty("fluentIconFile", FLUENT_IMMERSIVE_ASSETS["return_current"])
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
            # Keep the approved 100% immersive baseline while scaling the
            # actual rendered size at every setting value. The former hard
            # lower bounds flattened 75%-112% into one visually identical
            # primary lyric size, making the live settings preview misleading.
            active = max(54, min(64, active))
            normal = max(29, min(38, normal))
            translation = max(18, min(26, translation))
            romanization = max(15, min(22, romanization))
            active_bounds, normal_bounds = (36, 76), (20, 52)
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
        self.return_button.setIcon(fluent_immersive_interactive_icon("return_current", theme, 18))
        self.return_button.setStyleSheet(
            "QToolButton#returnToCurrentLyrics {"
            "border: 1px solid transparent; border-radius: 11px; background: transparent; "
            f"padding: 6px 14px; min-height: 36px; color: {_rgba(theme.colors.text_primary, 0.88)};"
            "}"
            "QToolButton#returnToCurrentLyrics:hover {"
            f"background: {_rgba(theme.colors.text_primary, 0.08)}; border-color: transparent; color: {theme.colors.text_primary};"
            "}"
            "QToolButton#returnToCurrentLyrics:pressed {"
            f"background: {_rgba(theme.colors.text_primary, 0.13)}; border-color: transparent;"
            "}"
            "QToolButton#returnToCurrentLyrics:focus {"
            f"background: transparent; border: 1px solid {_rgba(theme.colors.focus_ring, 0.55)};"
            "}"
        )
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = "immersive" if mode == "immersive" else "ordinary"
        if self._mode != "immersive":
            self._highlight_timer.stop()
        self._refresh_ordinary_metrics()
        self.update()

    def set_document(self, document: LyricsDocument | None) -> None:
        self._document = document
        self._browse_anchor = -1
        self._browse_offset = 0.0
        self._browse_content_height = 0
        self.return_button.setVisible(False)
        self.update()

    def set_active_line(self, line: LyricLine | None) -> None:
        previous_id = self._active_line.id if self._active_line is not None else ""
        self._active_line = line
        if line is None or line.id != previous_id:
            self._active_segment_index = -1
            self._active_segment_progress = 0.0
        if self._playback_active and line is not None and line.segments and self._mode == "immersive":
            self._highlight_timer.start()
        self.update()

    def set_active_segment(self, line: LyricLine, index: int, progress: float) -> None:
        line_changed = self._active_line is None or line.id != self._active_line.id
        self._active_line = line
        incoming_index = int(index)
        incoming_progress = max(0.0, min(1.0, float(progress)))
        incoming_position = None
        if 0 <= index < len(line.segments):
            segment = line.segments[index]
            if segment.end_ms is not None and segment.end_ms > segment.start_ms:
                incoming_position = round(
                    segment.start_ms
                    + (segment.end_ms - segment.start_ms) * incoming_progress
                )
        predicted_position = self._interpolated_position_ms()
        reanchor = (
            not self._playback_active
            or self._mode != "immersive"
            or line_changed
            or self._active_segment_index < 0
            or (
                incoming_position is not None
                and (
                    incoming_position < predicted_position - self._POSITION_BACKWARD_REANCHOR_MS
                    or abs(incoming_position - predicted_position) > self._POSITION_REANCHOR_TOLERANCE_MS
                )
            )
        )
        if reanchor:
            self._active_segment_index = incoming_index
            self._active_segment_progress = incoming_progress
            if incoming_position is not None:
                self._set_playback_anchor(incoming_position)
        if self._playback_active and self._mode == "immersive":
            self._highlight_timer.start()
        self.update()

    def set_playback_position(self, position_ms: int, *, force: bool = False) -> None:
        """Correct local interpolation only when the shared clock actually drifts."""

        position = max(0, int(position_ms))
        predicted = self._interpolated_position_ms()
        if (
            force
            or not self._playback_active
            or position < predicted - self._POSITION_BACKWARD_REANCHOR_MS
            or abs(position - predicted) > self._POSITION_REANCHOR_TOLERANCE_MS
        ):
            self._set_playback_anchor(position)

    def set_playback_active(self, active: bool) -> None:
        """Refresh the visual highlight only while the shared player is running."""

        active = bool(active)
        if active == self._playback_active:
            if not active:
                self._highlight_timer.stop()
            return
        if not active and self._playback_active:
            self._playback_position_ms = self._interpolated_position_ms()
        self._playback_active = active
        self._playback_clock.restart()
        if self._playback_active and self._mode == "immersive" and self._active_line is not None and self._active_line.segments:
            self._highlight_timer.start()
        else:
            self._highlight_timer.stop()

    def _on_highlight_tick(self) -> None:
        if (
            not self._playback_active
            or self._mode != "immersive"
            or self.browsing
            or self._active_line is None
            or not self._active_line.segments
        ):
            return
        position = self._interpolated_position_ms()
        index, progress = self._segment_at_position(self._active_line, position)
        if index < 0:
            return
        if index != self._active_segment_index or abs(progress - self._active_segment_progress) >= 0.008:
            self._active_segment_index = index
            self._active_segment_progress = progress
            self.update()

    def _interpolated_position_ms(self) -> int:
        if not self._playback_active:
            return self._playback_position_ms
        return self._playback_position_ms + self._playback_clock.elapsed()

    def _set_playback_anchor(self, position_ms: int) -> None:
        self._playback_position_ms = max(0, int(position_ms))
        self._playback_clock.restart()

    @staticmethod
    def _segment_at_position(line: LyricLine, position_ms: int) -> tuple[int, float]:
        starts = tuple(segment.start_ms for segment in line.segments)
        index = bisect_right(starts, int(position_ms)) - 1
        if index < 0:
            return -1, 0.0
        segment = line.segments[index]
        end = segment.end_ms
        if end is None or end <= segment.start_ms:
            return index, 1.0
        progress = (int(position_ms) - segment.start_ms) / (end - segment.start_ms)
        return index, max(0.0, min(1.0, progress))

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
        self._browse_offset = 0.0
        self.return_button.setVisible(False)
        self.browsing_changed.emit(False)
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._document is None or not self._document.lines:
            event.ignore()
            return
        if not self.browsing:
            self._begin_browse()
        delta = event.pixelDelta().y()
        pixel_delta = bool(delta)
        if not delta:
            delta = event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        # Trackpads provide pixels directly.  A mouse wheel notch is mapped to
        # a comfortable distance instead of jumping exactly one lyric row.
        distance = float(delta) if pixel_delta else float(delta) * 0.65
        self._browse_offset = self._clamp_browse_offset(self._browse_offset - distance)
        self.update()
        event.accept()

    def _begin_browse(self) -> None:
        self._browse_anchor = self._active_index()
        self._browse_offset = self._offset_for_current_line()
        self.return_button.setVisible(True)
        self.browsing_changed.emit(True)

    def _offset_for_current_line(self) -> float:
        if self._document is None or not self._document.lines:
            return 0.0
        active_index = self._active_index()
        rows, content_height = self._browse_layout(active_index)
        self._browse_content_height = content_height
        if not rows:
            return 0.0
        active_row = rows[active_index]
        _index, _line, rect, _row_top, _row_bottom = active_row
        top_safe, bottom_safe, target_fraction = self._browse_viewport_metrics()
        target_center = top_safe + round((self.height() - top_safe - bottom_safe) * target_fraction)
        return self._clamp_browse_offset(rect.center().y() - target_center)

    def _clamp_browse_offset(self, value: float) -> float:
        maximum = max(0.0, float(self._browse_content_height - self.height()))
        return max(0.0, min(maximum, float(value)))

    def _browse_viewport_metrics(self) -> tuple[int, int, float]:
        ordinary_metrics = self._ordinary_metrics if self._mode == "ordinary" else None
        top_safe = ordinary_metrics.top_safe_area if ordinary_metrics is not None else 12
        bottom_safe = ordinary_metrics.bottom_safe_area if ordinary_metrics is not None else 12
        target_fraction = 0.45 if self._mode == "ordinary" else 0.48
        return top_safe, bottom_safe, target_fraction

    def _browse_layout(self, active_index: int) -> tuple[list[tuple[int, LyricLine, QRect, int, int]], int]:
        document = self._document
        if document is None or not document.lines:
            return [], 0
        sizes = self.effective_font_sizes
        text_width = min(self._max_text_width, max(240, self.width() - 40))
        top_safe, bottom_safe, _target_fraction = self._browse_viewport_metrics()
        x = max(20, (self.width() - text_width) // 2)
        rows: list[tuple[int, LyricLine, QRect, int, int]] = []
        y = top_safe
        for index, line in enumerate(document.lines):
            active = index == active_index
            distance = abs(index - active_index)
            font, lines = self._line_font_and_lines(line, active, distance, sizes, text_width)
            rect = self._text_rect(x, y, text_width, font, line.text, 5, lines=lines)
            row_bottom = y + self._line_height(line, active, distance, sizes)
            rows.append((index, line, rect, y, row_bottom))
            y = row_bottom
        return rows, y + bottom_safe

    def _paint_browsing(self, document: LyricsDocument) -> None:
        active_index = self._active_index()
        sizes = self.effective_font_sizes
        text_width = min(self._max_text_width, max(240, self.width() - 40))
        rows, content_height = self._browse_layout(active_index)
        self._browse_content_height = content_height
        self._browse_offset = self._clamp_browse_offset(self._browse_offset)
        offset = self._browse_offset
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        active_line_count = 0
        active_font_size = sizes[0]
        active_highlight_line_count = 0
        for index, line, source_rect, row_top, row_bottom in rows:
            screen_top = round(row_top - offset)
            screen_bottom = round(row_bottom - offset)
            if screen_bottom < 0 or screen_top > self.height():
                continue
            distance = abs(index - active_index)
            active = index == active_index
            font, lines = self._line_font_and_lines(line, active, distance, sizes, text_width)
            rect = self._text_rect(source_rect.x(), screen_top, source_rect.width(), font, line.text, 5, lines=lines)
            self._line_rects[line.id] = rect
            if active:
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
            y = screen_top + rect.height()
            if active and self._translation_visible and line.translation:
                sub_font = self._font(sizes[2], QFont.Weight.Medium)
                sub_rect = self._text_rect(source_rect.x(), y, text_width, sub_font, line.translation, 3)
                self._draw_text(painter, sub_rect, line.translation, sub_font, _with_alpha(self._theme.colors.secondary_text, 230), shadow=False)
                y += sub_rect.height() + 2
            if active and self._romanization_visible and line.romanization:
                roman_font = self._font(sizes[3], QFont.Weight.Normal)
                roman_rect = self._text_rect(source_rect.x(), y, text_width, roman_font, line.romanization, 3)
                self._draw_text(painter, roman_rect, line.romanization, roman_font, _with_alpha(self._theme.colors.subtle_text, 226), shadow=False)
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
            "browse_offset": round(self._browse_offset),
            "browse_content_height": self._browse_content_height,
        }

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
        if self.browsing:
            self._paint_browsing(document)
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
        target_y = target_center - active_center
        available_height = max(0, self.height() - top_safe - bottom_safe)
        if total_height <= available_height:
            y = max(top_safe, min(max(top_safe, self.height() - total_height - bottom_safe), target_y))
        else:
            # On compact lyric surfaces the context group can be taller than
            # the viewport.  Keep the active line in the reading band instead
            # of pinning the whole group to the top and making the current
            # line appear too low.
            y = target_y
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
        return max(9, round(11 * self._responsive_scale))

    def _section_spacing(self) -> int:
        if self._mode == "ordinary" and self._ordinary_metrics is not None:
            return self._ordinary_metrics.section_spacing
        return max(10, round((17 if self._mode == "ordinary" else 25) * self._responsive_scale))

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
        """Wrap without eliding and keep source offsets for smooth highlighting."""

        return [value for value, _start, _end in LyricsCanvasV2._wrapped_line_ranges(font, text, width)]

    @staticmethod
    def _wrapped_line_ranges(font: QFont, text: str, width: int) -> list[tuple[str, int, int]]:
        """Return displayed lines plus their source-text offsets.

        The painter must know which source characters belong to each visual
        line.  Reconstructing that relationship from ``len(wrapped)`` loses
        spaces at wrap boundaries and makes later glyphs snap into the accent
        color.  Keeping the offsets here lets the highlight use the exact
        same text that was measured by ``QFontMetrics``.
        """

        if not text:
            return [("", 0, 0)]
        metrics = QFontMetrics(font)
        available = max(1, int(width))
        ranges: list[tuple[str, int, int]] = []
        paragraphs = text.split("\n")
        source_offset = 0
        for paragraph_index, paragraph in enumerate(paragraphs):
            paragraph_start = source_offset
            paragraph_end = paragraph_start + len(paragraph)
            if not paragraph:
                ranges.append(("", paragraph_start, paragraph_start))
            else:
                start = paragraph_start
                while start < paragraph_end:
                    if metrics.horizontalAdvance(text[start:paragraph_end]) <= available:
                        visible_end = paragraph_end
                        while visible_end > start and text[visible_end - 1].isspace():
                            visible_end -= 1
                        ranges.append((text[start:visible_end], start, visible_end))
                        break

                    candidate_end = start
                    for end in range(start + 1, paragraph_end + 1):
                        if metrics.horizontalAdvance(text[start:end]) > available:
                            break
                        candidate_end = end
                    if candidate_end <= start:
                        candidate_end = min(paragraph_end, start + 1)

                    # Prefer a whitespace boundary when one fits; otherwise
                    # split at the last measured glyph that fits the width.
                    break_end = candidate_end
                    whitespace = -1
                    for index in range(start, candidate_end):
                        if text[index].isspace():
                            whitespace = index
                    if whitespace > start:
                        break_end = whitespace + 1

                    visible_end = break_end
                    while visible_end > start and text[visible_end - 1].isspace():
                        visible_end -= 1
                    ranges.append((text[start:visible_end], start, visible_end))
                    start = break_end
                    while start < paragraph_end and text[start].isspace():
                        start += 1

            source_offset = paragraph_end + 1
            if paragraph_index < len(paragraphs) - 1 and ranges and not ranges[-1][0]:
                ranges.append(("", source_offset, source_offset))
        return ranges or [("", 0, 0)]

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
        highlight_position = self._highlight_character_progress(line)
        if highlight_position <= 0:
            return 0
        drawn = 0
        metrics = QFontMetrics(font)
        line_height = metrics.height()
        start_y = rect.y() + max(0, (rect.height() - line_height * len(lines)) // 2)
        ranges = self._wrapped_line_ranges(font, line.text, rect.width())
        painter.setFont(font)
        painter.setPen(_with_alpha(self._theme.colors.accent, 255))
        for index, wrapped in enumerate(lines):
            if index >= len(ranges) or not wrapped:
                break
            _source_text, source_start, _source_end = ranges[index]
            local_progress = max(0.0, min(float(len(wrapped)), highlight_position - source_start))
            if local_progress <= 0:
                continue
            whole_count = min(len(wrapped), int(local_progress))
            fractional = local_progress - whole_count
            highlight_width = metrics.horizontalAdvance(wrapped[:whole_count])
            if fractional > 0 and whole_count < len(wrapped):
                highlight_width += metrics.horizontalAdvance(wrapped[whole_count]) * fractional
            if highlight_width <= 0:
                continue
            painter.save()
            painter.setClipRect(
                QRectF(
                    rect.x(),
                    start_y + index * line_height,
                    max(0.5, highlight_width),
                    line_height,
                ),
                Qt.ClipOperation.IntersectClip,
            )
            painter.drawText(
                QRect(rect.x(), start_y + index * line_height, rect.width(), line_height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                wrapped,
            )
            painter.restore()
            drawn += 1
        return drawn

    def _highlight_character_progress(self, line: LyricLine) -> float:
        """Return a fractional source-text offset for the active segment."""

        if not line.segments or line.id != (self._active_line.id if self._active_line else ""):
            return 0.0
        index = max(0, min(self._active_segment_index, len(line.segments) - 1))
        source_offset = 0
        for segment in line.segments[:index]:
            match = line.text.find(segment.text, source_offset)
            if match >= 0:
                source_offset = match + len(segment.text)
            else:
                source_offset += len(segment.text)
        current = line.segments[index].text
        current_start = line.text.find(current, source_offset)
        if current_start < 0:
            current_start = source_offset
        return min(
            float(len(line.text)),
            float(current_start) + len(current) * self._active_segment_progress,
        )

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
