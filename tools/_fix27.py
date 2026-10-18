import pathlib
p = pathlib.Path("hushplayer/ui/desktop_lyrics.py")
t = p.read_text(encoding="utf-8")

start = t.index("    def _resize_for_content(self) -> None:")
end = t.index("    def _screen(self):")
new_resize = '''    def _metrics_slots(self) -> tuple[int, int, int, int]:
        """返回 (padding, 主行高, 翻译行高, 下一行高)。"""
        fs = self._font_size
        pad = max(6, int(fs * 0.26))
        main_h = int(fs * 1.34)
        trans_h = int(fs * 0.64) if self._show_translation else 0
        next_h = int(fs * 0.98) if self._lines >= 2 else 0
        return pad, main_h, trans_h, next_h

    def _resize_for_content(self) -> None:
        screen = self._screen()
        width = int(min(max(680, screen.availableGeometry().width() * 0.56), 1500))
        pad, main_h, trans_h, next_h = self._metrics_slots()
        height = pad * 2 + main_h + trans_h + next_h
        self.resize(width, max(76, height))

'''
t = t[:start] + new_resize + t[end:]

start = t.index("    def paintEvent(self, _event) -> None:  # noqa: N802")
end = t.index("    def _paint_placeholder(self, painter: QPainter) -> None:")
new_paint = '''    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        document = self._document
        if document is None or document.is_empty():
            self._paint_placeholder(painter)
            painter.end()
            return

        index = document.index_at(self._position)
        if index < 0:
            index = 0
        if index >= len(document.lines):
            index = len(document.lines) - 1
        line = document.lines[index]

        pad, main_h, trans_h, next_h = self._metrics_slots()
        rect = QRectF(self.rect())
        left = rect.left() + 20
        width = rect.width() - 40
        top = rect.top() + pad

        primary = self._line_font(1.0)
        metrics = QFontMetrics(primary)
        text = line.text or "♪"
        main_rect = QRectF(left, top, width, main_h)
        self._draw_line(
            painter,
            main_rect,
            text,
            primary,
            QColor(self._color),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        cut = self._sweep_chars(document, line, index)
        if cut > 0:
            self._paint_sweep(painter, main_rect, text, cut, metrics, QColor(self._highlight))

        y = top + main_h
        if self._show_translation and trans_h:
            if line.translation:
                self._draw_line(
                    painter,
                    QRectF(left, y, width, trans_h),
                    line.translation,
                    self._line_font(0.54, 500),
                    rgba(self._color, 0.72),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                )
            y += trans_h

        if self._lines >= 2 and next_h:
            next_text = ""
            if index + 1 < len(document.lines):
                next_text = document.lines[index + 1].text
            if next_text:
                self._draw_line(
                    painter,
                    QRectF(left, y + 2, width, next_h - 2),
                    next_text,
                    self._line_font(0.62, 600),
                    rgba(self._color, 0.58),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                )
        painter.end()

    def _draw_line(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        font: QFont,
        color: QColor,
        alignment: Qt.AlignmentFlag,
    ) -> None:
        painter.setFont(font)
        painter.setPen(QPen(QColor(0, 0, 0, 170)))
        painter.drawText(rect.translated(1.4, 2.0), alignment, text)
        painter.setPen(QPen(color))
        painter.drawText(rect, alignment, text)

'''
t = t[:start] + new_paint + t[end:]

start = t.index("    def _paint_sweep(")
end = t.index("__all__ = [")
new_sweep = '''    def _paint_sweep(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        cut: int,
        metrics: QFontMetrics,
        highlight: QColor,
    ) -> None:
        if cut <= 0:
            return
        total = metrics.horizontalAdvance(text)
        prefix = metrics.horizontalAdvance(text[:cut])
        if total <= 0 or prefix <= 0:
            return
        left = rect.center().x() - total / 2
        painter.save()
        painter.setClipRect(QRectF(left - 2, rect.top(), prefix + 2, rect.height()))
        painter.setPen(QPen(highlight))
        painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


'''
t = t[:start] + new_sweep + t[end:]
p.write_text(t, encoding="utf-8")
print("rewritten")
