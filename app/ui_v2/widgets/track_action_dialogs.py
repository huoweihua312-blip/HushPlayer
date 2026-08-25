"""Small read-only dialogs used by song context-menu actions."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.styles import build_dialog_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.track_display import present_track_identity


class TrackInfoDialog(QDialog):
    """Non-modal read-only information surface for a local or online track."""

    def __init__(self, theme: Theme, track: Track, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("trackInfoDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(False)
        self.setWindowTitle("歌曲信息")
        self.setMinimumWidth(440)

        self.title_label = QLabel(self)
        self.title_label.setObjectName("trackInfoTitle")
        self.detail_label = QLabel(self)
        self.detail_label.setObjectName("trackInfoDetail")
        self.detail_label.setWordWrap(True)
        self.form = QFormLayout()
        self.form.setContentsMargins(0, 8, 0, 0)
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(8)
        self.close_button = QPushButton("关闭", self)
        self.close_button.setAccessibleName("关闭歌曲信息")
        self.close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 14, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addLayout(self.form)
        layout.addLayout(buttons)
        self.set_track(track)
        self.set_theme(theme)

    def set_track(self, track: Track) -> None:
        identity = present_track_identity(track)
        self.title_label.setText(identity.title)
        self.detail_label.setText(identity.artist)
        values = (
            ("专辑", identity.album),
            ("时长", format_duration(track.duration_ms)),
            ("来源", track.source_name or track.source_type or "本地文件"),
            ("状态", identity.availability.label if identity.availability.is_visible else "可用"),
            ("路径", track.local_path or "无本地路径"),
        )
        while self.form.rowCount():
            self.form.removeRow(0)
        for label, value in values:
            value_label = QLabel(str(value or "—"), self)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.form.addRow(QLabel(label, self), value_label)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            build_dialog_stylesheet(theme)
            + f"QDialog#trackInfoDialog {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }}"
            + f"QLabel#trackInfoTitle {{ color: {c.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
            + f"QLabel#trackInfoDetail {{ color: {c.secondary_text}; font-size: {theme.fonts.body}px; }}"
            + f"QLabel {{ color: {c.secondary_text}; }}"
        )
        self.close_button.setStyleSheet(
            f"QPushButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }}"
            f"QPushButton:hover {{ background: {c.hover_background}; border-color: {c.border_strong}; }}"
        )


class PlaylistSelectionDialog(QDialog):
    """Modal picker for adding one track to an existing custom playlist."""

    def __init__(self, theme: Theme, playlists: Iterable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("playlistSelectionDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowTitle("添加到歌单")

        self.title_label = QLabel("添加到歌单", self)
        self.title_label.setObjectName("trackInfoTitle")
        self.list_widget = QListWidget(self)
        self.list_widget.setAccessibleName("可用歌单")
        for playlist in playlists:
            playlist_id = str(getattr(playlist, "id", "") or "")
            if not playlist_id or playlist_id == "liked":
                continue
            item = QListWidgetItem(str(getattr(playlist, "name", "未命名歌单")), self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, playlist_id)
        self.empty_label = QLabel("还没有自定义歌单，请先创建一个歌单。", self)
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(self.list_widget.count() == 0)
        self.list_widget.setVisible(not self.empty_label.isVisible())
        self.cancel_button = QPushButton("取消", self)
        self.confirm_button = QPushButton("添加", self)
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        self.confirm_button.setEnabled(self.list_widget.count() > 0)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 12, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.empty_label)
        layout.addLayout(buttons)
        self.set_theme(theme)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    @property
    def selected_playlist_id(self) -> str:
        item = self.list_widget.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            build_dialog_stylesheet(theme)
            + f"QDialog#playlistSelectionDialog {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }}"
            + f"QLabel#trackInfoTitle {{ color: {c.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
            + f"QLabel {{ color: {c.secondary_text}; }}"
            + f"QListWidget {{ min-height: 170px; background: {c.input_background}; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; color: {c.primary_text}; }}"
            + f"QListWidget::item {{ padding: 8px; border-radius: {theme.metrics.radius_sm}px; }}"
            + f"QListWidget::item:selected {{ background: {c.selected_background}; color: {c.primary_text}; }}"
        )
        for button, primary in ((self.cancel_button, False), (self.confirm_button, True)):
            if primary:
                button.setStyleSheet(
                    f"QPushButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 0; border-radius: {theme.metrics.radius_sm}px; background: {c.accent}; color: {c.content_background}; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {c.accent_hover}; }}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }}"
                    f"QPushButton:hover {{ background: {c.hover_background}; }}"
                )
