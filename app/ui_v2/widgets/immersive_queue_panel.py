"""Read-only queue overlay for the immersive player shell."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.track_display import display_track_text


class ImmersiveQueuePanel(QFrame):
    """Compact, non-mutating queue projection backed by PlaybackAdapter."""

    closed = Signal()

    def __init__(self, playback: PlaybackAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playback = playback
        self._theme = theme
        self.setObjectName("immersiveQueuePanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(390)
        self.close_button = QToolButton(self)
        self.close_button.setObjectName("immersiveQueueClose")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setIconSize(QSize(17, 17))
        self.close_button.clicked.connect(self.closed)
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("immersiveQueueList")
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.empty_label = QLabel("播放队列为空", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("播放队列", self)
        heading.addWidget(self.title_label)
        heading.addStretch(1)
        heading.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 12, 16)
        layout.setSpacing(12)
        layout.addLayout(heading)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.empty_label, 1)
        playback.track_changed.connect(lambda _track: self.refresh())
        playback.queue_changed.connect(lambda _queue: self.refresh())
        self.refresh()
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#immersiveQueuePanel {{ background: {colors.surface_elevated}; border: 1px solid {colors.divider}; border-radius: 12px; }}"
            f"QLabel {{ color: {colors.text_primary}; }}"
            f"QListWidget {{ background: transparent; border: 0; outline: 0; color: {colors.text_secondary}; }}"
            f"QListWidget::item {{ padding: 9px 8px; border-radius: 7px; }}"
            f"QListWidget::item:hover {{ background: {colors.surface_hover}; }}"
            f"QToolButton {{ border: 0; border-radius: 16px; background: transparent; }}"
            f"QToolButton:hover {{ background: {colors.surface_hover}; }}"
        )
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {colors.text_primary};")
        self.empty_label.setStyleSheet(f"font-size: {theme.fonts.body}px; color: {colors.text_secondary};")
        self.close_button.setIcon(icon("window_close", theme))
        self.close_button.setToolTip("关闭队列")

    def refresh(self) -> None:
        tracks = self.playback.queue_tracks
        current_id = self.playback.state.current_track.id if self.playback.state.current_track else ""
        self.list_widget.clear()
        self.empty_label.setVisible(not tracks)
        self.list_widget.setVisible(bool(tracks))
        for track in tracks:
            item = QListWidgetItem(self._label_for(track))
            item.setData(Qt.ItemDataRole.UserRole, track.id)
            if track.id == current_id:
                item.setBackground(QColor(self._theme.colors.playing_background))
                item.setForeground(QColor(self._theme.colors.text_primary))
            self.list_widget.addItem(item)

    @staticmethod
    def _label_for(track: Track) -> str:
        title, artist, _album = display_track_text(track)
        return f"{title}  ·  {artist}" if artist else title
