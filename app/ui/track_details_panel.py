from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models.media_item import MediaItem


class TrackDetailsPanel(QFrame):
    """Read-only details panel shared by local and online tracks."""

    def __init__(self, value: MediaItem | dict, stats: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.item = MediaItem.from_mapping(value)
        self.stats = dict(stats or {})
        self.setObjectName("trackDetailsPanel")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        title = QLabel(self.item.title)
        title.setObjectName("trackDetailsTitle")
        title.setWordWrap(True)
        subtitle = QLabel(f"{self.item.artist} · {self.item.album}")
        subtitle.setObjectName("trackDetailsSubtitle")
        subtitle.setWordWrap(True)
        badge = QLabel("在线" if self.item.media_type == "online" else "本地")
        badge.setObjectName("trackDetailsBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedWidth(54)
        heading = QHBoxLayout()
        heading.addLayout(self._column(title, subtitle), 1)
        heading.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(9)
        rows = self._online_rows() if self.item.media_type == "online" else self._local_rows()
        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setObjectName("trackDetailsName")
            value_label = QLabel(str(value or "—"))
            value_label.setObjectName("trackDetailsValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(name_label, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()
        self.setStyleSheet(
            "QFrame#trackDetailsPanel { background: #151922; border: 1px solid #2a303b; border-radius: 16px; }"
            "QLabel#trackDetailsTitle { color: #f3f4f6; font-size: 22px; font-weight: 800; }"
            "QLabel#trackDetailsSubtitle { color: #aeb6c6; font-size: 13px; }"
            "QLabel#trackDetailsBadge { background: rgba(76,141,255,0.18); color: #91b9ff; border: 1px solid rgba(76,141,255,0.38); border-radius: 9px; padding: 4px 6px; font-weight: 700; }"
            "QLabel#trackDetailsName { color: #8a92a3; font-size: 12px; }"
            "QLabel#trackDetailsValue { color: #e4e8f0; font-size: 13px; }"
        )

    @staticmethod
    def _column(*widgets):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for widget in widgets:
            layout.addWidget(widget)
        return layout

    def _online_rows(self) -> list[tuple[str, str]]:
        return [
            ("来源", self.item.source_name),
            ("在线歌曲 ID", self.item.track_id),
            ("专辑", self.item.album),
            ("时长", self._duration(self.item.duration)),
            ("音质", self.item.quality or "来源未提供"),
            ("格式", self.item.format or "来源未提供"),
            ("在线播放", "可用" if self.item.can_play else "不可用"),
            ("下载能力", "支持" if self.item.can_download else "不支持"),
            ("播放地址", "已解析" if self.item.play_url else "播放时按需解析"),
            ("来源状态", "可用" if self.item.availability == "available" else "来源不可用"),
        ]

    def _local_rows(self) -> list[tuple[str, str]]:
        path = Path(self.item.local_file_path) if self.item.local_file_path else None
        try:
            size = path.stat().st_size if path and path.is_file() else 0
        except OSError:
            size = 0
        bitrate = self.item.extra.get("bitrate") or self.item.extra.get("bit_rate") or ""
        play_count = self._safe_int(self.stats.get("play_count"))
        listen_ms = self._safe_int(self.stats.get("total_listen_time"))
        return [
            ("文件路径", self.item.local_file_path or "文件不可用"),
            ("文件格式", self.item.format.upper() if self.item.format else "未知"),
            ("文件大小", self._size(size)),
            ("比特率", f"{bitrate} kbps" if bitrate else "未读取"),
            ("时长", self._duration(self.item.duration)),
            ("播放次数", f"{play_count} 次"),
            ("累计播放", self._duration(listen_ms // 1000)),
        ]

    @staticmethod
    def _duration(seconds: int) -> str:
        seconds = max(0, int(seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    @staticmethod
    def _size(size: int) -> str:
        if size <= 0:
            return "未知"
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return "未知"

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0


class TrackDetailsDialog(QDialog):
    def __init__(self, value: MediaItem | dict, stats: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("trackDetailsDialog")
        self.setWindowTitle("歌曲信息")
        self.resize(560, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(TrackDetailsPanel(value, stats, scroll))
        close_button = QPushButton("关闭")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addWidget(scroll, 1)
        layout.addLayout(button_row)
