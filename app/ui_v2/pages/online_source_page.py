"""Compact source-management page for the online discovery surface."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.online_source_adapter import OnlineSourceAdapter
from app.ui_v2.models.online_source import OnlineSource
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.source_import_dialog import SourceImportDialog, SourceRemoveConfirmDialog
from app.ui_v2.widgets.source_status_badge import SourceStatusBadge
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.settings_control_factory import SettingsToggle
from app.ui_v2.widgets.online_presentation import style_action, style_caption


class SourceRow(QFrame):
    toggle_requested = Signal(str, bool)
    retry_requested = Signal()
    remove_requested = Signal(str)

    def __init__(self, source: OnlineSource, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.source_id = source.id
        self.setObjectName("onlineSourceRow")
        self.setMinimumHeight(115)
        self.name_label = ElidedLabel(self)
        self.detail_label = ElidedLabel(self)
        self.capability_label = ElidedLabel(self)
        self.error_label = ElidedLabel(self)
        self.badge = SourceStatusBadge(theme, self)
        self.enabled_button = SettingsToggle(source.enabled, theme, self)
        self.source_icon = QLabel(self)
        self.source_icon.setFixedSize(38, 38)
        self.source_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.enabled_button.setObjectName("sourceToggleButton")
        self.enabled_button.clicked.connect(self._toggle)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重试")
        self.retry_button.setAccessibleName("重试在线来源")
        self.retry_button.clicked.connect(self.retry_requested)
        self.remove_button = QToolButton(self)
        self.remove_button.setText("…")
        self.remove_button.setToolTip("更多来源操作")
        self.remove_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.remove_menu = QMenu(self.remove_button)
        self.remove_button.setMenu(self.remove_menu)
        self.remove_action = self.remove_menu.addAction("移除来源")
        self.remove_button.setAccessibleName("移除在线来源")
        self.remove_action.triggered.connect(lambda: self.remove_requested.emit(self.source_id))
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(5)
        text.addWidget(self.name_label)
        text.addWidget(self.capability_label)
        text.addWidget(self.detail_label)
        text.addWidget(self.error_label)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        health = QVBoxLayout()
        health.setSpacing(0)
        health.addWidget(self.badge)
        health.addWidget(self.retry_button)
        actions.addLayout(health)
        actions.addSpacing(28)
        actions.addWidget(self.enabled_button)
        actions.addSpacing(14)
        actions.addWidget(self.remove_button)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 18)
        layout.setSpacing(16)
        layout.addWidget(self.source_icon)
        layout.addSpacing(8)
        layout.addLayout(text, 1)
        layout.addLayout(actions, 0)
        self.set_source(source)
        self.set_theme(theme)

    def set_source(self, source: OnlineSource) -> None:
        self.source_id = source.id
        self._enabled = source.enabled
        self.name_label.set_full_text(source.name)
        self.detail_label.set_full_text(
            f"响应 {source.latency_ms} ms · 最近搜索 {source.result_count} 条结果"
            + (f" · {source.test_summary}" if source.test_summary else "")
        )
        capabilities = []
        if source.supports_playback:
            capabilities.append("播放")
        if source.supports_download:
            capabilities.append("下载")
        if source.supports_lyrics:
            capabilities.append("歌词")
        self.capability_label.set_full_text(
            "支持 " + " · ".join(capabilities) if capabilities else "当前不提供附加能力"
        )
        self.error_label.set_full_text(source.last_error)
        self.error_label.setVisible(bool(source.last_error))
        self.badge.set_source(source)
        self.enabled_button.setChecked(source.enabled)
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
        theme = get_theme(theme.mode, profile="b2")
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            f"QFrame#onlineSourceRow {{ border: 0; border-bottom: 1px solid {colors.divider}; border-radius: 0; "
            f"background: transparent; }}"
            f"QFrame#onlineSourceRow:hover {{ background: {colors.hover_background}; }}"
        )
        self.name_label.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {colors.primary_text if self._enabled else colors.secondary_text};")
        self.source_icon.setPixmap(icon("online", theme).pixmap(QSize(22, 22)))
        self.source_icon.setStyleSheet(f"background: {colors.surface_secondary}; border: 0; border-radius: 5px;")
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
        self.enabled_button.setStyleSheet("")
        self.enabled_button.set_theme(theme)
        style_caption(self.detail_label, theme, subtle=True)
        style_caption(self.capability_label, theme)
        style_action(self.retry_button, theme)
        style_action(self.remove_button, theme)
        self.remove_button.setStyleSheet(self.remove_button.styleSheet() + "QToolButton::menu-indicator { image: none; }")
        self.remove_menu.setStyleSheet(build_stylesheet(theme))

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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self.verify_button = QToolButton(self)
        self.verify_button.setText("快速验证")
        self.verify_button.setAccessibleName("快速验证在线来源")
        self.verify_button.setToolTip("使用内置关键词逐个验证来源搜索能力")
        self.verify_button.clicked.connect(self.adapter.verify_sources)
        self.select_all_button = QToolButton(self)
        self.select_all_button.setText("启用全部")
        self.select_all_button.setAccessibleName("启用全部在线来源")
        self.select_all_button.clicked.connect(adapter.select_all)
        self.clear_button = QToolButton(self)
        self.clear_button.setText("停用全部")
        self.clear_button.setAccessibleName("停用全部在线来源")
        self.clear_button.clicked.connect(adapter.clear_selection)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.summary_label)
        actions.addStretch(1)
        actions.addWidget(self.select_all_button)
        actions.addWidget(self.clear_button)
        header_top = QHBoxLayout()
        header_top.setContentsMargins(0, 0, 0, 0)
        header_top.setSpacing(16)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(9)
        self.eyebrow = QLabel("在线音乐", self)
        heading.addWidget(self.eyebrow)
        heading.addWidget(self.title_label)
        heading.addWidget(self.detail_label)
        header_top.addLayout(heading, 1)
        header_top.addWidget(self.back_button)
        header_top.addWidget(self.verify_button)
        header_top.addWidget(self.add_source_button)

        header_bottom = QHBoxLayout()
        header_bottom.setContentsMargins(0, 0, 0, 0)
        self.hint_label = QLabel(
            "快速验证会使用内置关键词“夜曲”逐个搜索；停用来源不会移除已收藏的歌曲。",
            self,
        )
        self.hint_label.setWordWrap(True)
        header_bottom.addWidget(self.hint_label, 1)

        header_layout = QVBoxLayout(self.header_surface)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(24)
        header_layout.addLayout(header_top)
        header_layout.addLayout(actions)
        header_layout.addLayout(header_bottom)
        self.scroll_area = QScrollArea(self.list_surface)
        self.scroll_area.setObjectName("onlineSourceScrollArea")
        self.scroll_area.setAccessibleName("已注册在线来源列表")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("onlineSourceContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.empty_label = QLabel("还没有在线来源\n使用“添加来源”导入可用的来源地址。", self.content)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(180)
        self.content_layout.addWidget(self.empty_label)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        list_layout = QVBoxLayout(self.list_surface)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        list_layout.addWidget(self.scroll_area)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(42, 32, 42, 30)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.header_surface)
        layout.addWidget(self.list_surface, 1)
        adapter.sources_changed.connect(self.set_sources)
        adapter.verify_status_changed.connect(self._show_verify_status)
        adapter.verify_running_changed.connect(self.verify_button.setDisabled)
        self.set_sources(adapter.sources())
        self.set_theme(theme)

    def _show_verify_status(self, message: str) -> None:
        self.hint_label.setText(str(message or ""))

    def set_sources(self, sources) -> None:
        self.empty_label.setVisible(not sources)
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
        theme = get_theme(theme.mode, profile="b2")
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            build_stylesheet(theme)
            + f"""
            QWidget#onlineSourcePage, QWidget#onlineSourceContent {{ background: {colors.app_background}; }}
            QFrame#onlineSourceHeaderSurface {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QFrame#onlineSourceListSurface {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QLabel#onlineSourceTitle {{
                font-size: {theme.fonts.page_title}px;
                font-weight: 600;
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
            self.verify_button,
            self.back_button,
            self.select_all_button,
            self.clear_button,
        ):
            style_action(button, theme, primary=button is self.add_source_button)
        for button in (self.back_button, self.select_all_button, self.clear_button):
            style_action(button, theme)
        style_action(self.add_source_button, theme, primary=True)
        style_action(self.verify_button, theme, primary=True)
        for label in (self.eyebrow, self.hint_label, self.empty_label):
            style_caption(label, theme, subtle=True)
        for label in (self.detail_label, self.summary_label):
            style_caption(label, theme)
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
        inset = 28 if compact else 42
        self.layout().setContentsMargins(inset, 32, inset, 30)
        self.detail_label.setVisible(True)
        self.summary_label.setVisible(True)
        self.add_source_button.setText("添加" if compact else "添加来源")
        self.verify_button.setText("验证" if compact else "快速验证")
        self.select_all_button.setText("启用全部")
        self.clear_button.setText("停用全部")
