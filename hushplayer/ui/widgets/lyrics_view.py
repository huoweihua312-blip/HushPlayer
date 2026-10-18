"""歌词视图：可复用的同步歌词渲染控件。

`LyricsBody` 负责排版与绘制（逐行/逐词高亮），`LyricsView` 负责滚动跟随与状态。
沉浸式播放器与普通歌词页共用同一套渲染逻辑，保证两处高亮时间轴完全一致。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from ...core.theme import rgba, theme
from ...model.lyrics import LyricDocument, LyricLine


class LyricsBody(QWidget):
    """按行绘制的歌词画布。"""

    seek_requested = Signal(int)
    active_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._document: LyricDocument | None = None
        self._position = 0
        self._index = -1
        self._font_scale = 1.0
        self._show_translation = True
        self._alignment = Qt.AlignLeft
        self._rows: list[tuple[LyricLine, float, float]] = []  # line, top, height
        self._content_height = 0
        self._hover_row = -1
        self._top_pad = 26.0
        self._bottom_pad = 32.0
        self._active_color = "#ffffff"
        self._inactive_color = "#8a8a92"
        self._accent = "#C95770"
        self._trans_color = "#7a7a82"
        self._hint_color = "#6a6a72"
        self._empty_text = "暂无歌词"
        self._empty_hint = ""

    # ------------------------------------------------------------------ 数据
    def set_document(self, document: LyricDocument | None) -> None:
        self._document = document
        self._index = -1
        self._position = 0
        self._relayout()

    def document(self) -> LyricDocument | None:
        return self._document

    def set_empty_text(self, text: str, hint: str = "") -> None:
        self._empty_text = text
        self._empty_hint = hint
        self.update()

    def set_font_scale(self, scale: float) -> None:
        scale = max(0.6, min(2.0, float(scale)))
        if abs(scale - self._font_scale) < 0.01:
            return
        self._font_scale = scale
        self._relayout()

    def set_show_translation(self, enabled: bool) -> None:
        if enabled == self._show_translation:
            return
        self._show_translation = bool(enabled)
        self._relayout()

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        if alignment == self._alignment:
            return
        self._alignment = alignment
        self.update()

    def set_vertical_padding(self, top: float, bottom: float) -> None:
        top = max(12.0, float(top))
        bottom = max(12.0, float(bottom))
        if abs(top - self._top_pad) < 1 and abs(bottom - self._bottom_pad) < 1:
            return
        self._top_pad = top
        self._bottom_pad = bottom
        self._relayout()

    def refresh_theme(self) -> None:
        palette = theme().palette
        self._active_color = palette.text
        self._inactive_color = rgba(palette.text, 0.40)
        self._accent = palette.accent
        self._trans_color = rgba(palette.text, 0.45)
        self._hint_color = rgba(palette.text, 0.34)
        self._relayout()

    # ------------------------------------------------------------------ 布局
    def _line_font(self) -> QFont:
        base = 18.0 * self._font_scale
        if self.height() > 900:
            base += 1.5
        return theme().font(base, 600)

    def _trans_font(self) -> QFont:
        return theme().font(max(9.5, 12.6 * self._font_scale), 400)

    def _relayout(self) -> None:
        font = self._line_font()
        metrics = QFontMetrics(font)
        trans_metrics = QFontMetrics(self._trans_font())
        rows: list[tuple[LyricLine, float, float]] = []
        top = self._top_pad
        document = self._document
        if document and document.lines:
            line_gap = 9.0 * self._font_scale
            for line in document.lines:
                height = float(metrics.height())
                if self._show_translation and line.translation.strip():
                    height += trans_metrics.height() + 3
                rows.append((line, top, height))
                top += height + max(12.0, line_gap + metrics.height() * 0.55)
        self._rows = rows
        self._content_height = int(top + self._bottom_pad)
        self.setMinimumHeight(self._content_height)
        self.updateGeometry()
        self.update()

    # ------------------------------------------------------------------ 播放
    def set_position(self, position_ms: int) -> None:
        self._position = max(0, int(position_ms))
        index = self._document.index_at(self._position) if self._document else -1
        if index != self._index:
            self._index = index
            self.active_changed.emit(index)
        self.update()

    @property
    def active_index(self) -> int:
        return self._index

    def row_center(self, index: int) -> float:
        if 0 <= index < len(self._rows):
            _line, top, height = self._rows[index]
            return top + height / 2
        return self._content_height / 2

    def row_top(self, index: int) -> float:
        if 0 <= index < len(self._rows):
            return self._rows[index][1]
        return 0.0

    def content_height(self) -> int:
        return self._content_height

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        document = self._document
        if not document or not document.lines:
            self._paint_empty(painter)
            painter.end()
            return

        clip = QRectF(self.rect()).adjusted(0, -4, 0, 4)
        painter.setClipRect(clip)
        font = self._line_font()
        metrics = QFontMetrics(font)
        trans_font = self._trans_font()
        center = self._alignment & Qt.AlignHCenter
        max_width = max(120, self.width() - 8)

        for index, (line, top, height) in enumerate(self._rows):
            if top > self.height() + 260 or top + height < -260:
                continue
            active = index == self._index
            hovered = index == self._hover_row and not active
            if active:
                text_color = QColor(self._active_color)
            elif hovered:
                text_color = rgba(self._active_color, 0.62)
            else:
                text_color = QColor(self._inactive_color)
            text = line.text or " "
            elided = metrics.elidedText(text, Qt.ElideNone, int(max_width * 1.6)) if text else text
            text_width = metrics.horizontalAdvance(elided)
            x = (self.width() - text_width) / 2 if center else 0.0
            baseline = top + metrics.ascent()

            painter.setFont(font)
            painter.setPen(QPen(QColor(text_color)))
            painter.drawText(QPointF(x, baseline), elided)

            # 逐词 / 逐字高亮：用真实时间数据算出扫过位置，再裁剪重绘
            if active and document.synced:
                cut = self._sweep_offset(line, index, metrics, elided)
                if cut > 0:
                    sung_rect = QRectF(x - 4, top - 8, cut + 4, metrics.height() + 10)
                    painter.save()
                    painter.setClipRect(sung_rect)
                    painter.setPen(QPen(QColor(self._accent)))
                    painter.drawText(QPointF(x, baseline), elided)
                    painter.restore()

            if self._show_translation and line.translation.strip():
                trans_top = top + metrics.height() + 3
                painter.setFont(trans_font)
                painter.setPen(QPen(QColor(self._trans_color if not active else rgba(theme().palette.text, 0.55))))
                trans_width = QFontMetrics(trans_font).horizontalAdvance(line.translation)
                tx = (self.width() - trans_width) / 2 if center else 0.0
                painter.drawText(QPointF(tx, trans_top + QFontMetrics(trans_font).ascent()), line.translation)

        painter.end()

    def _sweep_offset(self, line: LyricLine, index: int, metrics: QFontMetrics, text: str) -> float:
        target = self._position - (self._document.offset_ms if self._document else 0)
        if not line.words:
            progress = self._progress(index)
            return metrics.horizontalAdvance(text) * progress
        width = 0.0
        for word in line.words:
            word_width = metrics.horizontalAdvance(word.text)
            if target >= word.end_ms:
                width += word_width
                continue
            if target <= word.start_ms:
                break
            span = max(1, word.end_ms - word.start_ms)
            width += word_width * max(0.0, min(1.0, (target - word.start_ms) / span))
            break
        return width

    def _progress(self, index: int) -> float:
        document = self._document
        if not document:
            return 0.0
        return document.line_progress(index, self._position)

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(self._active_color)))
        painter.setFont(theme().font(15.0, 600))
        title_rect = QRectF(0, self.height() / 2 - 26, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._empty_text)
        if self._empty_hint:
            painter.setPen(QPen(QColor(self._hint_color)))
            painter.setFont(theme().font(9.6))
            hint_rect = QRectF(0, self.height() / 2 + 4, self.width(), 40)
            painter.drawText(
                hint_rect,
                Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                self._empty_hint,
            )

    # ------------------------------------------------------------------ 交互
    def _row_at(self, y: float) -> int:
        for index, (_line, top, height) in enumerate(self._rows):
            if top <= y <= top + height:
                return index
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        row = self._row_at(event.position().y())
        if row != self._hover_row:
            self._hover_row = row
            self.setCursor(Qt.PointingHandCursor if row >= 0 else Qt.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_row != -1:
            self._hover_row = -1
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._document and self._document.synced:
            row = self._row_at(event.position().y())
            if 0 <= row < len(self._rows):
                self.seek_requested.emit(int(self._rows[row][0].start_ms))
                return
        super().mousePressEvent(event)


class LyricsView(QWidget):
    """滚动容器 + 跟随逻辑 + 空状态。"""

    seek_requested = Signal(int)
    active_changed = Signal(int)

    FOLLOW_SETTLE_MS = 6000

    def __init__(self, parent: QWidget | None = None, *, centered: bool = False) -> None:
        super().__init__(parent)
        self._follow = True
        self._pad_top_ratio = 0.42
        self._pad_bottom_ratio = 0.55
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.setInterval(self.FOLLOW_SETTLE_MS)
        self._follow_timer.timeout.connect(self._resume_follow)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}QScrollArea>QWidget>QWidget{background:transparent;}")
        self.scroll.viewport().setAutoFillBackground(False)
        self.body = LyricsBody(self.scroll)
        self.body.set_empty_text("暂无歌词")
        self.body.set_alignment(Qt.AlignHCenter if centered else Qt.AlignLeft)
        self.scroll.setWidget(self.body)
        self.body.seek_requested.connect(self.seek_requested)
        self.body.active_changed.connect(self._on_active)

        from PySide6.QtWidgets import QVBoxLayout

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

        self._scroll_anim = QVariantAnimation(self)
        self._scroll_anim.setDuration(420)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_anim.valueChanged.connect(self._apply_scroll)
        self._programmatic = False
        self._last_value = 0
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value)
        self.body.installEventFilter(self)

    # ------------------------------------------------------------------ 数据
    def set_document(self, document: LyricDocument | None) -> None:
        self._ensure_padding()
        self.body.set_document(document)
        self.body.setMinimumHeight(max(120, self.body.content_height()))
        self.scroll.verticalScrollBar().setValue(0)
        self._last_value = 0
        self._follow = True
        self._pad_top_ratio = 0.42
        self._pad_bottom_ratio = 0.55
        self._follow_timer.stop()

    def document(self) -> LyricDocument | None:
        return self.body.document()

    def set_position(self, position_ms: int) -> None:
        had_lines = bool(self.body.document() and self.body.document().lines)
        previous = self.body.active_index
        self.body.set_position(position_ms)
        if not had_lines:
            return
        index = self.body.active_index
        if index != previous:
            self._follow = True
            self._scroll_to_index(index, animate=True)

    def set_font_scale(self, scale: float) -> None:
        self.body.set_font_scale(scale)

    def set_show_translation(self, enabled: bool) -> None:
        self.body.set_show_translation(enabled)

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self.body.set_alignment(alignment)

    def set_empty_text(self, text: str, hint: str = "") -> None:
        self.body.set_empty_text(text, hint)

    def refresh_theme(self) -> None:
        self.body.refresh_theme()
        self._scroll_to_index(self.body.active_index, animate=False)

    # ------------------------------------------------------------------ 滚动
    def _on_active(self, index: int) -> None:
        self.active_changed.emit(index)

    def _viewport_center(self) -> float:
        return self.scroll.viewport().height() / 2

    def set_padding_ratio(self, top: float, bottom: float) -> None:
        self._pad_top_ratio = max(0.0, min(1.0, top))
        self._pad_bottom_ratio = max(0.0, min(1.0, bottom))
        self._ensure_padding()

    def _ensure_padding(self) -> None:
        height = max(120, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * self._pad_top_ratio, height * self._pad_bottom_ratio)

    def _scroll_to_index(self, index: int, *, animate: bool) -> None:
        if index < 0:
            return
        self._ensure_padding()
        bar = self.scroll.verticalScrollBar()
        target = int(self.body.row_center(index) - self._viewport_center())
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._move_to(target, animate=animate)

    def _move_to(self, target: int, *, animate: bool) -> None:
        self._scroll_anim.stop()
        if theme().reduce_motion or not animate:
            self._programmatic = True
            self._apply_scroll(target)
            self._programmatic = False
            return
        start = self.scroll.verticalScrollBar().value()
        if abs(target - start) < 2:
            return
        self._scroll_anim.setStartValue(start)
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def _apply_scroll(self, value) -> None:
        self._programmatic = True
        self.scroll.verticalScrollBar().setValue(int(value))
        self._programmatic = False

    def _on_scroll_value(self, value: int) -> None:
        self._last_value = value
        if self._programmatic:
            return
        # 用户手动滚动：暂停跟随，静置后恢复
        self._follow = False
        self._follow_timer.start()

    def _resume_follow(self) -> None:
        self._follow = True
        self._scroll_to_index(self.body.active_index, animate=True)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.body and event.type() in (QEvent.Wheel, QEvent.MouseButtonPress):
            if event.type() == QEvent.Wheel:
                self._follow = False
                self._follow_timer.start()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        height = max(200, self.scroll.viewport().height())
        self.body.set_vertical_padding(height * 0.42, height * 0.55)
        self._scroll_to_index(self.body.active_index, animate=False)
