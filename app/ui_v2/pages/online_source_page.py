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
        self.setObjectName("onlineSourceRow")
        self.setMinimumHeight(106)
        self.name_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.capability_label = QLabel(self)
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
        text.setSpacing(5)
        text.addWidget(self.name_label)
        text.addWidget(self.detail_label)
        text.addWidget(self.capability_label)
        text.addWidget(self.error_label)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.enabled_button)
        actions.addWidget(self.retry_button)
        actions.addWidget(self.remove_button)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(16)
        layout.addLayout(text, 1)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(actions, 0)
        self.set_source(source)
        self.set_theme(theme)

    def set_source(self, source: OnlineSource) -> None:
        self.source_id = source.id
        self._enabled = source.enabled
        self.name_label.setText(source.name)
        self.detail_label.setText(
            f"响应 {source.latency_ms} ms · 最近搜索 {source.result_count} 条结果"
        )
        capabilities = []
        if source.supports_playback:
            capabilities.append("播放")
        if source.supports_download:
            capabilities.append("下载")
        if source.supports_lyrics:
            capabilities.append("歌词")
        self.capability_label.setText(
            "支持 " + " · ".join(capabilities) if capabilities else "当前不提供附加能力"
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
        self.set_theme(self._theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            f"QFrame#onlineSourceRow {{ border: 1px solid {colors.border}; border-radius: {metrics.radius_md}px; "
            f"background: {colors.surface_primary}; }}"
            f"QFrame#onlineSourceRow:hover {{ border-color: {colors.border_strong}; background: {colors.surface_secondary}; }}"
        )
        self.name_label.setStyleSheet(f"font-weight: 700; color: {colors.primary_text};")
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {colors.secondary_text};"
        )
        self.capability_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {colors.text_tertiary};"
        )
        self.error_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {colors.danger};"
        )
        self.badge.set_theme(theme)
        if self._enabled:
            self.enabled_button.setStyleSheet(
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
                f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; "
                f"color: {colors.secondary_text}; background: {colors.surface_secondary}; font-weight: 400; }}"
                f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
            )
        else:
            self.enabled_button.setStyleSheet(
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
                f"border: 1px solid transparent; border-radius: {metrics.radius_sm}px; "
                f"color: {colors.content_background}; background: {colors.accent}; font-weight: 600; }}"
                f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
            )
        self.retry_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_sm}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.warning}; "
                f"background: {colors.surface_secondary}; font-weight: 400; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; }}"
        )
        self.remove_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_sm}px; "
                f"border: 1px solid transparent; border-radius: {metrics.radius_sm}px; color: {colors.secondary_text}; background: transparent; font-weight: 400; }}"
            f"QToolButton:hover {{ color: {colors.danger}; background: {colors.hover_background}; }}"
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
        self.header_surface = QFrame(self)
        self.header_surface.setObjectName("onlineSourceHeaderSurface")
        self.list_surface = QFrame(self)
        self.list_surface.setObjectName("onlineSourceListSurface")
        self.title_label = QLabel("在线来源", self.header_surface)
        self.title_label.setObjectName("onlineSourceTitle")
        self.detail_label = QLabel("来源可停用并再次启用；只有“移除”才会删除来源配置。", self.header_surface)
        self.detail_label.setObjectName("onlineSourceDetail")
        self.summary_label = QLabel(self.header_surface)
        self.summary_label.setObjectName("onlineSourceSummary")
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
        self.add_source_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_source_button.clicked.connect(self._open_import_dialog)
        self.select_all_button = QToolButton(self)
        self.select_all_button.setText("全选")
        self.select_all_button.setAccessibleName("启用全部在线来源")
        self.select_all_button.clicked.connect(adapter.select_all)
        self.clear_button = QToolButton(self)
        self.clear_button.setText("清空")
        self.clear_button.setAccessibleName("停用全部在线来源")
        self.clear_button.clicked.connect(adapter.clear_selection)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.add_source_button)
        actions.addWidget(self.select_all_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.back_button)
        header_top = QHBoxLayout()
        header_top.setContentsMargins(0, 0, 0, 0)
        header_top.setSpacing(16)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(3)
        heading.addWidget(self.title_label)
        heading.addWidget(self.detail_label)
        header_top.addLayout(heading, 1)
        header_top.addLayout(actions)
        header_bottom = QHBoxLayout()
        header_bottom.setContentsMargins(0, 0, 0, 0)
        header_bottom.addWidget(self.summary_label)
        header_bottom.addStretch(1)
        header_layout = QVBoxLayout(self.header_surface)
        header_layout.setContentsMargins(20, 18, 20, 16)
        header_layout.setSpacing(14)
        header_layout.addLayout(header_top)
        header_layout.addLayout(header_bottom)
        self.scroll_area = QScrollArea(self.list_surface)
        self.scroll_area.setObjectName("onlineSourceScrollArea")
        self.scroll_area.setAccessibleName("已注册在线来源列表")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget(self.scroll_area)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(theme.metrics.spacing_sm)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        list_layout = QVBoxLayout(self.list_surface)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(0)
        list_layout.addWidget(self.scroll_area)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(metrics.page_margin, metrics.spacing_lg, metrics.page_margin, metrics.page_margin)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.header_surface)
        layout.addWidget(self.list_surface, 1)
        adapter.sources_changed.connect(self.set_sources)
        self.set_sources(adapter.sources())
        self.set_theme(theme)

    def set_sources(self, sources) -> None:
        is_searching = any(source.status == "searching" for source in sources)
        enabled_count = sum(source.enabled for source in sources)
        disabled_count = len(sources) - enabled_count
        self.summary_label.setText(
            f"{len(sources)} 个来源 · {enabled_count} 个已启用"
            + (f" · {disabled_count} 个已停用" if disabled_count else "")
        )
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
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            build_stylesheet(theme)
            + f"""
            QFrame#onlineSourceHeaderSurface {{
                background: {colors.surface_primary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_lg}px;
            }}
            QFrame#onlineSourceListSurface {{
                background: {colors.surface_primary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_lg}px;
            }}
            QLabel#onlineSourceTitle {{
                font-size: {theme.fonts.page_title}px;
                font-weight: 700;
                color: {colors.primary_text};
            }}
            QLabel#onlineSourceDetail {{ color: {colors.secondary_text}; }}
            QLabel#onlineSourceSummary {{
                padding: 3px 8px;
                border-radius: {metrics.radius_sm}px;
                background: {colors.surface_secondary};
                color: {colors.secondary_text};
                font-size: {theme.fonts.caption}px;
            }}
            """
        )
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
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
                f"border: 1px solid {'transparent' if primary else colors.border}; border-radius: {metrics.radius_sm}px; "
                f"background: {colors.accent if primary else colors.surface_secondary}; "
                f"color: {colors.content_background if primary else colors.secondary_text}; "
                f"font-weight: {'600' if primary else '500'}; }}"
                f"QToolButton:hover {{ color: {colors.content_background if primary else colors.primary_text}; "
                f"background: {colors.accent_hover if primary else colors.hover_background}; border-color: {'transparent' if primary else colors.border_strong}; }}"
                f"QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_pressed}; }}"
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
        self.summary_label.setVisible(not compact)
        self.add_source_button.setText("添加" if compact else "添加来源")
        self.select_all_button.setText("全选" if not compact else "全")
        self.clear_button.setText("清空" if not compact else "清")
