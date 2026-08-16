"""Small semantic source-health label shared by search and source management."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from app.ui_v2.models.online_source import OnlineSource
from app.ui_v2.theme.tokens import Theme


class SourceStatusBadge(QLabel):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._status = "ready"
        self.set_source_status("ready")

    def set_source_status(self, status: str) -> None:
        self._status = status
        labels = {
            "ready": "可用",
            "searching": "搜索中",
            "success": "已完成",
            "warning": "部分可用",
            "failed": "失败",
            "disabled": "已禁用",
        }
        self.setText(labels.get(status, "未知"))
        self.setToolTip(self.text())
        self._refresh()

    def set_source(self, source: OnlineSource) -> None:
        self.set_source_status(source.status)
        self.setToolTip(source.last_error or self.text())

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh()

    def _refresh(self) -> None:
        colors = self._theme.colors
        color = {
            "success": colors.success,
            "ready": colors.secondary_text,
            "searching": colors.accent,
            "warning": colors.warning,
            "failed": colors.danger,
            "disabled": colors.disabled_text,
        }.get(self._status, colors.secondary_text)
        self.setStyleSheet(
            f"padding: 3px 8px; border: 1px solid {self._theme.colors.border}; "
            f"border-radius: {self._theme.metrics.radius_sm}px; "
            f"background: {self._theme.colors.surface_secondary}; color: {color}; "
            f"font-size: {self._theme.fonts.caption}px; font-weight: 600;"
        )
