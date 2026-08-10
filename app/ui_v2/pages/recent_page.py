"""Recent-play page with a mock-only time range and clear action."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QToolButton

from app.ui_v2.adapters.recent_adapter import RecentAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme


class RecentPage(TrackListPage):
    def __init__(self, adapter: RecentAdapter, theme: Theme, parent=None) -> None:
        super().__init__("最近播放", adapter, theme, parent)
        self.range_box = QComboBox(self)
        self.range_box.addItem("全部时间", None)
        self.range_box.addItem("最近 7 天", 7)
        self.range_box.addItem("最近 30 天", 30)
        self.range_box.currentIndexChanged.connect(
            lambda _index: adapter.set_range_days(self.range_box.currentData())
        )
        self.clear_button = QToolButton(self)
        self.clear_button.setText("清空记录")
        self.clear_button.clicked.connect(adapter.clear)
        self.clear_button.setVisible(not adapter.collection.read_only)
        self.header.trailing_layout.insertWidget(0, self.range_box)
        self.header.trailing_layout.insertWidget(1, self.clear_button)
        self.empty_state.set_state("empty", "播放一首歌曲后，记录会显示在这里。")
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if not hasattr(self, "range_box"):
            return
        self.range_box.setStyleSheet(
            f"QComboBox {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {theme.colors.input_background}; color: {theme.colors.primary_text}; }}"
        )
        self.clear_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
        )
