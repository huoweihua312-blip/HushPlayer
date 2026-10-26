"""歌词手动搜索对话框（LRCLIB）。

结果列表用自绘行：选中行有底色、左侧强调条与「已选中」标记，避免用户在
一长串相似结果里看不出当前选的是哪一条。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.theme import css_rgba, draw_text, rgba, theme
from ...lyrics.service import LyricsCandidate
from ...online.matching import normalize_text
from ..context import ctx
from ..widgets.common import TextButton
from ..widgets.searchfield import SearchField

ROW_HEIGHT = 76


def _match_reason(candidate: LyricsCandidate, title: str, artist: str, duration_ms: int) -> str:
    reasons: list[str] = []
    want_title = normalize_text(title)
    want_artist = normalize_text(artist)
    got_title = normalize_text(candidate.title)
    got_artist = normalize_text(candidate.artist)
    if want_title and got_title:
        if got_title == want_title:
            reasons.append("歌名匹配")
        elif want_title in got_title or got_title in want_title:
            reasons.append("歌名相近")
    if want_artist and got_artist and (want_artist in got_artist or got_artist in want_artist):
        reasons.append("歌手匹配")
    if duration_ms and candidate.duration_ms:
        if abs(duration_ms - candidate.duration_ms) <= 2500:
            reasons.append("时长接近")
    if candidate.has_timing:
        reasons.append("时间轴")
    return " · ".join(reasons)


class _ResultRow(QWidget):
    """一条搜索结果：标题、歌手/专辑/时长、匹配理由。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._selected = False
        self._candidate: LyricsCandidate | None = None
        self._reason = ""
        self._index = 0
        self.setFixedHeight(ROW_HEIGHT)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(320, ROW_HEIGHT)

    def set_data(self, index: int, candidate: LyricsCandidate, reason: str) -> None:
        self._index = index
        self._candidate = candidate
        self._reason = reason
        self.update()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = theme().palette
        rect = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        if self._selected:
            painter.setPen(QPen(rgba(palette.accent, 0.55), 1))
            painter.setBrush(rgba(palette.accent, 0.16))
            painter.drawRoundedRect(rect, 9, 9)
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.accent, 0.95))
            painter.drawRoundedRect(QRectF(rect.left() + 1, rect.top() + 8, 3, rect.height() - 16), 2, 2)
        else:
            painter.setPen(QPen(rgba(palette.text, 0.06), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 9, 9)

        candidate = self._candidate
        if candidate is None:
            painter.end()
            return
        left = rect.left() + 14
        badge_width = 58 if self._selected and rect.width() > 260 else 0
        width = rect.width() - 28 - badge_width
        title_font = theme().font(9.8, 600)
        meta_font = theme().font(8.6)
        reason_font = theme().font(8.2)

        painter.setFont(title_font)
        painter.setPen(QColor(palette.text))
        tags = f"{self._index + 1:02d}"
        title_text = QFontMetrics(title_font).elidedText(
            f"{tags}  {candidate.title or '未知歌曲'}", Qt.ElideRight, int(width)
        )
        draw_text(painter, QRectF(left, rect.top() + 8, width, 18), Qt.AlignLeft | Qt.AlignVCenter, title_text)

        if badge_width:
            badge = QRectF(rect.right() - 14 - 52, rect.top() + 9, 52, 17)
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.accent, 0.9))
            painter.drawRoundedRect(badge, 8, 8)
            painter.setFont(theme().font(7.6, 600))
            painter.setPen(QColor("#ffffff"))
            draw_text(painter, badge, Qt.AlignCenter, "已选中")

        painter.setFont(meta_font)
        painter.setPen(QColor(rgba(palette.text, 0.62)))
        meta = " · ".join(
            part
            for part in (
                candidate.artist or "未知歌手",
                candidate.album or "",
                candidate.duration_text,
            )
            if part
        )
        meta_text = QFontMetrics(meta_font).elidedText(meta, Qt.ElideRight, int(rect.width() - 28))
        draw_text(painter, QRectF(left, rect.top() + 29, rect.width() - 28, 16), Qt.AlignLeft | Qt.AlignVCenter, meta_text)

        painter.setFont(reason_font)
        painter.setPen(QColor(rgba(palette.text, 0.72 if self._selected else 0.42)))
        reason_text = QFontMetrics(reason_font).elidedText(self._reason or "无匹配信息", Qt.ElideRight, int(rect.width() - 28))
        draw_text(painter, QRectF(left, rect.top() + 50, rect.width() - 28, 15), Qt.AlignLeft | Qt.AlignVCenter, reason_text)
        painter.end()


