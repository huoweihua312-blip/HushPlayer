"""右键「替换歌曲来源」对话框。

只做一件事：把一首在线歌曲的所有可播源候选列出来，让用户挑一条替换掉
原来的来源（记录 id 不变，收藏/歌单/历史都不丢）。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.theme import css_rgba, theme
from ..model.track import Track, format_duration
from ..online import models as online_models
from ..services.source_replace import SourceCandidate, SourceReplaceSearch
from .context import ctx
from .dialogs import CardDialog
from .widgets.common import TextButton


class TrackSourceDialog(CardDialog):
    """``exec()`` 返回 ``QDialog.Accepted`` 时 ``chosen`` 是选中的候选。"""

    def __init__(self, parent: QWidget | None, track: Track) -> None:
        super().__init__(parent, "替换歌曲来源", width=700)
        self._track = track
        self._search: SourceReplaceSearch | None = None
        self.chosen: SourceCandidate | None = None
        self._candidates: list[SourceCandidate] = []

        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(10)

        self.current_label = QLabel(
            f"当前：{track.display_title} — {track.display_artist} · {track.source_name or track.source_id}",
            body,
        )
        self.current_label.setObjectName("DialogText")
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        self.status = QLabel("正在其它音源里查找…", body)
        self.status.setObjectName("DialogHint")
        layout.addWidget(self.status)

        self.list = QListWidget(body)
        self.list.setMinimumWidth(560)
        self.list.setMinimumHeight(theme().scaled(240, factor=0.8))
        self.list.setObjectName("SourceCandidateList")
        self.list.setAlternatingRowColors(False)
        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_current())
        layout.addWidget(self.list, 1)

        self.add_named_button("取消", name="cancel")
        self.add_named_button("使用此来源", name="ok", accent=True)
        self.body.addWidget(body)

        self._apply_list_style()
        self.list.currentRowChanged.connect(self._sync_ok)
        self._sync_ok(-1)

    # -- lifecycle ------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().showEvent(event)
        if self._search is None:
            QTimer.singleShot(0, self._start_search)

    def _apply_list_style(self) -> None:
        p = theme().palette
        self.list.setStyleSheet(
            "QListWidget#SourceCandidateList {"
            f" background: transparent; border: none; outline: none;"
            f" }}"
            "QListWidget#SourceCandidateList::item {"
            " padding: 8px 10px; border-radius: 8px;"
            f" color: {p.text};"
            " }}"
            "QListWidget#SourceCandidateList::item:selected {"
            f" background: {css_rgba(p.accent, 0.18)}; color: {p.text};"
            " }}"
        )

    def _start_search(self) -> None:
        if self._candidates:
            return
        try:
            client = ctx().client
            sources = online_models.build_sources(client.sources)
        except Exception:  # pragma: no cover - defensive
            sources = []
        if not sources:
            self.status.setText("没有可用的在线音源，先在设置里添加音源再试。")
            return
        self._search = SourceReplaceSearch(client, self._track, sources, self._on_finished)
        self._search.start()

    # -- results --------------------------------------------------------
    def _on_finished(self, candidates: list[SourceCandidate], errors: list[str]) -> None:
        self._candidates = candidates
        self.list.clear()
        if not candidates:
            self.status.setText(
                "没有找到可替换的来源。" + (f"（{len(errors)} 个音源失败）" if errors else "")
            )
            self._sync_ok(-1)
            return
        for candidate in candidates:
            item = QListWidgetItem(f"{candidate.label}\n{candidate.detail} · 匹配 {candidate.score}")
            item.setToolTip(f"{candidate.label}\n{candidate.detail}\n匹配分 {candidate.score}")
            item.setData(Qt.UserRole, candidate)
            item.setSizeHint(QSize(0, theme().scaled(54, factor=0.7)))
            self.list.addItem(item)
        self.status.setText(
            f"{len(candidates)} 个候选，来自 {len({c.source_id for c in candidates})} 个音源。"
            + (f" {len(errors)} 个音源失败。" if errors else "")
        )
        self.list.setCurrentRow(0)
        self._sync_ok(self.list.currentRow())

    def _sync_ok(self, row: int) -> None:
        ok = self.button_for("ok")
        if ok is not None:
            ok.setEnabled(row >= 0)

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.chosen = item.data(Qt.UserRole)
        self.accept()
