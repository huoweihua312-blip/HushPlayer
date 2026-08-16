"""Non-blocking visual state for initial, loading, empty, and failed online search."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.online_search_state import OnlineSearchState
from app.ui_v2.theme.tokens import Theme


class SearchStateView(QWidget):
    cancel_requested = Signal()
    retry_requested = Signal()
    sources_requested = Signal()
    history_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setMinimumHeight(260)
        self.title_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.progress = QProgressBar(self)
        self.cancel_button = QToolButton(self)
        self.cancel_button.setText("取消搜索")
        self.cancel_button.setAccessibleName("取消在线搜索")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重试")
        self.retry_button.setAccessibleName("重试在线搜索")
        self.retry_button.clicked.connect(self.retry_requested)
        self.sources_button = QToolButton(self)
        self.sources_button.setText("管理来源")
        self.sources_button.setAccessibleName("查看在线来源")
        self.sources_button.clicked.connect(self.sources_requested)
        self.history_button = QToolButton(self)
        self.history_button.setText("返回历史搜索")
        self.history_button.setAccessibleName("返回搜索历史")
        self.history_button.clicked.connect(self.history_requested)
        self.progress.setAccessibleName("在线搜索进度")
        for label in (self.title_label, self.detail_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.actions = QWidget(self)
        self.actions.setObjectName("onlineSearchStateActions")
        action_layout = QHBoxLayout(self.actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addStretch(1)
        action_layout.addWidget(self.cancel_button)
        action_layout.addWidget(self.retry_button)
        action_layout.addWidget(self.sources_button)
        action_layout.addWidget(self.history_button)
        action_layout.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.actions)
        layout.addStretch(1)
        self.set_state(OnlineSearchState("idle", ""))
        self.set_theme(theme)

    def set_state(self, state: OnlineSearchState) -> None:
        values = {
            "idle": ("开始在线搜索", "输入关键词后从已启用来源搜索。"),
            "searching": ("正在搜索", state.message or "正在等待在线来源响应。"),
            "empty": ("没有找到结果", state.message or "尝试调整关键词或切换来源。"),
            "failed": ("搜索暂不可用", state.message or "请重试或检查来源状态。"),
        }
        title, detail = values.get(state.phase, values["idle"])
        self.title_label.setText(title)
        self.detail_label.setText(detail)
        self.progress.setValue(state.progress)
        self.progress.setVisible(state.phase == "searching")
        self.cancel_button.setVisible(state.phase == "searching")
        retry = state.phase == "failed"
        self.retry_button.setVisible(retry)
        self.sources_button.setVisible(state.phase in {"empty", "failed"})
        self.history_button.setVisible(state.phase in {"empty", "failed"})

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 700; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"color: {theme.colors.secondary_text}; max-width: 560px;"
        )
        self.progress.setStyleSheet(
            f"QProgressBar {{ border: 0; height: 5px; border-radius: 2px; background: {theme.colors.border}; }}"
            f"QProgressBar::chunk {{ border-radius: 2px; background: {theme.colors.accent}; }}"
        )
        for button in (self.cancel_button, self.sources_button, self.history_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
                f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; "
                f"background: {theme.colors.surface_primary}; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; "
                f"border-color: {theme.colors.border_strong}; }}"
            )
        self.retry_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 1px solid transparent; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {theme.colors.accent}; color: {theme.colors.content_background}; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {theme.colors.accent_hover}; }}"
        )
