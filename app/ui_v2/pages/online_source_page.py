"""Compact source-management page for the online discovery surface."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.online_source_adapter import OnlineSourceAdapter
from app.ui_v2.models.online_source import OnlineSource
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.source_import_dialog import SourceImportDialog, SourceRemoveConfirmDialog
from app.ui_v2.widgets.source_status_badge import SourceStatusBadge


class SourceRow(QFrame):
    toggle_requested = Signal(str, bool)
    retry_requested = Signal()
    remove_requested = Signal(str)

    def __init__(self, source: OnlineSource, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.source_id = source.id
        self.name_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.error_label = QLabel(self)
        self.badge = SourceStatusBadge(theme, self)
        self.enabled_button = QToolButton(self)
        self.enabled_button.setObjectName("sourceToggleButton")
        self.enabled_button.clicked.connect(self._toggle)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重试")
        self.retry_button.setAccessibleName("重试在线来源")
        self.retry_button.clicked.connect(self.retry_requested)
        self.remove_button = QToolButton(self)
        self.remove_button.setText("移除")
        self.remove_button.setAccessibleName("移除在线来源")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.source_id))
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        text.addWidget(self.name_label)
        text.addWidget(self.detail_label)
        text.addWidget(self.error_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.addLayout(text, 1)
        layout.addWidget(self.badge)
        layout.addWidget(self.enabled_button)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.remove_button)
        self.set_source(source)
        self.set_theme(theme)

    def set_source(self, source: OnlineSource) -> None:
        self.source_id = source.id
        self._enabled = source.enabled
        self.name_label.setText(source.name)
        self.detail_label.setText(
            f"{source.latency_ms} ms  {source.result_count} 条结果  "
            f"播放 {'支持' if source.supports_playback else '不支持'}  下载 {'支持' if source.supports_download else '不支持'}  "
            f"歌词 {'支持' if source.supports_lyrics else '不支持'}"
        )
        self.error_label.setText(source.last_error)
        self.error_label.setVisible(bool(source.last_error))
        self.badge.set_source(source)
        self.enabled_button.setText("停用" if source.enabled else "启用")
        self.enabled_button.setToolTip(
            f"停用 {source.name}；来源仍会保留，可再次启用"
            if source.enabled
            else f"启用 {source.name}"
        )
        self.enabled_button.setAccessibleName(
            f"停用 {source.name}（不会删除来源）"
            if source.enabled
            else f"启用 {source.name}"
        )
        self.enabled_button.setEnabled(source.status != "searching")
        self.retry_button.setVisible(source.status in {"failed", "warning"})

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"QFrame {{ border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {theme.colors.elevated_background}; }}"
        )
        self.name_label.setStyleSheet(f"font-weight: 600; color: {theme.colors.primary_text};")
        self.detail_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};")
        self.error_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {theme.colors.danger};")
        self.badge.set_theme(theme)
        for button in (self.enabled_button, self.retry_button, self.remove_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
                f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
            )

    def _toggle(self) -> None:
        self.toggle_requested.emit(self.source_id, not self._enabled)


class OnlineSourcePage(QWidget):
    back_requested = Signal()
    add_source_requested = Signal()

    def __init__(self, adapter: OnlineSourceAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self._rows: dict[str, SourceRow] = {}
        self.setObjectName("onlineSourcePage")
        self.setAccessibleName("在线来源管理")
        self.title_label = QLabel("在线来源", self)
        self.detail_label = QLabel("查看已注册在线来源的能力与当前状态。", self)
        self.back_button = QToolButton(self)
        self.back_button.setText("返回搜索")
        self.back_button.setAccessibleName("返回在线搜索")
        self.back_button.clicked.connect(self.back_requested)
        self.add_source_button = QToolButton(self)
        self.add_source_button.setText("添加来源")
        self.add_source_button.setAccessibleName("添加在线来源")
        self.add_source_button.setToolTip("通过 .js 或 .json URL 添加在线来源")
        self.add_source_button.setIcon(icon("add", theme))
        self.add_source_button.setIconSize(QSize(16, 16))
        self.add_source_button.clicked.connect(self._open_import_dialog)
        self.select_all_button = QToolButton(self)
        self.select_all_button.setText("全选")
        self.select_all_button.setAccessibleName("启用全部在线来源")
        self.select_all_button.clicked.connect(adapter.select_all)
        self.clear_button = QToolButton(self)
        self.clear_button.setText("清空")
        self.clear_button.setAccessibleName("停用全部在线来源")
        self.clear_button.clicked.connect(adapter.clear_selection)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.add_source_button)
        header.addWidget(self.select_all_button)
        header.addWidget(self.clear_button)
        header.addWidget(self.back_button)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("onlineSourceScrollArea")
        self.scroll_area.setAccessibleName("已注册在线来源列表")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget(self.scroll_area)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(theme.metrics.spacing_sm)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(metrics.page_margin, metrics.spacing_lg, metrics.page_margin, metrics.page_margin)
        layout.setSpacing(metrics.spacing_md)
        layout.addLayout(header)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.scroll_area, 1)
        adapter.sources_changed.connect(self.set_sources)
        self.set_sources(adapter.sources())
        self.set_theme(theme)

    def set_sources(self, sources) -> None:
        is_searching = any(source.status == "searching" for source in sources)
        self.select_all_button.setEnabled(not is_searching)
        self.clear_button.setEnabled(not is_searching)
        source_ids = {source.id for source in sources}
        for source_id, row in tuple(self._rows.items()):
            if source_id not in source_ids:
                self.content_layout.removeWidget(row)
                row.deleteLater()
                del self._rows[source_id]
        for source in sources:
            row = self._rows.get(source.id)
            if row is None:
                row = SourceRow(source, self._theme, self.content)
                row.toggle_requested.connect(self.adapter.set_enabled)
                row.retry_requested.connect(self.adapter.retry)
                row.remove_requested.connect(self._confirm_remove)
                self._rows[source.id] = row
                self.content_layout.insertWidget(max(0, self.content_layout.count() - 1), row)
            else:
                row.set_source(source)
            row.remove_button.setVisible(self.adapter.importer is not None)
        self.add_source_button.setEnabled(self.adapter.importer is not None)
        self.add_source_button.setToolTip(
            "通过 .js 或 .json URL 添加在线来源"
            if self.adapter.importer is not None
            else "正式运行模式可管理在线来源"
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(f"color: {theme.colors.secondary_text};")
        self.scroll_area.setStyleSheet(
            f"QScrollArea#onlineSourceScrollArea {{ border: 0; background: transparent; }}"
            f"QScrollArea#onlineSourceScrollArea QScrollBar:vertical {{ width: 10px; margin: 4px 2px; background: transparent; }}"
            f"QScrollArea#onlineSourceScrollArea QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 5px; background: {theme.colors.border_strong}; }}"
            f"QScrollArea#onlineSourceScrollArea QScrollBar::handle:vertical:hover {{ background: {theme.colors.text_tertiary}; }}"
            f"QScrollArea#onlineSourceScrollArea QScrollBar::add-line:vertical, QScrollArea#onlineSourceScrollArea QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        for button in (
            self.add_source_button,
            self.back_button,
            self.select_all_button,
            self.clear_button,
        ):
            primary = button is self.add_source_button
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
                f"border: 1px solid {'transparent' if primary else theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; "
                f"background: {theme.colors.accent if primary else theme.colors.surface_secondary}; "
                f"color: {theme.colors.content_background if primary else theme.colors.secondary_text}; "
                f"font-weight: {'600' if primary else '400'}; }}"
                f"QToolButton:hover {{ color: {theme.colors.content_background if primary else theme.colors.primary_text}; "
                f"background: {theme.colors.accent_hover if primary else theme.colors.hover_background}; }}"
                f"QToolButton:disabled {{ color: {theme.colors.disabled_text}; background: {theme.colors.surface_pressed}; }}"
            )
        for row in self._rows.values():
            row.set_theme(theme)

    def _open_import_dialog(self) -> None:
        importer = self.adapter.importer
        if importer is None:
            return
        dialog = SourceImportDialog(importer, self._theme, self)
        dialog.exec()
        dialog.deleteLater()

    def _confirm_remove(self, source_id: str) -> None:
        source = next(
            (item for item in self.adapter.sources() if item.id == str(source_id or "")),
            None,
        )
        if source is None:
            return
        dialog = SourceRemoveConfirmDialog(source.name, self._theme, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.adapter.remove(source.id)
        dialog.deleteLater()

    def set_responsive_reference_width(self, width: int) -> None:
        compact = width < 950
        self.detail_label.setVisible(not compact)
        self.add_source_button.setText("添加" if compact else "添加来源")
        self.select_all_button.setText("全选" if not compact else "全")
        self.clear_button.setText("清空" if not compact else "清")
