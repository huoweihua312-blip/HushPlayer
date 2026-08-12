"""Candidate picker used when online recovery finds multiple close matches."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.theme.styles import build_dialog_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.models.track import format_duration
from app.ui_v2.widgets.elided_label import ElidedLabel


class _CandidateRow(QFrame):
    """Stable two-line candidate presentation that never relies on wrapping."""

    def __init__(self, track: OnlineTrack, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("onlineRecoveryCandidateRow")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_label = ElidedLabel(self)
        self.title_label.set_full_text(f"{track.title}  —  {track.artist}")
        self.detail_label = ElidedLabel(self)
        self.detail_label.set_full_text(
            f"{track.album} · {track.source_name} · {format_duration(track.duration_ms)}"
        )
        self.title_label.setAccessibleName("歌曲标题和歌手")
        self.detail_label.setAccessibleName("专辑、来源和时长")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        self.setMinimumHeight(56)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )


class OnlineRecoveryCandidateDialog(QDialog):
    def __init__(self, candidates: tuple[OnlineTrack, ...], theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._candidates = tuple(candidates)
        self.selected_track: OnlineTrack | None = None
        self.setWindowTitle("选择在线版本")
        self.setObjectName("onlineRecoveryCandidateDialog")
        self.setMinimumSize(640, 430)
        self.resize(720, min(560, 300 + min(8, len(self._candidates)) * 28))
        self.setStyleSheet(build_dialog_stylesheet(theme))
        title = QLabel("找到多个相似的在线版本", self)
        title.setObjectName("onlineRecoveryTitle")
        title.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        detail = QLabel(
            f"选择一个版本后将只更换播放来源，保留歌单位置和收藏关系（共 {len(self._candidates)} 个候选）。",
            self,
        )
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {theme.colors.secondary_text};")
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("onlineRecoveryCandidateList")
        self.list_widget.setAccessibleName("在线候选歌曲")
        self.list_widget.setAccessibleDescription("使用方向键选择版本，按 Enter 替换播放来源并播放")
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setSpacing(4)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        for track in self._candidates:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setToolTip(self._label_for(track))
            row = _CandidateRow(track, theme, self.list_widget)
            item.setSizeHint(QSize(0, 60))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        else:
            self.list_widget.setEnabled(False)
        cancel = QPushButton("取消", self)
        cancel.setAccessibleName("取消在线版本选择")
        cancel.clicked.connect(self.reject)
        play = QPushButton("替换播放来源并播放", self)
        play.setAccessibleName("替换播放来源并播放")
        play.setProperty("role", "primary")
        play.setMinimumWidth(168)
        play.setDefault(True)
        play.setEnabled(bool(self._candidates))
        play.clicked.connect(self._accept_selected)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(play)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(buttons)
        cancel.setFocus()

    @staticmethod
    def _label_for(track: OnlineTrack) -> str:
        duration = format_duration(track.duration_ms)
        return f"{track.title}  —  {track.artist}\n{track.album} · {track.source_name} · {duration}"

    def _accept_selected(self) -> None:
        item = self.list_widget.currentItem()
        track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(track, OnlineTrack):
            self.selected_track = track
            self.accept()
