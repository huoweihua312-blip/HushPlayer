"""Modal Settings Overlay for the formal UI V2 shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QMessageBox,
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
)
from app.core.version import APP_NAME, APP_VERSION
from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES, category_for_key
from app.ui_v2.models.settings_edit_session import SettingsEditSession
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.theme.icons import fluent_settings_icon, fluent_settings_interactive_icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import (
    SettingsControlFactory,
    SliderSpinControl,
    ThemedComboBox,
)
from app.ui_v2.widgets.settings_footer import SettingsFooter
from app.ui_v2.widgets.settings_row import SettingsRow
from app.ui_v2.widgets.settings_section import SettingsSection
from app.ui_v2.widgets.settings_sidebar import SettingsSidebar


@dataclass(slots=True)
class _PathControl:
    widget: QWidget
    input: QLineEdit
    browse: QPushButton


class SettingsOverlay(QWidget):
    """One cached modal overlay with a fresh edit session per open."""

    closed = Signal()
    saved = Signal(object)

    def __init__(
        self,
        bridge: LegacySettingsBridge,
        theme: Theme,
        *,
        preview_callback: Callable[[dict[str, Any]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self._theme = theme
        self._preview_callback = preview_callback
        self._session: SettingsEditSession | None = None
        self._controls: dict[str, QWidget] = {}
        self._path_controls: dict[str, _PathControl] = {}
        self._category_pages: dict[str, QWidget] = {}
        self._category_scrolls: dict[str, QScrollArea] = {}
        self._current_category = "general"
        self._feedback = ""
        self._last_parent_rect = None
        self.setObjectName("settingsOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
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
        self.dim_layer = QFrame(self)
        self.dim_layer.setObjectName("settingsDimLayer")
        self.dialog = QFrame(self)
        self.dialog.setObjectName("settingsDialog")

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
        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addLayout(body, 1)
        layout.addWidget(self.confirmation_bar)
        layout.addWidget(self.footer)

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

    def _wire_state(self) -> None:
        self.sidebar.category_requested.connect(self.set_category)
        self.close_button.clicked.connect(self.request_close)
        self.footer.cancel_requested.connect(self.cancel_and_close)
        self.footer.save_requested.connect(self.save_and_close)
        self.confirm_save.clicked.connect(self.save_and_close)
        self.confirm_discard.clicked.connect(self.cancel_and_close)
        self.confirm_cancel.clicked.connect(self._hide_confirmation)

    def _section(self, title: str, description: str) -> SettingsSection:
        return SettingsSection(title, description, self._theme, self)

    def _toggle_row(self, key: str, title: str, description: str) -> SettingsRow:
        control = SettingsControlFactory.switch(False, self._theme, self)
        self._bind_control(key, control, lambda: bool(control.isChecked()), control.setChecked, control.toggled)
        return SettingsRow(key, title, description, control, self._theme, self)

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
        return SettingsRow(key, title, description, control, self._theme, self)

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
        return SettingsRow(key, title, description, control, self._theme, self)

    def _path_row(self, key: str, title: str, description: str) -> SettingsRow:
        container = QWidget(self)
        edit = QLineEdit(container)
        edit.setObjectName(f"settingsPath_{key.replace('.', '_')}")
        edit.setPlaceholderText("未选择")
        browse = QPushButton("选择", container)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit, 1)
        layout.addWidget(browse)
        path_control = _PathControl(container, edit, browse)
        self._path_controls[key] = path_control
        edit.textChanged.connect(lambda value, path=key: self._value_changed(path, value))
        browse.clicked.connect(lambda _checked=False, path=key: self._choose_path(path))
        self._controls[key] = container
        return SettingsRow(key, title, description, container, self._theme, self)

    def _build_general(self, layout: QVBoxLayout) -> None:
        section = self._section("启动与窗口", "保留现有 HushPlayer 启动和窗口行为。")
        section.add_row(self._toggle_row("auto_scan_music_folders_on_startup", "启动时自动扫描这些文件夹", "启动时扫描已保存的音乐文件夹。"))
        section.add_row(self._toggle_row("floating_lyrics_auto_open", "启动时自动打开桌面歌词", "播放启动时自动打开现有桌面歌词窗口。"))
        layout.addWidget(section)

    def _build_appearance(self, layout: QVBoxLayout) -> None:
        section = self._section("主题", "沿用当前正式 Theme，不创建第二套壳层。")
        section.add_row(self._combo_row("appearance_mode", "主题", "切换后立即应用，保存后写入现有设置文件。", (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark"))))
        layout.addWidget(section)

    def _build_playback(self, layout: QVBoxLayout) -> None:
        section = self._section("播放恢复", "沿用现有播放会话恢复语义。")
        section.add_row(self._toggle_row("restore_last_playback", "启动时恢复上次播放的歌曲和进度", "启动时读取现有播放会话。"))
        layout.addWidget(section)

    def _build_lyrics(self, layout: QVBoxLayout) -> None:
        immersive = self._section("沉浸歌词", "保留现有沉浸歌词设置，不改变 Lyrics 或沉浸页面结构。")
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

        floating = self._section("桌面歌词", "调整现有桌面歌词窗口的默认外观。")
        floating.add_row(self._combo_row("floating_lyrics_color", "默认歌词颜色", "保存后应用到桌面歌词窗口。", (("白色", "white"), ("黑色", "black"), ("黄色", "yellow"), ("蓝色", "blue"), ("绿色", "green"), ("粉色", "pink"), ("紫色", "purple"))))
        floating.add_row(self._slider_row("floating_lyrics_opacity", "默认不透明度", "保留现有 20% 到 100% 范围。", 20, 100, "%"))
        floating.add_row(self._slider_row("floating_lyrics_font_size", "默认字号", "保留现有 22 到 84 px 范围。", 22, 84, " px"))
        floating.add_row(self._slider_row("floating_lyrics_width", "默认宽度", "保留现有 420 到 1600 px 范围。", 420, 1600, " px"))
        layout.addWidget(floating)

    def _build_library(self, layout: QVBoxLayout) -> None:
        section = self._section("音乐文件夹", "修改后保存到现有扫描设置；手动扫描仍是独立操作。")
        self.folder_list = QListWidget(self)
        self.folder_list.setObjectName("settingsFolderList")
        self.folder_list.setMinimumHeight(100)
        section.add_widget(self.folder_list)
        buttons = QHBoxLayout()
        add = QPushButton("添加文件夹", self)
        remove = QPushButton("移除选中", self)
        scan = QPushButton("手动重新扫描", self)
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
        section = self._section("缓存", "缓存命令不参与 Save/Dirty；仅调用现有服务。")
        self.cache_status = QLabel("缓存统计由正式缓存服务提供。", self)
        self.cache_status.setWordWrap(True)
        section.add_widget(self.cache_status)
        for text, action in (
            ("清理封面 / 歌词失败缓存", "clear_missing_cache"),
            ("打开音频缓存目录", "open_audio_cache_directory"),
            ("清理未完成音频缓存", "clear_incomplete_audio_cache"),
            ("清理全部音频缓存", "clear_all_audio_cache"),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(lambda _checked=False, name=action: self._run_action(name))
            button.setEnabled(self.bridge.has_action(action))
            section.add_widget(button)
        layout.addWidget(section)

    def _build_updates(self, layout: QVBoxLayout) -> None:
        section = self._section("应用更新", "更新检查沿用现有 AppUpdateService。")
        section.add_row(self._toggle_row("auto_check_updates_on_startup", "启动后自动检查更新", "下次启动时按现有服务规则检查。"))
        section.add_row(self._combo_row("update_check_delay_seconds", "启动后延迟", "保留现有 5 到 300 秒范围。", (("5 秒", "5"), ("15 秒", "15"), ("30 秒", "30"), ("60 秒", "60"))))
        check = QPushButton("检查更新", self)
        check.clicked.connect(lambda: self._run_action("check_updates"))
        check.setEnabled(self.bridge.has_action("check_updates"))
        section.add_widget(check)
        layout.addWidget(section)

    def _build_about(self, layout: QVBoxLayout) -> None:
        section = self._section("关于 HushPlayer", "当前 HushPlayer 的版本与应用信息。")
        app_name = QLabel(APP_NAME, self)
        app_name.setObjectName("settingsAboutAppName")
        app_name.setWordWrap(True)
        version = QLabel(f"版本 {APP_VERSION}", self)
        version.setObjectName("settingsAboutVersion")
        version.setWordWrap(True)
        section.add_widget(app_name)
        section.add_widget(version)
        layout.addWidget(section)

    def _bind_control(self, key: str, control: QWidget, getter, setter, signal) -> None:
        self._controls[key] = control
        signal.connect(lambda *_args, path=key, read=getter: self._value_changed(path, read()))

    def _value_changed(self, key: str, value: Any) -> None:
        if self._session is None:
            return
        if key == "update_check_delay_seconds":
            value = int(value)
        changed = self._session.set(key, value)
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
                with QSignalBlocker(path_control.input):
                    path_control.input.setText(str(value or ""))
                continue
            with QSignalBlocker(control):
                if isinstance(control, QLineEdit):
                    control.setText(str(value or ""))
                elif isinstance(control, ThemedComboBox):
                    control.setCurrentIndex(max(0, control.findData(str(value))))
                elif isinstance(control, SliderSpinControl):
                    control.set_value(int(value))
                elif hasattr(control, "setChecked"):
                    control.setChecked(bool(value))
        if hasattr(self, "folder_list"):
            self.folder_list.clear()
            for folder in self.bridge.value(self._session.working_snapshot, "music_scan_folders") or []:
                self.folder_list.addItem(str(folder))

    def _choose_path(self, key: str) -> None:
        selected = QFileDialog.getOpenFileName(self, "选择背景图片", str(Path.home()))[0]
        if selected:
            self._path_controls[key].input.setText(selected)

    def _add_folder(self) -> None:
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
            decision = QMessageBox.question(
                self,
                "确认清理缓存",
                "此操作会删除本地缓存文件，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if decision != QMessageBox.StandardButton.Yes:
                return
        try:
            result = self.bridge.run_action(name)
            if isinstance(result, str):
                self._set_feedback(result)
            elif isinstance(result, dict):
                self.cache_status.setText("缓存操作已完成。")
            else:
                self._set_feedback("操作已发送到现有服务。")
        except SettingsBridgeError as error:
            self._set_feedback(str(error))

    def _set_feedback(self, text: str) -> None:
        self._feedback = str(text or "")
        self.footer.set_status(self._feedback)

    def _refresh_state(self) -> None:
        if self._session is None:
            self.footer.set_state(dirty=False, valid=False)
            return
        errors = self._session.validate(self.bridge.validate)
        self.footer.set_state(dirty=self._session.is_dirty, valid=not errors)
        self.footer.set_status(self._feedback or ("有未保存修改" if self._session.is_dirty else ""))

    def open(self) -> None:  # noqa: A003
        self._session = SettingsEditSession.open(self.bridge.read_snapshot())
        self._feedback = ""
        self.confirmation_bar.hide()
        self.set_category("general")
        self._sync_controls()
        self._refresh_state()
        self.show()
        self.raise_()
        self.setFocus()
        self.sync_geometry(self.parentWidget().rect() if self.parentWidget() is not None else None)

    def open_category(self, category: str) -> None:
        """Open this cached overlay and select one existing settings category."""

        self.open()
        self.set_category(category)

    def request_close(self) -> None:
        if self.is_dirty:
            self.confirmation_bar.show()
            return
        self._hide_overlay()

    def _hide_confirmation(self) -> None:
        self.confirmation_bar.hide()

    def save_and_close(self) -> None:
        if self._session is None:
            return
        self._session.validate(self.bridge.validate)
        if not self._session.is_valid:
            self._set_feedback(next(iter(self._session.validation_errors.values())))
            return
        try:
            saved = self.bridge.save_snapshot(self._session.working_snapshot)
        except SettingsBridgeError as error:
            self._set_feedback(str(error))
            return
        self._session.replace_after_save(saved)
        if self._preview_callback is not None:
            self._preview_callback(saved.to_dict())
        self.saved.emit(saved)
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

    def set_responsive_reference_width(self, width: int) -> None:
        self.sidebar.set_compact(int(width) < 1000)

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

    def _dialog_geometry(self):
        """Keep the fixed header/footer inside the body at narrow heights."""

        margin = 24 if self.width() < 1000 else 36
        width = min(1020, max(820, self.width() - margin * 2))
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
        self.setStyleSheet(f"QWidget#settingsOverlay {{ background: transparent; }} QFrame#settingsDimLayer {{ background: rgba(0, 0, 0, 150); }}")
        self.dialog.setStyleSheet(
            f"QFrame#settingsDialog {{ background: {c.content_background}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QFrame#settingsConfirmationBar {{ background: {c.selected_background}; border-top: 1px solid {c.border}; }}"
            f"QPushButton {{ min-height: {theme.metrics.control_height - 2}px; padding: 0 12px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.input_background}; color: {c.primary_text}; }}"
            f"QPushButton:hover {{ background: {c.hover_background}; }}"
        )
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.page_title}px; font-weight: 650; color: {c.primary_text};")
        self.subtitle_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {c.secondary_text};")
        self.close_button.setIcon(fluent_settings_interactive_icon("dismiss", theme, 18))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setStyleSheet(
            f"QToolButton#settingsCloseButton {{ min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; border: 0; border-radius: 9px; background: transparent; }} "
            f"QToolButton#settingsCloseButton:hover {{ background: rgba(255,255,255,18); }} "
            f"QToolButton#settingsCloseButton:pressed {{ background: rgba(255,255,255,28); }} "
            f"QToolButton#settingsCloseButton:focus {{ border: 1px solid {c.focus_ring}; background: transparent; }}"
        )
        self.sidebar.set_theme(theme)
        self.footer.set_theme(theme)
        for control in self._controls.values():
            if hasattr(control, "set_theme"):
                control.set_theme(theme)
        for page in self._category_pages.values():
            page.setStyleSheet(f"background: {c.content_background};")
        for scroll in self._category_scrolls.values():
            scroll.setStyleSheet(f"QScrollArea {{ border: 0; background: {c.content_background}; }} QAbstractScrollArea::viewport {{ background: {c.content_background}; }} QScrollBar:vertical {{ width: 9px; background: transparent; }} QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 4px; background: {c.border_strong}; }} QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}")
