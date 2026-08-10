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
        self.summary_label = QLabel(self)
        self.warning_label = QLabel(self)
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
        self.sort_selector.currentIndexChanged.connect(self._emit_sort)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重试")
        self.retry_button.clicked.connect(self.retry_requested)
        self.sources_button = QToolButton(self)
        self.sources_button.setText("来源状态")
        self.sources_button.clicked.connect(self.sources_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
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
        self.summary_label.setStyleSheet(
            f"color: {theme.colors.secondary_text}; padding-right: {theme.metrics.spacing_xs}px; "
            f"font-size: {theme.fonts.caption}px;"
        )
        self.warning_label.setStyleSheet(f"color: {theme.colors.warning};")
        self.source_filter.set_theme(theme)
        self.sort_selector.set_theme(theme)
        for button in (self.retry_button, self.sources_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
                f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
            )

    def _emit_source_filter(self) -> None:
        self.source_filter_changed.emit(str(self.source_filter.currentData() or ""))

    def _emit_sort(self) -> None:
        self.sort_changed.emit(str(self.sort_selector.currentData() or "relevance"))
