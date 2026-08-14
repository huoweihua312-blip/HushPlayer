"""Menu-based enabled-source selector that stays compact on narrow windows."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class SourceSelector(QToolButton):
    sources_changed = Signal()

    def __init__(self, adapter: OnlineAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self._compact = False
        self.setObjectName("onlineSourceSelector")
        self.setAccessibleName("在线来源筛选")
        self.setAccessibleDescription("选择在线搜索时使用的来源；点击打开来源筛选菜单")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        # QToolButton defaults to icon-only on some Windows styles.  That made
        # this control appear as an unexplained square even though it already
        # had a useful label. Keep the label visible beside the cloud icon.
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        adapter.source_state_changed.connect(self._rebuild_menu)
        adapter.state_changed.connect(lambda _state: self._rebuild_menu(adapter.sources()))
        self._rebuild_menu(adapter.sources())
        self.set_theme(theme)

    def set_compact(self, compact: bool) -> None:
        self._compact = bool(compact)
        self.setMinimumWidth(80 if self._compact else 96)
        self._refresh_text()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setIcon(icon("online", theme))
        self.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
        self.setMinimumWidth(80 if self._compact else 96)
        self.setStyleSheet(
            f"QToolButton#onlineSourceSelector {{ min-height: {theme.metrics.control_height}px; "
            f"padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_md}px; "
            f"background: {theme.colors.surface_secondary}; color: {theme.colors.primary_text}; font-weight: 500; }}"
            f"QToolButton#onlineSourceSelector:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; "
            f"border-color: {theme.colors.border_strong}; }}"
            f"QToolButton#onlineSourceSelector:pressed {{ background: {theme.colors.surface_elevated}; }}"
            f"QToolButton#onlineSourceSelector:focus {{ border-color: {theme.colors.focus_ring}; }}"
            f"QToolButton#onlineSourceSelector::menu-indicator {{ subcontrol-origin: padding; "
            f"subcontrol-position: right center; width: 12px; height: 12px; "
            f"right: {theme.metrics.spacing_xs}px; }}"
        )

    def _rebuild_menu(self, sources) -> None:
        self._menu.clear()
        selectable = self.adapter.state.phase != "searching"
        all_action = self._menu.addAction("全选来源")
        all_action.setEnabled(selectable)
        all_action.triggered.connect(
            lambda: self.adapter.set_enabled_sources(source.id for source in self.adapter.sources())
        )
        clear_action = self._menu.addAction("清空来源")
        clear_action.setEnabled(selectable)
        clear_action.triggered.connect(lambda: self.adapter.set_enabled_sources(()))
        self._menu.addSeparator()
        for source in sources:
            status = {
                "ready": "可用",
                "searching": "搜索中",
                "success": "已完成",
                "warning": "部分可用",
                "failed": "失败",
                "disabled": "已禁用",
            }.get(source.status, "未知")
            action = self._menu.addAction(f"{source.name}  {status}  {source.result_count} 条")
            action.setCheckable(True)
            action.setChecked(source.enabled)
            action.setEnabled(selectable)
            action.setToolTip(
                f"{source.name}\n状态: {status}\n结果: {source.result_count} 条\n延迟: {source.latency_ms} ms"
            )
            action.triggered.connect(
                lambda checked, source_id=source.id: self.adapter.set_source_enabled(source_id, checked)
            )
        self._refresh_text()
        self.sources_changed.emit()

    def _refresh_text(self) -> None:
        count = sum(source.enabled for source in self.adapter.sources())
        # The identity row already shows the enabled-source count. Keep this
        # action label short so the control reads as one coherent secondary
        # button instead of repeating the same status twice.
        self.setText("来源")
        self.setToolTip(f"已启用 {count} 个在线来源；点击调整本次搜索范围")
