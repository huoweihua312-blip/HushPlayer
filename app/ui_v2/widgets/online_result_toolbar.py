"""Concise result summary and source-management entry for online search."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import ToolbarComboBox


class OnlineResultToolbar(QWidget):
    retry_requested = Signal()
    sources_requested = Signal()
    source_filter_changed = Signal(str)
    sort_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("onlineResultToolbar")
        self.setMinimumHeight(56)
        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("onlineResultCount")
        self.warning_label = QLabel(self)
        self.warning_label.setObjectName("onlineResultWarning")
        self.source_filter = ToolbarComboBox(theme, self)
        self.source_filter.setAccessibleName("来源筛选")
        self.source_filter.setAccessibleDescription("筛选在线搜索结果的来源")
        self.source_filter.view().setMinimumWidth(210)
        self.source_filter.currentIndexChanged.connect(self._emit_source_filter)
        self.sort_selector = ToolbarComboBox(theme, self)
        self.sort_selector.setAccessibleName("排序方式")
        self.sort_selector.setAccessibleDescription("选择在线搜索结果的排序方式")
        self.sort_selector.view().setMinimumWidth(140)
        self.sort_selector.addItem("相关度", "relevance")
        self.sort_selector.addItem("歌曲名称", "title")
        self.sort_selector.addItem("时长", "duration")
        self.sort_selector.setToolTip("排序：默认按相关度，可切换歌曲名称或时长")
        self.sort_selector.currentIndexChanged.connect(self._emit_sort)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重试")
        self.retry_button.setAccessibleName("重试在线搜索")
        self.retry_button.setToolTip("重新查询当前关键词")
        self.retry_button.clicked.connect(self.retry_requested)
        self.sources_button = QToolButton(self)
        self.sources_button.setText("管理来源")
        self.sources_button.setAccessibleName("查看在线来源状态")
        self.sources_button.setToolTip("管理在线来源的启用状态")
        self.sources_button.clicked.connect(self.sources_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.source_filter)
        layout.addWidget(self.sort_selector)
        layout.addStretch(1)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.sources_button)
        self.set_compact(False)
        self.set_summary(0, "")
        self.set_theme(theme)

    def set_sources(self, sources) -> None:
        selected = self.source_filter.currentData()
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("全部来源", "")
        for source in sources:
            self.source_filter.addItem(source.name, source.id)
            index = self.source_filter.count() - 1
            self.source_filter.setItemData(
                index,
                f"{source.name}: {source.result_count} 条结果，{source.latency_ms} ms",
                Qt.ItemDataRole.ToolTipRole,
            )
        selected_index = self.source_filter.findData(selected)
        self.source_filter.setCurrentIndex(max(0, selected_index))
        self.source_filter.blockSignals(False)

    def set_compact(self, compact: bool) -> None:
        self.source_filter.setFixedWidth(128 if compact else 146)
        self.sort_selector.setFixedWidth(104 if compact else 112)

    def set_summary(self, count: int, warning: str) -> None:
        self.summary_label.setText(f"{count} 条结果")
        self.warning_label.setText(warning)
        self.warning_label.setVisible(bool(warning))
        self.retry_button.setVisible(bool(warning))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            f"QWidget#onlineResultToolbar {{ background: {colors.surface_secondary}; border: 1px solid {colors.border}; "
            f"border-radius: {metrics.radius_md}px; }}"
        )
        self.summary_label.setStyleSheet(
            f"padding: 3px 8px; border-radius: {metrics.radius_sm}px; background: {colors.elevated_background}; "
            f"color: {colors.primary_text}; font-size: {theme.fonts.caption}px; font-weight: 600;"
        )
        self.warning_label.setStyleSheet(
            f"color: {colors.warning}; font-size: {theme.fonts.caption}px;"
        )
        self.source_filter.set_theme(theme)
        self.sort_selector.set_theme(theme)
        self.retry_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.warning}; "
            f"background: {colors.surface_primary}; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
        )
        self.sources_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.secondary_text}; "
            f"background: {colors.surface_primary}; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
            f"QToolButton:focus {{ border-color: {colors.focus_ring}; }}"
        )

    def _emit_source_filter(self) -> None:
        self.source_filter_changed.emit(str(self.source_filter.currentData() or ""))

    def _emit_sort(self) -> None:
        self.sort_changed.emit(str(self.sort_selector.currentData() or "relevance"))
