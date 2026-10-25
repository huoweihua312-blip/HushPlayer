"""右键「替换歌曲来源」对话框。

只做一件事：把一首在线歌曲的所有可播源候选列出来，让用户挑一条替换掉
原来的来源（记录 id 不变，收藏/歌单/历史都不丢）。

界面要点：
- 结果**边到边显示**（不等最慢的音源），状态行带进度；
- 每条候选显示来源、专辑、时长、匹配分，以及「可能不是同一版本」的提示；
- 单击选中、双击立即替换；右下角按钮也走同一套「选中即替换」逻辑。
"""

from __future__ import annotations

import time
from typing import Sequence

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.theme import css_rgba, theme
from ..model.track import Track, format_duration
from ..online import models as online_models
from ..services.source_replace import (
    SourceCandidate,
    SourceReplaceSearch,
    clear_cache,
)
from .context import ctx
from .dialogs import CardDialog
from .widgets.common import TextButton


class TrackSourceDialog(CardDialog):
    """``exec()`` 返回 ``QDialog.Accepted`` 时 ``chosen`` 是选中的候选。"""

    def __init__(self, parent: QWidget | None, track: Track) -> None:
        super().__init__(parent, "替换歌曲来源", width=760)
        self._track = track
        self._search: SourceReplaceSearch | None = None
        self.chosen: SourceCandidate | None = None
        self._candidates: list[SourceCandidate] = []
        self._started_at = time.monotonic()

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

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.status = QLabel("正在其它音源里查找…", body)
        self.status.setObjectName("DialogHint")
        status_row.addWidget(self.status, 1)
        self.retry_button = TextButton("重新搜索", parent=body, size=28)
        self.retry_button.clicked.connect(self._restart_search)
        self.retry_button.setVisible(False)
        status_row.addWidget(self.retry_button)
        layout.addLayout(status_row)

        self.list = QListWidget(body)
        self.list.setMinimumWidth(600)
        self.list.setMinimumHeight(theme().scaled(260, factor=0.85))
        self.list.setObjectName("SourceCandidateList")
        self.list.setAlternatingRowColors(False)
        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_current())
        layout.addWidget(self.list, 1)

        self.add_named_button("取消", name="cancel")
        ok = self.add_named_button("使用此来源", name="ok", accent=True)
        # `add_named_button` 已经把 clicked 接到 done(Accepted)；这里再挂一个
        # 「提交前把当前行写进 chosen」，否则按钮点下去对话框关了、chosen 仍是
        # None，调用方以为用户取消 —— 这就是用户反馈「按钮没用」的原因。
        ok.clicked.connect(self._accept_current)
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
            " background: transparent; border: none; outline: none;"
            " }"
            "QListWidget#SourceCandidateList::item {"
            " padding: 8px 10px; border-radius: 8px;"
            f" color: {p.text};"
            " }"
            "QListWidget#SourceCandidateList::item:selected {"
            f" background: {css_rgba(p.accent, 0.18)}; color: {p.text};"
            " }"
        )

    def _start_search(self) -> None:
        if self._candidates:
            return
        self.retry_button.setVisible(False)
        self._started_at = time.monotonic()
        self.status.setText("正在其它音源里查找…")
        try:
            client = ctx().client
            sources = online_models.build_sources(client.sources)
        except Exception:  # pragma: no cover - defensive
            sources = []
        if not sources:
            self.status.setText("没有可用的在线音源，先在设置里添加音源再试。")
            self.retry_button.setVisible(True)
            return
        self._search = SourceReplaceSearch(
            client,
            self._track,
            sources,
            self._on_finished,
            on_update=self._on_update,
        )
        self._search.start()

    def _restart_search(self) -> None:
        clear_cache()
        self._candidates = []
        self.list.clear()
        self._sync_ok(-1)
        self._search = None
        self._start_search()

    # -- results --------------------------------------------------------
    def _render(self, candidates: list[SourceCandidate], errors: list[str]) -> None:
        previous = self._selected_remote()
        self._candidates = candidates
        self.list.blockSignals(True)
        self.list.clear()
        for candidate in candidates:
            lines = [candidate.label, candidate.detail + f" · 匹配 {candidate.score}"]
            if candidate.note:
                lines.append(f"提示：{candidate.note}")
            item = QListWidgetItem("\n".join(lines))
            item.setToolTip(f"{candidate.label}\n{candidate.detail}\n匹配分 {candidate.score}")
            item.setData(Qt.UserRole, candidate)
            height = 72 if candidate.note else 54
            item.setSizeHint(QSize(0, theme().scaled(height, factor=0.7)))
            self.list.addItem(item)
        self.list.blockSignals(False)
        if candidates:
            row = 0
            if previous:
                for index, candidate in enumerate(candidates):
                    if candidate.remote_id == previous:
                        row = index
                        break
            self.list.setCurrentRow(row)
        self._sync_ok(self.list.currentRow())
        if errors:
            pass  # errors 已体现在状态行里

    def _selected_remote(self) -> str:
        item = self.list.currentItem()
        if item is None:
            return ""
        candidate = item.data(Qt.UserRole)
        return candidate.remote_id if candidate else ""

    def _on_update(
        self, candidates: list[SourceCandidate], errors: list[str], done: int, total: int
    ) -> None:
        self._render(candidates, errors)
        elapsed = time.monotonic() - self._started_at if self._started_at else 0.0
        hint = f"已返回 {done}/{total} 个音源"
        if elapsed >= 1.0:
            hint += f" · {elapsed:.1f}s"
        if errors:
            hint += f" · {len(errors)} 个失败"
        self.status.setText(f"{len(candidates)} 个候选，{hint}")

    def _on_finished(self, candidates: list[SourceCandidate], errors: list[str]) -> None:
        self._render(candidates, errors)
        self.retry_button.setVisible(True)
        if not candidates:
            self.status.setText(
                "没有找到可替换的来源（已过滤掉标题/歌手/时长不符的结果）。"
                + (f" {len(errors)} 个音源失败。" if errors else "")
            )
            return
        sources = len({c.source_id for c in candidates})
        self.status.setText(
            f"{len(candidates)} 个候选，来自 {sources} 个音源（已过滤明显不符/试听片段）。"
            + (f" {len(errors)} 个音源失败。" if errors else "")
        )

    def _sync_ok(self, row: int) -> None:
        ok = self.button_for("ok")
        if ok is not None:
            ok.setEnabled(row >= 0)

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        candidate = item.data(Qt.UserRole)
        if candidate is None:
            return
        self.chosen = candidate
        self.accept()