class LyricsSearchDialog(QDialog):
    """Search LRCLIB by structured track info and pick a replacement lyric."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial: str = "",
        title: str = "",
        artist: str = "",
        album: str = "",
        duration_ms: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("搜索歌词")
        self.setMinimumSize(760, 520)
        self.candidate: LyricsCandidate | None = None
        self._results: list[LyricsCandidate] = []
        self._rows: list[_ResultRow] = []
        self._title = title.strip()
        self._artist = artist.strip()
        self._album = album.strip()
        self._duration_ms = int(duration_ms or 0)
        self._initial = initial.strip()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.field = SearchField("输入歌曲名、歌手或专辑")
        self.field.setMinimumWidth(360)
        self.field.submitted.connect(self._search)
        self.search_button = TextButton("搜索", icon_name="search", size=30, accent=True)
        self.search_button.clicked.connect(self._search)
        row.addWidget(self.field, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)

        self.status = QLabel("输入关键词后在 LRCLIB 中查找歌词")
        self.status.setFont(theme().font(8.8))
        self.status.setStyleSheet(f"color: {css_rgba(theme().palette.text, 0.55)};")
        layout.addWidget(self.status)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.list = QListWidget()
        self.list.setFont(theme().font(9.2))
        self.list.setSpacing(2)
        self.list.setStyleSheet(
            f"QListWidget{{background:transparent;border:none;outline:none;}}"
            f"QListWidget::item{{border:none;padding:0;margin:0;}}"
            f"QListWidget::item:selected{{background:transparent;}}"
        )
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        body.addWidget(self.list, 5)

        preview_box = QVBoxLayout()
        preview_box.setSpacing(6)
        self.selection_label = QLabel("未选择歌词")
        self.selection_label.setFont(theme().font(9.0, 600))
        self.selection_label.setStyleSheet(f"color: {css_rgba(theme().palette.text, 0.86)};")
        preview_box.addWidget(self.selection_label)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(theme().font(9.0))
        self.preview.setPlaceholderText("选择左侧结果以预览歌词")
        preview_box.addWidget(self.preview, 1)
        body.addLayout(preview_box, 4)
        layout.addLayout(body, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = TextButton("取消", size=30)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button = TextButton("使用这首歌的歌词", icon_name="check", size=30, accent=True)
        self.apply_button.clicked.connect(self._accept)
        self.apply_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        layout.addLayout(buttons)

        service = ctx().lyrics
        service.search_finished.connect(self._on_results)
        service.search_failed.connect(self._on_failed)

        if initial:
            self.field.set_text(initial)
            self._search(initial)

    # ------------------------------------------------------------------
    def _search(self, text: str = "") -> None:
        query = (text or self.field.text()).strip()
        if not query:
            self.status.setText("请输入关键词")
            return
        # 字段被用户改过就不再套用原曲的结构化参数，但仍优先按歌名查询。
        edited = query != self._initial and query != f"{self._title} {self._artist}".strip()
        title = query if edited else self._title or query
        artist = "" if edited else self._artist
        self.status.setText(f"正在搜索「{query}」…")
        self.search_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        ctx().lyrics.search(
            query,
            title=title,
            artist=artist,
            album="" if edited else self._album,
            duration_ms=self._duration_ms,
        )

    def _on_results(self, candidates: list[LyricsCandidate]) -> None:
        self.search_button.setEnabled(True)
        self._results = list(candidates)
        self.list.clear()
        self._rows.clear()
        for index, candidate in enumerate(self._results):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self.list.addItem(item)
            row = _ResultRow(self.list)
            row.set_data(
                index,
                candidate,
                _match_reason(candidate, self._title, self._artist, self._duration_ms),
            )
            self.list.setItemWidget(item, row)
            self._rows.append(row)
        if not self._results:
            self.status.setText("没有找到歌词，换个关键词试试")
            self.apply_button.setEnabled(False)
            self.selection_label.setText("未选择歌词")
            return
        self.status.setText(f"找到 {len(self._results)} 条结果，双击可直接使用")
        self.list.setCurrentRow(0)

    def _on_failed(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.status.setText(message)

    def _on_row(self, row: int) -> None:
        for index, widget in enumerate(self._rows):
            widget.set_selected(index == row)
        if 0 <= row < len(self._results):
            candidate = self._results[row]
            text = candidate.synced or candidate.plain
            self.preview.setPlainText("\n".join(text.splitlines()[:80]))
            timing = "逐行时间轴" if candidate.has_timing else "纯文本"
            self.selection_label.setText(
                f"已选中：{candidate.title or '未知歌曲'} · {candidate.artist or '未知歌手'}"
                f"  （{timing}）"
            )
            self.apply_button.setEnabled(True)
        else:
            self.preview.clear()
            self.selection_label.setText("未选择歌词")
            self.apply_button.setEnabled(False)

    def _accept(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._results):
            self.candidate = self._results[row]
            self.accept()
