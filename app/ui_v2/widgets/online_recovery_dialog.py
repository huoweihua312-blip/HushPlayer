"""Candidate picker used when online recovery finds multiple close matches."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.models.track import format_duration


class OnlineRecoveryCandidateDialog(QDialog):
    def __init__(self, candidates: tuple[OnlineTrack, ...], theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._candidates = tuple(candidates)
        self.selected_track: OnlineTrack | None = None
        self.setWindowTitle("选择在线版本")
        self.setMinimumSize(560, 360)
        self.setStyleSheet(build_stylesheet(theme))
        title = QLabel("找到多个相似的在线版本", self)
        title.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        detail = QLabel("请选择要播放的歌曲；原歌单歌曲不会被替换。", self)
        detail.setStyleSheet(f"color: {theme.colors.secondary_text};")
        self.list_widget = QListWidget(self)
        self.list_widget.setAccessibleName("在线候选歌曲")
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        for track in self._candidates:
            item = QListWidgetItem(self._label_for(track))
            item.setData(Qt.ItemDataRole.UserRole, track)
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        cancel = QPushButton("取消", self)
        cancel.clicked.connect(self.reject)
        play = QPushButton("播放选中", self)
        play.setDefault(True)
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
