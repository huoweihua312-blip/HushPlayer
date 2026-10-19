"""歌词手动搜索对话框（LRCLIB）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from ...core.theme import css_rgba, theme
from ...lyrics.service import LyricsCandidate
from ..context import ctx
from ..widgets.common import TextButton
from ..widgets.searchfield import SearchField


class LyricsSearchDialog(QDialog):
    """Search LRCLIB by free text and pick a replacement lyric."""

    def __init__(self, parent: QWidget | None = None, *, initial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("搜索歌词")
        self.setMinimumSize(620, 460)
        self.candidate: LyricsCandidate | None = None
        self._results: list[LyricsCandidate] = []

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
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        body.addWidget(self.list, 3)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(theme().font(9.0))
        self.preview.setPlaceholderText("选择左侧结果以预览歌词")
        body.addWidget(self.preview, 2)
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
        self.status.setText(f"正在搜索「{query}」…")
        self.search_button.setEnabled(False)
        ctx().lyrics.search(query)

    def _on_results(self, candidates: list[LyricsCandidate]) -> None:
        self.search_button.setEnabled(True)
        self._results = list(candidates)
        self.list.clear()
        for candidate in self._results:
            timing = "逐行时间轴" if candidate.has_timing else "纯文本"
            item = QListWidgetItem(
                f"{candidate.title or '未知歌曲'} — {candidate.artist}\n"
                f"{candidate.album or '未知专辑'} · {candidate.duration_text} · {timing}"
            )
            self.list.addItem(item)
        if not self._results:
            self.status.setText("没有找到歌词，换个关键词试试")
            self.apply_button.setEnabled(False)
            return
        self.status.setText(f"找到 {len(self._results)} 条结果，双击可直接使用")
        self.list.setCurrentRow(0)

    def _on_failed(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.status.setText(message)

    def _on_row(self, row: int) -> None:
        if 0 <= row < len(self._results):
            candidate = self._results[row]
            text = candidate.synced or candidate.plain
            self.preview.setPlainText("\n".join(text.splitlines()[:80]))
            self.apply_button.setEnabled(True)
        else:
            self.preview.clear()
            self.apply_button.setEnabled(False)

    def _accept(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._results):
            self.candidate = self._results[row]
            self.accept()
