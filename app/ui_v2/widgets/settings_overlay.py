"""Modal Settings Overlay for the formal UI V2 shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, QTimer, QRect, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from app.ui_v2.adapters.legacy_settings_bridge import (
    DEFAULT_SETTINGS,
    LegacySettingsBridge,
    SettingsBridgeError,
    normalize_immersive_background_visual_mode,
)
from app.ui_v2.adapters.online_source_adapter import OnlineSourceAdapter
from app.core.version import APP_NAME, APP_VERSION
from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES, category_for_key
from app.ui_v2.models.settings_edit_session import SettingsEditSession
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.pages.online_source_page import OnlineSourcePage
from app.ui_v2.pages.pending_imports_page import PendingImportsPage
from app.services.music_folder_scan import MusicFolderImportService
from app.ui_v2.theme.icons import fluent_settings_icon, fluent_settings_interactive_icon
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES, Theme
from app.ui_v2.widgets.settings_control_factory import (
    SettingsControlFactory,
    SettingSlider,
    SettingsActionButton,
    SettingsDangerAction,
    SettingsPathPicker,
    ThemedComboBox,
)
from app.ui_v2.widgets.settings_footer import SettingsFooter
from app.ui_v2.widgets.settings_row import SettingsRow
from app.ui_v2.widgets.settings_section import SettingsSection
from app.ui_v2.widgets.settings_sidebar import SettingsSidebar


@dataclass(slots=True)
class _PathControl:
    widget: QWidget
    picker: SettingsPathPicker


def _published_changelog_text() -> str:
    """Return user-facing release summaries while hiding development details."""

    changelog_path = Path(__file__).resolve().parents[3] / "CHANGELOG.md"
    try:
        lines = changelog_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "暂时无法读取更新日志。"
    published: list[str] = []
    version_heading = ""
    in_summary = False
    for line in lines:
        if line.startswith("## "):
            heading = line.removeprefix("## ").strip()
            version_heading = line if heading and heading[0].isdigit() else ""
            in_summary = False
            if version_heading:
                published.append(version_heading)
            continue
        if line.startswith("### "):
            in_summary = line.strip() == "### 在线更新摘要" and bool(version_heading)
            if in_summary:
                published.append(line)
            continue
        if in_summary and not any(
            token in line.casefold() for token in ("mock", "demo", "fixture", "preview")
        ):
            published.append(line)
    text = "\n".join(published).strip()
    return text or "暂时没有可用的更新日志。"


class _OverlayScrim(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class SettingsConfirmDialog(QFrame):
    """Inline themed confirmation panel; never creates a system window."""

    confirm_requested = Signal()
    discard_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsConfirmDialog")
        self.title_label = QLabel(self)
        self.message_label = QLabel(self)
        self.message_label.setWordWrap(True)
        self.confirm_button = SettingsDangerAction("确认", theme, self)
        self.discard_button = SettingsDangerAction("放弃修改", theme, self)
        self.cancel_button = SettingsActionButton("取消", theme, self)
        self.confirm_button.clicked.connect(self.confirm_requested)
        self.discard_button.clicked.connect(self.discard_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(6)
        heading.addWidget(self.title_label)
        heading.addWidget(self.message_label)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 12, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.confirm_button)
        buttons.addWidget(self.discard_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addLayout(heading)
        layout.addLayout(buttons)
        self.set_theme(theme)
        self.hide()

    def set_content(self, title: str, message: str, *, danger: bool) -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.confirm_button.setVisible(danger)
        self.discard_button.setVisible(not danger)
        self.cancel_button.setDefault(True)
        self.cancel_button.setFocus()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QFrame#settingsConfirmDialog {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }} "
            f"QLabel {{ color: {c.primary_text}; }} QLabel:first-child {{ font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {c.primary_text};"
        )
        self.message_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; color: {c.secondary_text};"
        )
        self.confirm_button.set_theme(theme)
        self.discard_button.set_theme(theme)
        self.cancel_button.set_theme(theme)


class SettingsOverlay(QWidget):
    """One cached modal overlay with a fresh edit session per open."""

    closed = Signal()
    saved = Signal(object)
    pending_import_requested = Signal(object)
    pending_ignore_requested = Signal(object)
    pending_open_folder_requested = Signal(str)

    def __init__(
        self,
        bridge: LegacySettingsBridge,
        theme: Theme,
        *,
        online_sources: OnlineSourceAdapter | None = None,
        pending_import_service: MusicFolderImportService | None = None,
        preview_callback: Callable[[dict[str, Any]], None] | None = None,
        path_chooser: Callable[[str], str] | None = None,
        folder_chooser: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self._theme = theme
        self._online_sources = online_sources
        self._pending_import_service = pending_import_service
        self._preview_callback = preview_callback
        self._path_chooser = path_chooser
        self._folder_chooser = folder_chooser
        self._session: SettingsEditSession | None = None
        self._controls: dict[str, QWidget] = {}
        self._path_controls: dict[str, _PathControl] = {}
        self._rows: list[SettingsRow] = []
        self._sections: list[SettingsSection] = []
        self._aux_controls: list[QWidget] = []
        self._category_pages: dict[str, QWidget] = {}
        self._category_scrolls: dict[str, QScrollArea] = {}
        self._current_category = "general"
        self._feedback = ""
        self._save_state = "clean"
        self._pending_action = ""
        self.setObjectName("settingsOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_shell()
        self._build_categories()
        self._wire_state()
        self.set_theme(theme)
        self.hide()

    @property
    def session(self) -> SettingsEditSession | None:
        return self._session

    @property
    def current_category(self) -> str:
        return self._current_category

    @property
    def is_dirty(self) -> bool:
        return bool(self._session and self._session.is_dirty)

    def _build_shell(self) -> None:
        self.dim_layer = _OverlayScrim(self)
        self.dim_layer.setObjectName("settingsDimLayer")
        self.dim_layer.clicked.connect(self.request_close)
        self.dialog = QFrame(self)
        self.dialog.setObjectName("settingsDialog")

        self.header_icon = QToolButton(self.dialog)
        self.header_icon.setObjectName("settingsHeaderIcon")
        self.header_icon.setFixedSize(32, 32)
        self.header_icon.setAutoRaise(True)
        self.header_icon.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.title_label = QLabel("设置", self.dialog)
        self.subtitle_label = QLabel("管理 HushPlayer 的现有设置", self.dialog)
        self.close_button = QToolButton(self.dialog)
        self.close_button.setObjectName("settingsCloseButton")
        self.close_button.setIconSize(QSize(16, 16))
        self.close_button.setToolTip("关闭设置")
        self.close_button.setAccessibleName("关闭设置")
        header = QHBoxLayout()
        header.setContentsMargins(24, 18, 18, 14)
        header.setSpacing(10)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(2)
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header.addWidget(self.header_icon)
        header.addLayout(heading, 1)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

        self.sidebar = SettingsSidebar(self._theme, self.dialog)
        self.content_stack = QStackedWidget(self.dialog)
        self.content_stack.setObjectName("settingsContentStack")
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(self.content_stack, 1)

        self.confirmation_bar = QFrame(self.dialog)
        self.confirmation_bar.setObjectName("settingsConfirmationBar")
        confirmation_label = QLabel("设置尚未保存。离开前要如何处理？", self.confirmation_bar)
        self.confirm_save = QPushButton("保存并关闭", self.confirmation_bar)
        self.confirm_discard = QPushButton("放弃修改", self.confirmation_bar)
        self.confirm_cancel = QPushButton("继续编辑", self.confirmation_bar)
        confirmation_layout = QHBoxLayout(self.confirmation_bar)
        confirmation_layout.setContentsMargins(18, 8, 18, 8)
        confirmation_layout.setSpacing(8)
        confirmation_layout.addWidget(confirmation_label, 1)
        confirmation_layout.addWidget(self.confirm_save)
        confirmation_layout.addWidget(self.confirm_discard)
        confirmation_layout.addWidget(self.confirm_cancel)
        self.confirmation_bar.hide()

        self.footer = SettingsFooter(self._theme, self.dialog)
        self.confirm_scrim = _OverlayScrim(self)
        self.confirm_scrim.setObjectName("settingsConfirmScrim")
        self.confirm_scrim.clicked.connect(self._hide_confirmation)
        self.confirm_dialog = SettingsConfirmDialog(self._theme, self)
        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addLayout(body, 1)
        layout.addWidget(self.confirmation_bar)
        layout.addWidget(self.footer)
        self.confirm_scrim.hide()
        self.confirm_dialog.hide()

    def _build_categories(self) -> None:
        builders = {
            "general": self._build_general,
            "appearance": self._build_appearance,
            "playback": self._build_playback,
            "lyrics": self._build_lyrics,
            "library": self._build_library,
            "cache": self._build_cache,
            "updates": self._build_updates,
            "about": self._build_about,
        }
        for category in SETTINGS_CATEGORIES:
            if category.key == "online_sources":
                page = self._build_online_sources_page()
                self._category_pages[category.key] = page
                self.content_stack.addWidget(page)
                continue
            if category.key == "pending_imports":
                page = self._build_pending_imports_page()
                self._category_pages[category.key] = page
                self.content_stack.addWidget(page)
                continue
            page = QWidget(self.content_stack)
            page.setObjectName(f"settingsCategory_{category.key}")
            outer = QVBoxLayout(page)
            outer.setContentsMargins(24, 12, 24, 24)
            outer.setSpacing(0)
            scroll = QScrollArea(page)
            scroll.setObjectName(f"settingsScroll_{category.key}")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content = QWidget(scroll)
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(24)
            builders[category.key](content_layout)
            content_layout.addStretch(1)
            scroll.setWidget(content)
            outer.addWidget(scroll)
            self._category_pages[category.key] = page
            self._category_scrolls[category.key] = scroll
            self.content_stack.addWidget(page)

    def _build_online_sources_page(self) -> QWidget:
        """Embed the production source manager as one settings category."""

        if self._online_sources is None:
            page = QWidget(self.content_stack)
            message = QLabel("在线来源服务当前不可用。", page)
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout = QVBoxLayout(page)
            layout.addWidget(message)
            return page
        page = OnlineSourcePage(self._online_sources, self._theme, self.content_stack)
        page.setObjectName("settingsCategory_online_sources")
        page.back_button.hide()
        return page

    def _build_pending_imports_page(self) -> PendingImportsPage:
        """Reuse the existing review surface inside Settings without a shell route."""

        page = PendingImportsPage(self._theme, self.content_stack)
        page.header.set_context("设置")
        page.import_requested.connect(self.pending_import_requested)
        page.ignore_requested.connect(self.pending_ignore_requested)
        page.open_folder_requested.connect(self.pending_open_folder_requested)
        service = self._pending_import_service
        if service is None:
            page.set_records(())
            page.set_status("待导入服务当前不可用。")
        else:
            self._sync_pending_records(service.pending_records(), page=page)
            service.pending_changed.connect(self._sync_pending_records)
        self.pending_imports_page = page
        return page

    def _sync_pending_records(
        self,
        records: object,
        *,
        page: PendingImportsPage | None = None,
    ) -> None:
        target = page or getattr(self, "pending_imports_page", None)
        if target is None:
            return
        values = records if isinstance(records, (list, tuple)) else ()
        target.set_records(values)
        self.sidebar.set_category_count("pending_imports", len(values))

    def _wire_state(self) -> None:
        self.sidebar.category_requested.connect(self.set_category)
        self.close_button.clicked.connect(self.request_close)
        self.footer.cancel_requested.connect(self.request_close)
        self.footer.save_requested.connect(self.save)
        self.confirm_save.clicked.connect(self.save_and_close)
        self.confirm_discard.clicked.connect(self.cancel_and_close)
        self.confirm_cancel.clicked.connect(self._hide_confirmation)
        self.confirm_dialog.confirm_requested.connect(self._confirm_pending_action)
        self.confirm_dialog.discard_requested.connect(self.cancel_and_close)
        self.confirm_dialog.cancel_requested.connect(self._hide_confirmation)

    def _section(self, title: str, description: str) -> SettingsSection:
        return SettingsSection(title, description, self._theme, self)

    def _toggle_row(self, key: str, title: str, description: str) -> SettingsRow:
        control = SettingsControlFactory.switch(False, self._theme, self)
        self._bind_control(key, control, lambda: bool(control.isChecked()), control.setChecked, control.toggled)
        return self._track_row(SettingsRow(key, title, description, control, self._theme, self))

    def _combo_row(
        self,
        key: str,
        title: str,
        description: str,
        items: tuple[tuple[str, str], ...],
    ) -> SettingsRow:
        control = SettingsControlFactory.combo(items, items[0][1], self._theme, self)
        self._bind_control(
            key,
            control,
            lambda: str(control.currentData()),
            lambda value: control.setCurrentIndex(max(0, control.findData(value))),
            control.currentIndexChanged,
        )
        return self._track_row(SettingsRow(key, title, description, control, self._theme, self))

    def _slider_row(
        self,
        key: str,
        title: str,
        description: str,
        minimum: int,
        maximum: int,
        suffix: str,
    ) -> SettingsRow:
        control = SettingsControlFactory.slider_spin(minimum, maximum, minimum, suffix, self._theme, self)
        self._bind_control(key, control, control.value, control.set_value, control.value_changed)
        return self._track_row(SettingsRow(key, title, description, control, self._theme, self))

    def _path_row(self, key: str, title: str, description: str) -> SettingsRow:
        container = QWidget(self)
        picker = SettingsPathPicker(self._theme, container)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(picker)
        path_control = _PathControl(container, picker)
        self._path_controls[key] = path_control
        picker.path_changed.connect(lambda value, path=key: self._path_value_changed(path, value))
        picker.browse_requested.connect(lambda path=key: self._choose_path(path))
        picker.open_requested.connect(lambda path=key: self._open_path(path))
        self._controls[key] = container
        return self._track_row(SettingsRow(key, title, description, container, self._theme, self))

    def _track_row(self, row: SettingsRow) -> SettingsRow:
        self._rows.append(row)
        return row

    def _track_section(self, section: SettingsSection) -> SettingsSection:
        self._sections.append(section)
        return section

    def _build_general(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("启动与窗口", "保留现有 HushPlayer 启动和窗口行为。"))
        section.add_row(self._toggle_row("auto_scan_music_folders_on_startup", "启动时自动扫描这些文件夹", "启动时扫描已保存的音乐文件夹。"))
        section.add_row(self._toggle_row("floating_lyrics_auto_open", "启动时自动打开桌面歌词", "播放启动时自动打开现有桌面歌词窗口。"))
        section.add_row(self._toggle_row("remember_close_choice", "记住关闭窗口时的选择", "关闭后记住“直接退出”或“最小化到托盘”；关闭此项后恢复每次询问。"))
        layout.addWidget(section)

    def _build_appearance(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("主题", "沿用当前正式 Theme，不创建第二套壳层。"))
        section.add_row(self._combo_row("appearance_mode", "主题", "切换后立即应用，保存后写入现有设置文件。", (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark"))))
        layout.addWidget(section)

    def _build_playback(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("播放恢复", "沿用现有播放会话恢复语义。"))
        section.add_row(self._toggle_row("restore_last_playback", "启动时恢复上次播放的歌曲和进度", "启动时读取现有播放会话。"))
        layout.addWidget(section)

    def _build_lyrics(self, layout: QVBoxLayout) -> None:
        immersive = self._track_section(self._section("沉浸歌词", "保留现有沉浸歌词设置，不改变 Lyrics 或沉浸页面结构。"))
        immersive.add_row(self._toggle_row("immersive_auto_hide_ui", "自动隐藏控制层", "播放中静止后按现有规则隐藏控制层。"))
        immersive.add_row(self._combo_row("immersive_background_mode", "背景模式", "使用封面、纯色、半透明或自定义背景。", (("封面背景", "cover"), ("纯色背景", "default"), ("半透明背景", "translucent"), ("自定义图片", "custom"))))
        immersive.add_row(self._path_row("immersive_background_custom_path", "自定义背景图片", "仅在选择自定义背景时使用。"))
        immersive.add_row(self._slider_row("immersive_background_blur", "背景模糊", "保留现有背景模糊范围。", 0, 40, " px"))
        immersive.add_row(self._slider_row("immersive_background_darkness", "背景暗度", "仅影响背景图层。", 0, 90, "%"))
        immersive.add_row(self._slider_row("immersive_background_image_opacity", "背景图片不透明度", "仅影响背景图片。", 20, 100, "%"))
        immersive.add_row(self._slider_row("immersive_background_transparency", "背景透明度", "沿用现有透明度语义。", 0, 85, "%"))
        immersive.add_row(self._combo_row("immersive_background_fill_mode", "背景填充方式", "选择封面填充或完整显示。", (("填充", "cover"), ("完整显示", "contain"))))
        immersive.add_row(self._slider_row("immersive_lyrics_font_scale", "沉浸歌词字号比例", "沿用现有 70% 到 160% 范围。", 70, 160, "%"))
        layout.addWidget(immersive)

        floating = self._track_section(self._section("桌面歌词", "调整桌面歌词窗口的外观；显示后可从边缘进入交互并拖动位置。"))
        floating.add_row(self._combo_row("floating_lyrics_color", "默认歌词颜色", "保存后应用到桌面歌词窗口。", (("白色", "white"), ("黑色", "black"), ("黄色", "yellow"), ("蓝色", "blue"), ("绿色", "green"), ("粉色", "pink"), ("紫色", "purple"))))
        floating.add_row(self._combo_row("floating_lyrics_font_family", "歌词字体", "仅提供随应用分发且具有开放授权的字体。", tuple((family, family) for family in OPEN_FONT_FAMILIES)))
        floating.add_row(self._slider_row("floating_lyrics_opacity", "默认不透明度", "保留现有 20% 到 100% 范围。", 20, 100, "%"))
        floating.add_row(self._slider_row("floating_lyrics_font_size", "默认字号", "保留现有 22 到 84 px 范围。", 22, 84, " px"))
        floating.add_row(self._slider_row("floating_lyrics_width", "默认宽度", "保留现有 420 到 1600 px 范围。", 420, 1600, " px"))
        floating.add_row(self._toggle_row("floating_lyrics_passthrough", "默认鼠标穿透", "默认不拦截其他应用；进入窗口边缘后可临时操作工具栏。"))
        layout.addWidget(floating)

    def _build_library(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("音乐文件夹", "修改后保存到现有扫描设置；手动扫描仍是独立操作。"))
        self.folder_list = QListWidget(self)
        self.folder_list.setObjectName("settingsFolderList")
        self.folder_list.setMinimumHeight(100)
        section.add_widget(self.folder_list)
        buttons = QHBoxLayout()
        add = SettingsActionButton("添加文件夹", self._theme, self)
        remove = SettingsActionButton("移除选中", self._theme, self)
        scan = SettingsActionButton("手动重新扫描", self._theme, self)
        self._aux_controls.extend((add, remove, scan))
        add.clicked.connect(self._add_folder)
        remove.clicked.connect(self._remove_folder)
        scan.clicked.connect(lambda: self._run_action("scan_music_folders"))
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(scan)
        buttons.addStretch(1)
        section.add_layout(buttons)
        section.add_row(self._combo_row("music_scan_import_mode", "扫描新音乐后的处理方式", "沿用待导入或自动加入音乐库的现有语义。", (("进入待导入列表，手动确认", "pending"), ("自动加入音乐库", "auto"))))
        layout.addWidget(section)

    def _build_cache(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("缓存", "缓存命令不参与 Save/Dirty；仅调用现有服务。"))
        cache_path_row = self._path_row(
            "cache_directory",
            "缓存位置",
            "留空表示使用系统默认目录；修改后重启 HushPlayer 才会切换。",
        )
        cache_path_control = self._path_controls["cache_directory"].picker
        cache_path_control.clear_button.setText("恢复默认")
        cache_path_control.clear_button.setToolTip("恢复系统默认缓存目录")
        section.add_row(cache_path_row)
        self.cache_status = QLabel("缓存统计由正式缓存服务提供。", self)
        self.cache_status.setWordWrap(True)
        section.add_widget(self.cache_status)
        operations = QWidget(self)
        operations.setObjectName("settingsCacheOperations")
        operations_layout = QGridLayout(operations)
        operations_layout.setContentsMargins(0, 4, 0, 0)
        operations_layout.setHorizontalSpacing(10)
        operations_layout.setVerticalSpacing(10)
        for index, (text, action) in enumerate((
            ("清理封面 / 歌词失败缓存", "clear_missing_cache"),
            ("打开音频缓存目录", "open_audio_cache_directory"),
            ("清理未完成音频缓存", "clear_incomplete_audio_cache"),
            ("清理全部音频缓存", "clear_all_audio_cache"),
        )):
            button = (
                SettingsActionButton(text, self._theme, self)
                if action == "open_audio_cache_directory"
                else SettingsDangerAction(text, self._theme, self)
            )
            self._aux_controls.append(button)
            button.clicked.connect(lambda _checked=False, name=action: self._run_action(name))
            button.setEnabled(self.bridge.has_action(action))
            operations_layout.addWidget(button, index // 2, index % 2)
        section.add_widget(operations)
        layout.addWidget(section)

    def _build_updates(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("应用更新", "更新检查沿用现有 AppUpdateService。"))
        section.add_row(self._toggle_row("auto_check_updates_on_startup", "启动后自动检查更新", "下次启动时按现有服务规则检查。"))
        section.add_row(self._combo_row("update_check_delay_seconds", "启动后延迟", "保留现有 5 到 300 秒范围。", (("5 秒", "5"), ("15 秒", "15"), ("30 秒", "30"), ("60 秒", "60"))))
        self.update_status = QLabel("尚未检查更新。", self)
        self.update_status.setWordWrap(True)
        section.add_widget(self.update_status)
        check = SettingsActionButton("检查更新", self._theme, self)
        self._aux_controls.append(check)
        check.clicked.connect(lambda: self._run_action("check_updates"))
        check.setEnabled(self.bridge.has_action("check_updates"))
        section.add_widget(check)
        layout.addWidget(section)

    def _build_about(self, layout: QVBoxLayout) -> None:
        section = self._track_section(self._section("关于 HushPlayer", "当前 HushPlayer 的版本与应用信息。"))
        logo = QLabel(self)
        logo.setObjectName("settingsAboutLogo")
        logo.setAccessibleName("Quiet Orbit")
        logo.setFixedSize(72, 48)
        logo.setPixmap(
            QPixmap(str(Path(__file__).resolve().parents[1] / "assets" / "quiet-orbit-logo.svg"))
            .scaled(72, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        app_name = QLabel(APP_NAME, self)
        app_name.setObjectName("settingsAboutAppName")
        app_name.setWordWrap(True)
        version = QLabel(f"版本 {APP_VERSION}", self)
        version.setObjectName("settingsAboutVersion")
        version.setWordWrap(True)
        section.add_widget(logo)
        section.add_widget(app_name)
        section.add_widget(version)
        layout.addWidget(section)

        changelog = self._track_section(self._section("更新日志", "查看已发布版本的主要变化。"))
        self.about_changelog = QPlainTextEdit(self)
        self.about_changelog.setObjectName("settingsAboutChangelog")
        self.about_changelog.setReadOnly(True)
        self.about_changelog.setPlainText(_published_changelog_text())
        self.about_changelog.setMinimumHeight(260)
        self.about_changelog.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        changelog.add_widget(self.about_changelog)
        layout.addWidget(changelog)

    def _bind_control(self, key: str, control: QWidget, getter, setter, signal) -> None:
        self._controls[key] = control
        signal.connect(lambda *_args, path=key, read=getter: self._value_changed(path, read()))

    def _value_changed(self, key: str, value: Any) -> None:
        if self._session is None:
            return
        if key == "update_check_delay_seconds":
            value = int(value)
        changed = self._session.set(key, value)
        if changed and key == "immersive_background_mode":
            self._session.set(
                "immersive_background_visual_mode",
                normalize_immersive_background_visual_mode(None, value),
            )
        if changed and key == "appearance_mode" and self._preview_callback is not None:
            self._session.mark_previewed(key)
            self._preview_callback(self._session.working_snapshot.to_dict())
        self._refresh_state()

    def _sync_controls(self) -> None:
        if self._session is None:
            return
        for key, control in self._controls.items():
            value = self.bridge.value(self._session.working_snapshot, key)
            if key in self._path_controls:
                path_control = self._path_controls[key]
                with QSignalBlocker(path_control.picker):
                    path_control.picker.set_path(str(value or ""))
                continue
            with QSignalBlocker(control):
                if isinstance(control, QLineEdit):
                    control.setText(str(value or ""))
                elif isinstance(control, ThemedComboBox):
                    control.setCurrentIndex(max(0, control.findData(str(value))))
                elif isinstance(control, SettingSlider):
                    control.set_value(int(value))
                elif hasattr(control, "setChecked"):
                    control.setChecked(bool(value))
        if hasattr(self, "folder_list"):
            self.folder_list.clear()
            for folder in self.bridge.value(self._session.working_snapshot, "music_scan_folders") or []:
                self.folder_list.addItem(str(folder))

    def _choose_path(self, key: str) -> None:
        if self._path_chooser is not None:
            selected = self._path_chooser(key)
        elif key == "cache_directory":
            selected = QFileDialog.getExistingDirectory(self, "选择缓存目录", str(Path.home()))
        else:
            selected = QFileDialog.getOpenFileName(self, "选择背景图片", str(Path.home()))[0]
        if selected:
            self._path_controls[key].picker.set_path(selected)
            if key == "immersive_background_custom_path":
                self._set_immersive_background_mode("custom")

    def _open_path(self, key: str) -> None:
        path = self._path_controls[key].picker.path()
        if path and Path(path).exists():
            self._run_action("open_settings_path", path)

    def _add_folder(self) -> None:
        if self._folder_chooser is not None:
            selected = self._folder_chooser()
        else:
            selected = QFileDialog.getExistingDirectory(self, "添加音乐文件夹", str(Path.home()))
        if not selected or self._session is None:
            return
        folders = list(self.bridge.value(self._session.working_snapshot, "music_scan_folders") or [])
        normalized = str(Path(selected).resolve())
        if normalized.casefold() not in {str(item).casefold() for item in folders}:
            folders.append(normalized)
            self._session.set("music_scan_folders", folders)
            self._sync_controls()
            self._refresh_state()

    def _remove_folder(self) -> None:
        if self._session is None:
            return
        row = self.folder_list.currentRow()
        if row < 0:
            return
        folders = list(self.bridge.value(self._session.working_snapshot, "music_scan_folders") or [])
        if row < len(folders):
            folders.pop(row)
            self._session.set("music_scan_folders", folders)
            self._sync_controls()
            self._refresh_state()

    def _run_action(self, name: str) -> None:
        if name in {
            "clear_missing_cache",
            "clear_incomplete_audio_cache",
            "clear_all_audio_cache",
        }:
            self._pending_action = name
            self._show_confirmation(
                "确认清理缓存",
                "此操作会删除本地缓存文件，且不会通过保存设置撤销。",
                danger=True,
            )
            return
        self._execute_action(name)

    def _confirm_pending_action(self) -> None:
        name = self._pending_action
        self._pending_action = ""
        self._hide_confirmation()
        if name:
            self._execute_action(name)

    def _execute_action(self, name: str) -> None:
        self._save_state = "saving"
        self.footer.set_state_message("saving", "正在处理…")
        try:
            result = self.bridge.run_action(name)
            if isinstance(result, str):
                if name == "check_updates" and hasattr(self, "update_status"):
                    self.update_status.setText(result)
                self._set_feedback(result, state="success")
            elif isinstance(result, dict):
                if hasattr(self, "cache_status"):
                    self.cache_status.setText("缓存操作已完成。")
                self._set_feedback("操作已完成。", state="success")
            else:
                self._set_feedback("操作已发送到现有服务。", state="success")
        except SettingsBridgeError as error:
            self._set_feedback(str(error), state="failed")

    def _set_feedback(self, text: str, *, state: str | None = None) -> None:
        self._feedback = str(text or "")
        if state is not None:
            self._save_state = state
            self.footer.set_state_message(state, self._feedback)
        else:
            self.footer.set_status(self._feedback)

    def set_update_status(self, text: str, *, state: str = "success") -> None:
        """Show asynchronous AppUpdateService feedback in the updates section."""

        if hasattr(self, "update_status"):
            self.update_status.setText(str(text or ""))
        self._set_feedback(str(text or ""), state=state)

    def _refresh_state(self) -> None:
        if self._session is None:
            self.footer.set_state(dirty=False, valid=False)
            return
        errors = self._session.validate(self.bridge.validate)
        if errors:
            self._save_state = "failed"
            self.footer.set_state(dirty=self._session.is_dirty, valid=False, state="failed")
            self.footer.set_status(self._feedback or next(iter(errors.values())))
            return
        state = self._save_state if self._save_state in {"success", "failed"} and not self._session.is_dirty else None
        self.footer.set_state(dirty=self._session.is_dirty, valid=True, state=state)
        if state is None:
            self.footer.set_status(self._feedback or ("有未保存修改" if self._session.is_dirty else ""))

    def open(self) -> None:  # noqa: A003
        self._session = SettingsEditSession.open(self.bridge.read_snapshot())
        self._feedback = ""
        self._save_state = "clean"
        self._pending_action = ""
        self.confirmation_bar.hide()
        self._hide_confirmation()
        self.set_category("general")
        self._sync_controls()
        self._refresh_state()
        parent = self.parentWidget()
        self.sync_geometry(parent.rect() if parent is not None else None)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _path_value_changed(self, key: str, value: str) -> None:
        self._value_changed(key, value)
        if key == "immersive_background_custom_path" and not str(value or "").strip():
            self._set_immersive_background_mode("cover")

    def _set_immersive_background_mode(self, value: str) -> None:
        control = self._controls.get("immersive_background_mode")
        if not isinstance(control, ThemedComboBox):
            return
        index = control.findData(value)
        if index < 0:
            return
        with QSignalBlocker(control):
            control.setCurrentIndex(index)
        self._value_changed("immersive_background_mode", value)

    def open_category(self, category: str) -> None:
        """Open this cached overlay and select one existing settings category."""

        self.open()
        self.set_category(category)

    def request_close(self) -> None:
        if self.is_dirty:
            self._show_confirmation(
                "放弃未保存修改？",
                "当前修改尚未保存。选择放弃后，预览中的主题和显示设置也会恢复。",
                danger=False,
            )
            return
        self._hide_overlay()

    def _show_confirmation(self, title: str, message: str, *, danger: bool) -> None:
        self.confirm_scrim.setGeometry(self.rect())
        self.confirm_scrim.show()
        self.confirm_scrim.raise_()
        self.confirm_dialog.set_content(title, message, danger=danger)
        self.confirm_dialog.adjustSize()
        dialog_rect = self.dialog.geometry()
        width = min(max(360, self.confirm_dialog.sizeHint().width()), max(360, dialog_rect.width() - 48))
        height = self.confirm_dialog.sizeHint().height()
        self.confirm_dialog.setGeometry(
            dialog_rect.x() + (dialog_rect.width() - width) // 2,
            dialog_rect.y() + (dialog_rect.height() - height) // 2,
            width,
            height,
        )
        self.confirm_dialog.show()
        self.confirm_dialog.raise_()
        self.confirm_dialog.setFocus()

    def _hide_confirmation(self) -> None:
        self._pending_action = ""
        self.confirmation_bar.hide()
        self.confirm_scrim.hide()
        self.confirm_dialog.hide()

    def save(self) -> bool:
        if self._session is None:
            return False
        self._session.validate(self.bridge.validate)
        if not self._session.is_valid:
            self._save_state = "failed"
            self.footer.set_state(
                dirty=self._session.is_dirty,
                valid=False,
                state="failed",
            )
            self._set_feedback(next(iter(self._session.validation_errors.values())))
            return False
        self._save_state = "saving"
        self.footer.set_state_message("saving", "正在保存…")
        cache_directory_changed = (
            str(self._session.original_snapshot.get("cache_directory", "") or "")
            != str(self._session.working_snapshot.get("cache_directory", "") or "")
        )
        try:
            saved = self.bridge.save_snapshot(self._session.working_snapshot)
        except SettingsBridgeError as error:
            self._save_state = "failed"
            self.footer.set_state(dirty=True, valid=True, state="failed")
            self._set_feedback(str(error))
            return False
        self._session.replace_after_save(saved)
        if self._preview_callback is not None:
            self._preview_callback(saved.to_dict())
        self.saved.emit(saved)
        self._save_state = "success"
        self._feedback = (
            "设置已保存；缓存位置将在重启后生效"
            if cache_directory_changed
            else "设置已保存"
        )
        self.footer.set_state_message("success", self._feedback)
        QTimer.singleShot(1800, self._clear_success)
        return True

    def _clear_success(self) -> None:
        if self._session is not None and not self._session.is_dirty and self.isVisible():
            self._save_state = "clean"
            self._feedback = ""
            self._refresh_state()

    def save_and_close(self) -> None:
        if self.save():
            self._hide_overlay()

    def cancel_and_close(self) -> None:
        if self._session is None:
            self._hide_overlay()
            return
        original = self._session.cancel()
        if self._preview_callback is not None:
            self._preview_callback(original.to_dict())
        self._hide_overlay()

    def _hide_overlay(self) -> None:
        self._hide_confirmation()
        self.confirmation_bar.hide()
        self.hide()
        self.closed.emit()

    def set_category(self, category: str) -> None:
        key = str(category)
        if key not in self._category_pages:
            return
        self._current_category = key
        self.sidebar.set_current(key)
        self.content_stack.setCurrentWidget(self._category_pages[key])
        self.subtitle_label.setText(category_for_key(key).title)

    def set_appearance_mode(self, mode: str) -> None:
        """Route the shell's quick theme action through this edit session."""

        control = self._controls.get("appearance_mode")
        if not isinstance(control, ThemedComboBox):
            return
        index = control.findData(str(mode))
        if index >= 0:
            control.setCurrentIndex(index)

    def set_responsive_reference_width(self, width: int) -> None:
        compact = int(width) < 1000
        self.sidebar.set_compact(compact)
        for row in self._rows:
            row.set_compact(compact)
        online_sources_page = self._category_pages.get("online_sources")
        if online_sources_page is not None and hasattr(
            online_sources_page, "set_responsive_reference_width"
        ):
            online_sources_page.set_responsive_reference_width(int(width))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self.confirm_dialog.isVisible() or self.confirm_scrim.isVisible():
                self._hide_confirmation()
            else:
                self.request_close()
            event.accept()
            return
        super().keyPressEvent(event)

    def sync_geometry(self, parent_rect) -> None:
        if parent_rect is None:
            return
        self.setGeometry(parent_rect)
        self.dim_layer.setGeometry(self.rect())
        self.dialog.setGeometry(self._dialog_geometry())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.dim_layer.setGeometry(self.rect())
        self.dialog.setGeometry(self._dialog_geometry())
        if self.confirm_scrim.isVisible():
            self._show_confirmation(
                self.confirm_dialog.title_label.text(),
                self.confirm_dialog.message_label.text(),
                danger=self.confirm_dialog.confirm_button.isVisible(),
            )

    def _dialog_geometry(self):
        """Keep the fixed header/footer inside the body at narrow heights."""

        margin = 24 if self.width() < 1000 else 36
        width = min(920, max(820, self.width() - margin * 2))
        available_height = max(0, self.height() - margin * 2)
        height = min(740, max(360, available_height))
        return QRect(
            (self.width() - width) // 2,
            (self.height() - height) // 2,
            width,
            height,
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        overlay_color = "rgba(31, 48, 41, 62)" if theme.mode == "light" else "rgba(0, 0, 0, 110)"
        self.setStyleSheet(
            f"QWidget#settingsOverlay {{ background: transparent; }} "
            f"QFrame#settingsDimLayer {{ background: {overlay_color}; }} "
            f"QFrame#settingsConfirmScrim {{ background: rgba(0, 0, 0, 78); }}"
        )
        self.dialog.setStyleSheet(
            f"QFrame#settingsDialog {{ background: {c.content_background}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QFrame#settingsConfirmationBar {{ background: {c.selected_background}; border-top: 1px solid {c.border}; }}"
            f"QPushButton {{ min-height: {theme.metrics.control_height - 2}px; padding: 0 12px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.input_background}; color: {c.primary_text}; }}"
            f"QPushButton:hover {{ background: {c.hover_background}; }}"
        )
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.page_title}px; font-weight: 700; color: {c.primary_text};")
        self.subtitle_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {c.secondary_text};")
        self.header_icon.setIcon(fluent_settings_icon("general", theme, "selected", 20))
        self.header_icon.setIconSize(QSize(20, 20))
        self.header_icon.setStyleSheet(
            "QToolButton#settingsHeaderIcon { border: 0; background: transparent; padding: 0; }"
        )
        self.close_button.setIcon(fluent_settings_interactive_icon("dismiss", theme, 18))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setStyleSheet(
            f"QToolButton#settingsCloseButton {{ min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; border: 0; border-radius: 9px; background: transparent; }} "
            f"QToolButton#settingsCloseButton:hover {{ background: rgba(255,255,255,18); }} "
            f"QToolButton#settingsCloseButton:pressed {{ background: rgba(255,255,255,28); }} "
            f"QToolButton#settingsCloseButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {c.focus_ring}; background: transparent; }}"
        )
        self.sidebar.set_theme(theme)
        self.footer.set_theme(theme)
        self.confirm_dialog.set_theme(theme)
        for section in self._sections:
            section.set_theme(theme)
        for row in self._rows:
            row.set_theme(theme)
        for control in self._controls.values():
            if hasattr(control, "set_theme"):
                control.set_theme(theme)
        for path_control in self._path_controls.values():
            path_control.picker.set_theme(theme)
        for control in self._aux_controls:
            if hasattr(control, "set_theme"):
                control.set_theme(theme)
        if hasattr(self, "update_status"):
            self.update_status.setStyleSheet(
                f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {c.secondary_text};"
            )
        if hasattr(self, "cache_status"):
            self.cache_status.setStyleSheet(
                f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {c.secondary_text};"
            )
        if hasattr(self, "about_changelog"):
            self.about_changelog.setStyleSheet(
                f"QPlainTextEdit#settingsAboutChangelog {{ min-height: 260px; padding: 12px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_md}px; background: {c.surface_secondary}; color: {c.primary_text}; selection-background-color: {c.accent}; selection-color: {c.content_background}; font-size: {theme.fonts.body}px; font-weight: 400; }}"
            )
        for page in self._category_pages.values():
            if hasattr(page, "set_theme"):
                page.set_theme(theme)
            else:
                page.setStyleSheet(f"background: {c.content_background};")
        for scroll in self._category_scrolls.values():
            scroll.setStyleSheet(f"QScrollArea {{ border: 0; background: {c.content_background}; }} QAbstractScrollArea::viewport {{ background: {c.content_background}; }} QScrollBar:vertical {{ width: 9px; background: transparent; }} QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 4px; background: {c.border_strong}; }} QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}")
