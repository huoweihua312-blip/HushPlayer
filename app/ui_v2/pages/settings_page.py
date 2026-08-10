"""Cached, in-memory Settings Center for UI V2."""

from __future__ import annotations

import platform
from functools import partial

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.settings_adapter import SettingsAdapter
from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES, category_for_key, category_key_for
from app.ui_v2.models.settings_search_result import SettingsSearchResult
from app.ui_v2.models.settings_state import SettingsState
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_badge import SettingsBadge
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory, SliderSpinControl
from app.ui_v2.widgets.settings_empty_result import SettingsEmptyResult
from app.ui_v2.widgets.settings_footer import SettingsFooter
from app.ui_v2.widgets.settings_row import SettingsRow
from app.ui_v2.widgets.settings_search_box import SettingsSearchBox
from app.ui_v2.widgets.settings_section import SettingsSection
from app.ui_v2.widgets.settings_sidebar import SettingsSidebar


class SettingsPage(QWidget):
    """A single cached settings surface backed exclusively by SettingsAdapter."""

    immersive_preview_requested = Signal()
    leave_resolved = Signal(str, str)

    def __init__(self, adapter: SettingsAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._theme = theme
        self._current_category = "general"
        self._scroll_positions: dict[str, int] = {}
        self._category_pages: dict[str, QWidget] = {}
        self._category_inners: dict[str, QWidget] = {}
        self._rows: dict[str, SettingsRow] = {}
        self._controls: dict[str, QWidget] = {}
        self._themed_widgets: list[object] = []
        self._pending_leave_route = ""
        self._confirmation_kind = ""
        self._validation_errors: dict[str, str] = {}
        self._responsive_reference_width: int | None = None
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self.setObjectName("settingsPage")
        self._build_layout()
        self._build_categories()
        self._connect_state()
        self._feedback_timer.timeout.connect(self.feedback_label.clear)
        self._refresh_from_state(adapter.draft())
        self._update_cache_stats(adapter.cache_stats())
        self._update_dirty(adapter.is_dirty())
        valid, errors = adapter.validate()
        self._update_validation(valid, errors)
        self.set_theme(theme)

    @property
    def adapter(self) -> SettingsAdapter:
        return self._adapter

    @property
    def current_category(self) -> str:
        return self._current_category

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(f"SettingsPage {{ background: {theme.colors.content_background}; }}")
        content_color = QColor(theme.colors.content_background)
        for surface in (self.scroll, self.scroll.viewport(), self.content_stack):
            palette = surface.palette()
            palette.setColor(QPalette.ColorRole.Window, content_color)
            palette.setColor(QPalette.ColorRole.Base, content_color)
            surface.setPalette(palette)
        self.scroll.setStyleSheet(
            f"QScrollArea#settingsContentScroll {{ border: 0; background: {theme.colors.content_background}; }} "
            f"QAbstractScrollArea::viewport {{ background: {theme.colors.content_background}; }} "
            f"QScrollBar:vertical {{ width: 9px; background: transparent; }} "
            f"QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 4px; background: {theme.colors.border_strong}; }} "
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        self.content_stack.setStyleSheet(f"background: {theme.colors.content_background};")
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.page_title}px; font-weight: 650; color: {theme.colors.primary_text};")
        self.feedback_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};")
        self.sidebar.set_theme(theme)
        self.search_box.set_theme(theme)
        self.dirty_badge.set_theme(theme)
        self.footer.set_theme(theme)
        self._style_confirmation()
        for item in self._themed_widgets:
            if hasattr(item, "set_theme"):
                item.set_theme(theme)
        for row in self._rows.values():
            row.set_theme(theme)
        self._style_plain_buttons()
        if hasattr(self, "folder_list"):
            self.folder_list.setStyleSheet(
                f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};"
            )
            self.folder_input.setStyleSheet(
                f"min-height: {theme.metrics.control_height - 4}px; padding: 0 8px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};"
            )

    def set_responsive_reference_width(self, width: int) -> None:
        self._responsive_reference_width = int(width)
        self._apply_responsive_layout(self._responsive_reference_width)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout(self._responsive_reference_width or event.size().width())

    def request_leave(self, route_id: str) -> None:
        """Show the in-page save/discard/cancel decision without a native dialog."""
        self._pending_leave_route = route_id
        self._confirmation_kind = "leave"
        self.confirmation_label.setText("设置尚未保存。离开前要如何处理？")
        self.confirm_primary.setText("保存并离开")
        self.confirm_secondary.setText("放弃并离开")
        self.confirm_cancel.setText("取消")
        self.confirmation_bar.setVisible(True)

    def _build_layout(self) -> None:
        self.title_label = QLabel("设置", self)
        self.search_box = SettingsSearchBox(self._theme, self)
        self.search_box.setMinimumWidth(260)
        self.dirty_badge = SettingsBadge(self._theme, self)
        self.feedback_label = QLabel(self)
        self.feedback_label.setWordWrap(True)
        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 24, 12)
        header.setSpacing(12)
        header.addWidget(self.title_label)
        header.addWidget(self.dirty_badge)
        header.addStretch(1)
        header.addWidget(self.search_box, 1)

        self.sidebar = SettingsSidebar(self._theme, self)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("settingsContentScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_stack = QStackedWidget(self.scroll)
        self.scroll.setWidget(self.content_stack)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(self.scroll, 1)

        self.confirmation_bar = QFrame(self)
        self.confirmation_label = QLabel(self.confirmation_bar)
        self.confirm_primary = QPushButton(self.confirmation_bar)
        self.confirm_secondary = QPushButton(self.confirmation_bar)
        self.confirm_cancel = QPushButton(self.confirmation_bar)
        confirmation_layout = QHBoxLayout(self.confirmation_bar)
        confirmation_layout.setContentsMargins(18, 8, 18, 8)
        confirmation_layout.setSpacing(8)
        confirmation_layout.addWidget(self.confirmation_label, 1)
        confirmation_layout.addWidget(self.confirm_primary)
        confirmation_layout.addWidget(self.confirm_secondary)
        confirmation_layout.addWidget(self.confirm_cancel)
        self.confirmation_bar.setVisible(False)

        self.footer = SettingsFooter(self._theme, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.feedback_label)
        layout.addLayout(body, 1)
        layout.addWidget(self.confirmation_bar)
        layout.addWidget(self.footer)

    def _build_categories(self) -> None:
        self._add_category_page("general", self._build_general)
        self._add_category_page("appearance", self._build_appearance)
        self._add_category_page("playback", self._build_playback)
        self._add_category_page("lyrics", self._build_lyrics)
        self._add_category_page("immersive", self._build_immersive)
        self._add_category_page("library", self._build_library)
        self._add_category_page("cache", self._build_cache)
        self._add_category_page("updates", self._build_updates)
        self._add_category_page("about", self._build_about)
        self._build_search_page()

    def _add_category_page(self, key: str, builder) -> None:
        page = QWidget(self.content_stack)
        page.setObjectName(f"settingsCategory_{key}")
        page.setStyleSheet(f"background: {self._theme.colors.content_background};")
        outer = QHBoxLayout(page)
        outer.setContentsMargins(24, 10, 24, 24)
        inner = QWidget(page)
        inner.setMaximumWidth(900)
        inner.setMinimumWidth(600)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(28)
        builder(inner_layout)
        inner_layout.addStretch(1)
        outer.addStretch(1)
        outer.addWidget(inner)
        outer.addStretch(1)
        self._category_pages[key] = page
        self._category_inners[key] = inner
        self.content_stack.addWidget(page)

    def _build_general(self, layout: QVBoxLayout) -> None:
        section = self._section("启动与窗口", "管理 HushPlayer 的启动与窗口偏好。")
        section.add_row(self._switch_row("general.restore_last_session", "恢复上次会话", "启动 HushPlayer 时恢复上次的队列和浏览状态。"))
        section.add_row(self._switch_row("general.auto_open_floating_lyrics", "自动打开桌面歌词", "播放时自动打开桌面歌词。"))
        section.add_row(self._switch_row("general.minimize_to_tray", "最小化到托盘", "最小化后保留在通知区域。"))
        section.add_row(self._combo_row("general.close_behavior", "关闭窗口行为", "选择关闭窗口时的操作。", (("直接退出", "exit"), ("最小化到托盘", "tray"), ("每次询问", "ask"))))
        section.add_row(self._combo_row("general.language", "界面语言", "更新语言偏好，不重启也不切换完整翻译。", (("简体中文", "zh_CN"), ("English", "en_US"))))
        layout.addWidget(section)

    def _build_appearance(self, layout: QVBoxLayout) -> None:
        section = self._section("主题与密度", "主题会立即应用到当前窗口。")
        section.add_row(self._combo_row("appearance.theme_mode", "主题", "选择跟随系统、浅色或深色主题。", (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark"))))
        section.add_row(self._combo_row("appearance.accent_mode", "强调色模式", "选择界面的强调色风格。", (("系统强调色", "system"), ("冷静蓝", "blue"), ("低饱和", "muted"))))
        section.add_row(self._slider_row("appearance.ui_scale", "UI 整体缩放", "调整设置页面的界面比例。", 80, 125, "%"))
        section.add_row(self._switch_row("appearance.compact_density", "紧凑密度", "缩小设置页的垂直留白。"))
        section.add_row(self._switch_row("appearance.reduce_motion", "减少动态效果", "减少设置页提示和沉浸歌词控制层淡入淡出。"))
        layout.addWidget(section)

    def _build_playback(self, layout: QVBoxLayout) -> None:
        section = self._section("播放偏好", "调整默认音量和播放行为。")
        section.add_row(self._switch_row("playback.autoplay_on_start", "启动自动播放", "启动 HushPlayer 时继续播放上次的队列。"))
        section.add_row(self._slider_row("playback.default_volume", "默认音量", "没有已记住音量时使用的备用值。", 0, 100, "%"))
        section.add_row(self._switch_row("playback.remember_volume", "记住上次音量", "启用时优先使用上次的音量。"))
        section.add_row(self._switch_row("playback.gapless_enabled", "无缝播放", "连续曲目之间保持平滑衔接。"))
        section.add_row(self._switch_row("playback.crossfade_enabled", "交叉淡化", "启用后可调整淡化时长。"))
        section.add_row(self._slider_row("playback.crossfade_seconds", "交叉淡化秒数", "范围为 1 到 12 秒。", 1, 12, " 秒"))
        section.add_row(self._combo_row("playback.replay_gain_mode", "ReplayGain 模式", "选择音量标准化策略。", (("关闭", "off"), ("曲目", "track"), ("专辑", "album"))))
        section.add_row(self._combo_row("playback.output_device_mock", "输出设备", "选择音频输出设备。", (("系统默认", "default"), ("耳机", "headphones"), ("扬声器", "speakers"))))
        layout.addWidget(section)

    def _build_lyrics(self, layout: QVBoxLayout) -> None:
        section = self._section("普通歌词", "立即预览现有 LyricsAdapter 的显示选项，不替换其定位逻辑。")
        section.add_row(self._switch_row("lyrics.show_translation", "显示翻译", "与普通歌词和沉浸歌词同步。"))
        section.add_row(self._switch_row("lyrics.show_romanization", "显示罗马音", "与普通歌词和沉浸歌词同步。"))
        section.add_row(self._float_slider_row("lyrics.lyrics_font_scale", "整体歌词大小", "普通歌词的基础文字比例。", 80, 145, "%"))
        section.add_row(self._combo_row("lyrics.lyrics_alignment", "歌词对齐", "仅记录普通歌词的阅读偏好。", (("居中", "center"), ("左对齐", "left"))))
        section.add_row(self._switch_row("lyrics.auto_follow", "自动跟随", "记录是否自动回到当前歌词。"))
        section.add_row(self._slider_row("lyrics.manual_browse_timeout", "手动浏览超时", "浏览模式返回当前歌词前的等待时间。", 2, 20, " 秒"))
        offset_row = self._slider_row("lyrics.lyrics_offset_ms", "歌词偏移", "可向前或向后微调歌词同步。", -10000, 10000, " ms")
        reset = QToolButton(offset_row.control)
        reset.setText("重置")
        reset.setToolTip("重置歌词偏移")
        reset.clicked.connect(lambda: self._adapter.set_value("lyrics.lyrics_offset_ms", 0))
        offset_row.control.layout().addWidget(reset)
        self._themed_widgets.append(reset)
        section.add_row(offset_row)
        layout.addWidget(section)

    def _build_immersive(self, layout: QVBoxLayout) -> None:
        visual = self._section("外观", "调整沉浸歌词的外观和可读性。")
        visual.add_row(self._combo_row("immersive.background_mode", "背景模式", "使用封面、渐变、纯色或透明背景。", (("封面背景", "artwork"), ("渐变背景", "gradient"), ("纯色背景", "solid"), ("透明背景", "transparent"))))
        visual.add_row(self._slider_row("immersive.background_opacity", "背景透明度", "只影响背景图层，不淡化歌词或控制层。", 35, 85, "%"))
        visual.add_row(self._slider_row("immersive.overlay_strength", "遮罩强度", "平衡背景氛围与歌词可读性。", 15, 85, "%"))
        visual.add_row(self._slider_row("immersive.control_surface_opacity", "控制层透明度", "控制层保持独立 elevated surface。", 20, 80, "%"))
        visual.add_row(self._switch_row("immersive.lyrics_protection_enabled", "歌词保护", "为复杂背景增加克制的文字保护。"))
        visual.add_row(self._slider_row("immersive.protection_strength", "保护强度", "控制歌词保护层强度。", 0, 100, "%"))
        layout.addWidget(visual)

        lyrics = self._section("歌词", "整体缩放先作用于基础字号，单项字号保持各自比例。")
        lyrics.add_row(self._slider_row("immersive.global_font_scale", "整体歌词大小", "同时影响当前、普通、翻译和罗马音字号。", 75, 160, "%"))
        lyrics.add_row(self._combo_row("immersive.font_weight", "字重", "强调当前歌词但保持克制。", (("Regular", "Regular"), ("Medium", "Medium"), ("Semibold", "Semibold"), ("Bold", "Bold"))))
        lyrics.add_row(self._slider_row("immersive.inactive_lyric_opacity", "非当前歌词透明度", "确保前后歌词仍清晰可读。", 40, 92, "%"))
        lyrics.add_row(self._combo_row("immersive.text_protection_mode", "文字保护方式", "选择不影响整体氛围的文字保护。", (("无", "无"), ("轻微阴影", "轻微阴影"), ("柔和描边", "柔和描边"))))
        lyrics.add_row(self._switch_row("lyrics.show_translation", "显示翻译", "沿用普通歌词的共享显示状态。"))
        lyrics.add_row(self._switch_row("lyrics.show_romanization", "显示罗马音", "沿用普通歌词的共享显示状态。"))
        layout.addWidget(lyrics)

        advanced = self._section("高级字号与布局", "高级字号作为整体缩放的基础值，不产生累计误差。")
        advanced.add_row(self._slider_row("immersive.active_font_size", "当前歌词字号", "整体缩放前的基础字号。", 28, 72, " px"))
        advanced.add_row(self._slider_row("immersive.normal_font_size", "普通歌词字号", "整体缩放前的基础字号。", 18, 52, " px"))
        advanced.add_row(self._slider_row("immersive.translation_font_size", "翻译字号", "整体缩放前的基础字号。", 11, 30, " px"))
        advanced.add_row(self._slider_row("immersive.romanization_font_size", "罗马音字号", "整体缩放前的基础字号。", 11, 30, " px"))
        advanced.add_row(self._slider_row("immersive.artwork_size", "封面大小", "调节沉浸布局中的封面比例。", 70, 130, "%"))
        advanced.add_row(self._slider_row("immersive.lyrics_max_width", "歌词最大宽度", "限制超宽窗口中的单行长度。", 420, 920, " px"))
        advanced.add_row(self._switch_row("immersive.controls_auto_hide", "控制层自动隐藏", "播放中静止后自动收起控制层。"))
        layout.addWidget(advanced)
        open_preview = QPushButton("打开沉浸预览", self)
        open_preview.setToolTip("进入现有沉浸歌词页面，并可返回设置")
        open_preview.clicked.connect(self.immersive_preview_requested)
        self._themed_widgets.append(open_preview)
        layout.addWidget(open_preview, 0, Qt.AlignmentFlag.AlignLeft)

    def _build_library(self, layout: QVBoxLayout) -> None:
        section = self._section("音乐文件夹", "管理需要扫描的音乐位置。")
        self.folder_list = QListWidget(self)
        self.folder_list.setMaximumHeight(130)
        self.folder_input = QLineEdit(self)
        self.folder_input.setPlaceholderText("例如 E:\\Music\\Preview")
        self.folder_add_button = QPushButton("添加文件夹", self)
        self.folder_remove_button = QPushButton("移除", self)
        self.folder_add_button.clicked.connect(self._add_folder)
        self.folder_remove_button.clicked.connect(self._remove_selected_folder)
        folder_control = QWidget(self)
        folder_layout = QVBoxLayout(folder_control)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(6)
        folder_layout.addWidget(self.folder_list)
        add_layout = QHBoxLayout()
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.addWidget(self.folder_input, 1)
        add_layout.addWidget(self.folder_add_button)
        add_layout.addWidget(self.folder_remove_button)
        folder_layout.addLayout(add_layout)
        section.add_row(self._custom_row("library.mock_music_folders", "音乐文件夹", "长路径可以悬停查看。", folder_control))
        section.add_row(self._switch_row("library.scan_on_start", "启动扫描", "启动 HushPlayer 时扫描音乐文件夹。"))
        section.add_row(self._switch_row("library.include_subfolders", "包含子文件夹", "扫描时同时包含子文件夹。"))
        section.add_row(self._combo_row("library.import_mode", "导入模式", "决定发现新歌曲后的处理方式。", (("先审核", "review"), ("直接导入", "direct"))))
        section.add_row(self._slider_row("library.ignore_short_tracks_seconds", "忽略短音频", "短于此时长的曲目会被忽略。", 0, 60, " 秒"))
        section.add_row(self._switch_row("library.watch_folder_changes", "监视文件夹变化", "音乐文件夹内容变化时自动更新。"))
        layout.addWidget(section)

    def _build_cache(self, layout: QVBoxLayout) -> None:
        section = self._section("缓存策略", "控制封面、歌词和在线音频的缓存方式。")
        section.add_row(self._switch_row("cache.artwork_cache_enabled", "封面缓存", "保留已加载的封面以便快速显示。"))
        section.add_row(self._switch_row("cache.lyrics_cache_enabled", "歌词缓存", "保留已加载的歌词以便快速显示。"))
        section.add_row(self._switch_row("cache.online_audio_cache_enabled", "在线音频缓存", "允许缓存可用的在线音频。"))
        section.add_row(self._slider_row("cache.cache_limit_mb", "缓存上限", "设置可使用的缓存容量。", 128, 8192, " MB"))
        section.add_row(self._switch_row("cache.clear_incomplete_on_start", "启动时清理未完成缓存", "启动时移除未完成的缓存任务。"))
        self.cache_stats_label = QLabel(self)
        self.cache_stats_label.setWordWrap(True)
        refresh = QPushButton("刷新统计", self)
        incomplete = QPushButton("清理未完成缓存", self)
        clear_all = QPushButton("清理全部缓存", self)
        refresh.clicked.connect(self._adapter.refresh_mock_cache_stats)
        incomplete.clicked.connect(self._adapter.clear_mock_incomplete_cache)
        clear_all.clicked.connect(lambda: self._show_confirmation("cache", "确定清理全部缓存吗？"))
        operations = QWidget(self)
        operations_layout = QVBoxLayout(operations)
        operations_layout.setContentsMargins(0, 0, 0, 0)
        operations_layout.setSpacing(6)
        operations_layout.addWidget(self.cache_stats_label)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(refresh)
        buttons.addWidget(incomplete)
        buttons.addWidget(clear_all)
        operations_layout.addLayout(buttons)
        self._themed_widgets.extend((refresh, incomplete, clear_all, self.cache_stats_label))
        section.add_row(self._custom_row("cache.operations", "缓存操作", "查看缓存用量并执行清理。", operations))
        layout.addWidget(section)

    def _build_updates(self, layout: QVBoxLayout) -> None:
        section = self._section("更新偏好", "管理更新检查和下载偏好。")
        section.add_row(self._switch_row("updates.auto_check_updates", "自动检查更新", "关闭后启动检查延迟会禁用。"))
        section.add_row(self._combo_row("updates.update_channel", "更新通道", "选择稳定版或测试版更新通道。", (("稳定版", "stable"), ("测试版", "beta"))))
        section.add_row(self._slider_row("updates.startup_check_delay_seconds", "启动检查延迟", "启动后等待指定时间再检查更新。", 0, 60, " 秒"))
        section.add_row(self._switch_row("updates.download_updates_automatically", "自动下载更新", "发现更新后自动准备下载。"))
        self.update_status_label = QLabel("上次检查：尚未检查", self)
        self.update_status_label.setWordWrap(True)
        check = QPushButton("检查更新", self)
        check.clicked.connect(self._adapter.check_mock_updates)
        operations = QWidget(self)
        operations_layout = QHBoxLayout(operations)
        operations_layout.setContentsMargins(0, 0, 0, 0)
        operations_layout.addWidget(self.update_status_label, 1)
        operations_layout.addWidget(check)
        self._themed_widgets.extend((self.update_status_label, check))
        section.add_row(self._custom_row("updates.operations", "更新状态", "查看当前更新状态。", operations))
        layout.addWidget(section)

    def _build_about(self, layout: QVBoxLayout) -> None:
        section = self._section("HushPlayer", "查看应用和运行环境信息。")
        details = QLabel(
            f"HushPlayer\n版本 0.2.0\nPython {platform.python_version()}\nPySide6\n{platform.platform()}",
            self,
        )
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setWordWrap(True)
        project = QPushButton("查看项目主页", self)
        project.setToolTip("项目主页")
        project.clicked.connect(lambda: self._show_feedback("项目主页", "项目主页暂不可用。"))
        update = QPushButton("检查更新", self)
        update.clicked.connect(self._adapter.check_mock_updates)
        controls = QWidget(self)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        controls_layout.addWidget(details)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(project)
        buttons.addWidget(update)
        buttons.addStretch(1)
        controls_layout.addLayout(buttons)
        self._themed_widgets.extend((details, project, update))
        section.add_row(self._custom_row("about.application", "应用信息", "文本可复制；运行环境由代码安全读取。", controls))
        layout.addWidget(section)

    def _build_search_page(self) -> None:
        self.search_page = QWidget(self.content_stack)
        self.search_layout = QVBoxLayout(self.search_page)
        self.search_layout.setContentsMargins(32, 16, 32, 24)
        self.search_layout.setSpacing(4)
        self.search_title = QLabel("搜索结果", self.search_page)
        self.search_layout.addWidget(self.search_title)
        self.search_empty = SettingsEmptyResult(self._theme, self.search_page)
        self._themed_widgets.extend((self.search_empty, self.search_title))
        self.content_stack.addWidget(self.search_page)

    def _section(self, title: str, description: str) -> SettingsSection:
        section = SettingsSection(title, description, self._theme, self)
        self._themed_widgets.append(section)
        return section

    def _switch_row(self, path: str, title: str, description: str) -> SettingsRow:
        control = SettingsControlFactory.switch(bool(self._adapter.get_value(path)), self._theme, self)
        control.toggled.connect(partial(self._adapter.set_value, path))
        return self._register_row(path, title, description, control)

    def _combo_row(self, path: str, title: str, description: str, items: tuple[tuple[str, str], ...]) -> SettingsRow:
        control = SettingsControlFactory.combo(items, str(self._adapter.get_value(path)), self._theme, self)
        control.currentIndexChanged.connect(lambda _index, combo=control, name=path: self._adapter.set_value(name, combo.currentData()))
        return self._register_row(path, title, description, control)

    def _slider_row(self, path: str, title: str, description: str, minimum: int, maximum: int, suffix: str) -> SettingsRow:
        control = SettingsControlFactory.slider_spin(minimum, maximum, int(self._adapter.get_value(path)), suffix, self._theme, self)
        control.value_changed.connect(partial(self._adapter.set_value, path))
        return self._register_row(path, title, description, control)

    def _float_slider_row(self, path: str, title: str, description: str, minimum: int, maximum: int, suffix: str) -> SettingsRow:
        value = round(float(self._adapter.get_value(path)) * 100)
        control = SettingsControlFactory.slider_spin(minimum, maximum, value, suffix, self._theme, self)
        control.value_changed.connect(lambda percent, name=path: self._adapter.set_value(name, round(percent / 100, 2)))
        return self._register_row(path, title, description, control)

    def _custom_row(self, path: str, title: str, description: str, control: QWidget) -> SettingsRow:
        return self._register_row(path, title, description, control)

    def _register_row(self, path: str, title: str, description: str, control: QWidget) -> SettingsRow:
        row = SettingsRow(path, title, description, control, self._theme, self)
        self._rows[path] = row
        self._controls[path] = control
        if hasattr(control, "set_theme"):
            self._themed_widgets.append(control)
        return row

    def _connect_state(self) -> None:
        self.sidebar.category_requested.connect(self.set_category)
        self.search_box.query_changed.connect(self._search)
        self.footer.category_defaults_requested.connect(lambda: self._adapter.restore_category_defaults(self._current_category))
        self.footer.all_defaults_requested.connect(lambda: self._show_confirmation("defaults", "确定恢复全部设置默认值吗？"))
        self.footer.cancel_requested.connect(self._adapter.cancel)
        self.footer.save_requested.connect(self._adapter.save)
        self.confirm_primary.clicked.connect(self._confirm_primary)
        self.confirm_secondary.clicked.connect(self._confirm_secondary)
        self.confirm_cancel.clicked.connect(self._cancel_confirmation)
        self._adapter.draft_changed.connect(self._refresh_from_state)
        self._adapter.dirty_changed.connect(self._update_dirty)
        self._adapter.validation_changed.connect(self._update_validation)
        self._adapter.cache_stats_changed.connect(self._update_cache_stats)
        self._adapter.mock_feedback_changed.connect(self._show_feedback)
        self._adapter.update_status_changed.connect(self._update_update_status)

    def set_category(self, category: str) -> None:
        if category not in self._category_pages:
            return
        self._scroll_positions[self._current_category] = self.scroll.verticalScrollBar().value()
        self._current_category = category
        self.sidebar.set_current(category)
        self.footer.category_defaults_button.setEnabled(category != "about")
        self.content_stack.setCurrentWidget(self._category_pages[category])
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self._scroll_positions.get(category, 0)))

    def _search(self, query: str) -> None:
        results = self._adapter.search(query)
        if not str(query).strip():
            self.content_stack.setCurrentWidget(self._category_pages[self._current_category])
            return
        self._clear_search_results()
        self.search_title.setText(f"搜索结果 · {len(results)}")
        if not results:
            self.search_layout.addWidget(self.search_empty, 1)
        else:
            for result in results:
                button = QPushButton(
                    f"{category_for_key(category_key_for(result.category)).title} · {result.title}",
                    self.search_page,
                )
                button.setToolTip(result.description)
                button.clicked.connect(partial(self._jump_to_result, result))
                self.search_layout.addWidget(button)
        self.search_layout.addStretch(1)
        self.content_stack.setCurrentWidget(self.search_page)
        self.scroll.verticalScrollBar().setValue(0)
        self._style_plain_buttons()

    def _clear_search_results(self) -> None:
        while self.search_layout.count() > 1:
            item = self.search_layout.takeAt(1)
            widget = item.widget()
            if widget is not None and widget is not self.search_empty:
                widget.deleteLater()

    def _jump_to_result(self, result: SettingsSearchResult) -> None:
        self.search_box.input.clear()
        self.set_category(category_key_for(result.category))
        row = self._rows.get(result.path)
        if row is None:
            return
        def reveal() -> None:
            target = row.mapTo(self.content_stack, row.rect().topLeft()).y()
            self.scroll.verticalScrollBar().setValue(max(0, target - 36))
            row.flash_highlight()
        QTimer.singleShot(0, reveal)

    def _refresh_from_state(self, state: SettingsState) -> None:
        for path, control in self._controls.items():
            try:
                value = state.get_value(path)
            except (AttributeError, ValueError):
                continue
            if isinstance(control, QCheckBox):
                with QSignalBlocker(control):
                    control.setChecked(bool(value))
            elif isinstance(control, QComboBox):
                with QSignalBlocker(control):
                    control.setCurrentIndex(max(0, control.findData(value)))
            elif isinstance(control, SliderSpinControl):
                control.set_value(round(float(value) * 100) if path == "lyrics.lyrics_font_scale" else int(value))
        self._refresh_folder_list(state.library.mock_music_folders)
        self._update_dependencies(state)

    def _refresh_folder_list(self, folders: list[str]) -> None:
        if not hasattr(self, "folder_list"):
            return
        current = self.folder_list.currentItem().text() if self.folder_list.currentItem() else ""
        self.folder_list.clear()
        for path in folders:
            item = QListWidgetItem(path)
            item.setToolTip(path)
            self.folder_list.addItem(item)
            if path == current:
                self.folder_list.setCurrentItem(item)

    def _update_dependencies(self, state: SettingsState) -> None:
        crossfade = self._controls.get("playback.crossfade_seconds")
        if crossfade is not None:
            crossfade.setEnabled(state.playback.crossfade_enabled)
        delay = self._controls.get("updates.startup_check_delay_seconds")
        if delay is not None:
            delay.setEnabled(state.updates.auto_check_updates)
        if hasattr(self, "folder_remove_button"):
            self.folder_remove_button.setEnabled(bool(state.library.mock_music_folders))

    def _update_dirty(self, dirty: bool) -> None:
        self.dirty_badge.set_status("有未保存更改" if dirty else "", "warning")
        valid, _errors = self._adapter.validate()
        self.footer.set_state(dirty=dirty, valid=valid)

    def _update_validation(self, valid: bool, errors: dict[str, str]) -> None:
        self._validation_errors = dict(errors)
        self.footer.set_state(dirty=self._adapter.is_dirty(), valid=valid)
        if not valid:
            self.dirty_badge.set_status("请修正设置项", "danger")

    def _update_cache_stats(self, stats: dict[str, int]) -> None:
        if hasattr(self, "cache_stats_label"):
            self.cache_stats_label.setText(
                f"封面 {stats['artwork']} MB · 歌词 {stats['lyrics']} MB · 在线音频 {stats['audio']} MB · 未完成 {stats['incomplete']} MB · 总计 {stats['total']} MB"
            )

    def _update_update_status(self, status: dict[str, str]) -> None:
        if hasattr(self, "update_status_label"):
            self.update_status_label.setText(f"{status['title']}：{status['detail']}")

    def _add_folder(self) -> None:
        path = self.folder_input.text().strip() or "E:\\Music\\Immersive Preview"
        if self._adapter.add_mock_folder(path):
            self.folder_input.clear()

    def _remove_selected_folder(self) -> None:
        item = self.folder_list.currentItem()
        if item is None:
            return
        self._show_confirmation("folder", f"确定移除音乐文件夹“{item.text()}”吗？", item.text())

    def _show_confirmation(self, kind: str, message: str, payload: str = "") -> None:
        self._confirmation_kind = f"{kind}:{payload}" if payload else kind
        self.confirmation_label.setText(message)
        self.confirm_primary.setText("确认")
        self.confirm_secondary.setVisible(False)
        self.confirm_cancel.setText("取消")
        self.confirmation_bar.setVisible(True)

    def _confirm_primary(self) -> None:
        if self._confirmation_kind == "leave":
            if self._adapter.save():
                self._resolve_leave("save")
        elif self._confirmation_kind == "defaults":
            self._adapter.restore_defaults()
            self._hide_confirmation()
        elif self._confirmation_kind == "cache":
            self._adapter.clear_all_mock_cache()
            self._hide_confirmation()
        elif self._confirmation_kind.startswith("folder:"):
            self._adapter.remove_mock_folder(self._confirmation_kind.partition(":")[2])
            self._hide_confirmation()

    def _confirm_secondary(self) -> None:
        if self._confirmation_kind == "leave":
            self._adapter.cancel()
            self._resolve_leave("discard")

    def _resolve_leave(self, decision: str) -> None:
        route = self._pending_leave_route
        self._hide_confirmation()
        self.leave_resolved.emit(route, decision)

    def _hide_confirmation(self) -> None:
        self.confirmation_bar.setVisible(False)
        self.confirm_secondary.setVisible(True)
        self._confirmation_kind = ""
        self._pending_leave_route = ""

    def _cancel_confirmation(self) -> None:
        was_leave = self._confirmation_kind == "leave"
        self._hide_confirmation()
        if was_leave:
            self.leave_resolved.emit("settings", "cancel")

    def _show_feedback(self, title: str, detail: str) -> None:
        self.feedback_label.setText(f"{title} · {detail}")
        self._feedback_timer.start(3000)

    def _apply_responsive_layout(self, width: int) -> None:
        compact = width < 1100
        self.sidebar.set_compact(compact)
        self.search_box.setMinimumWidth(200 if compact else 300)
        state = self._adapter.draft()
        density = 20 if state.appearance.compact_density else 28
        scale = max(80, min(125, state.appearance.ui_scale)) / 100
        self.search_box.input.setMinimumHeight(round(self._theme.metrics.control_height * scale))
        for page in self._category_pages.values():
            for child in page.findChildren(SettingsSection):
                child.layout().setSpacing(max(5, round(self._theme.metrics.spacing_sm * scale)))
            page.setContentsMargins(0, 0, 0, 0)
        margins = 12 if compact else 24
        for inner in self._category_inners.values():
            inner.setMinimumWidth(0 if compact else 600)
        for page in self._category_pages.values():
            layout = page.layout()
            if layout is not None:
                layout.setContentsMargins(margins, 8, margins, 18)

    def _style_confirmation(self) -> None:
        theme = self._theme
        self.confirmation_bar.setStyleSheet(f"SettingsConfirmBar {{ background: {theme.colors.elevated_background}; border-top: 1px solid {theme.colors.border}; }}")
        self.confirmation_label.setStyleSheet(f"color: {theme.colors.primary_text};")
        for button in (self.confirm_primary, self.confirm_secondary, self.confirm_cancel):
            button.setStyleSheet(f"min-height: {theme.metrics.control_height - 4}px; padding: 0 10px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};")

    def _style_plain_buttons(self) -> None:
        theme = self._theme
        for widget in self._themed_widgets:
            if isinstance(widget, (QPushButton, QToolButton)):
                widget.setStyleSheet(f"min-height: {theme.metrics.control_height - 2}px; padding: 0 10px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};")
            elif isinstance(widget, QLabel):
                widget.setStyleSheet(f"color: {theme.colors.secondary_text};")
        if hasattr(self, "search_page"):
            for button in self.search_page.findChildren(QPushButton):
                button.setStyleSheet(f"min-height: {theme.metrics.control_height - 2}px; text-align: left; padding: 0 10px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};")
