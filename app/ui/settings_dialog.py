"""Settings dialog for HushPlayer"""
from __future__ import annotations
from pathlib import Path
from dataclasses import replace
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.ui.design_system import ACTIVE_THEME_TOKENS
from app.ui.immersive_appearance import ImmersiveAppearanceConfig
from app.ui.theme_manager import (
    apply_dialog_style,
    normalize_appearance_mode,
    
)
from app.core.version import APP_VERSION

def normalize_update_check_delay_seconds(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return 15
    return max(5, min(300, seconds))



class SettingsDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("HushPlayer 设置")
        self.setObjectName("settingsDialog")
        self.setMinimumSize(900, 600)

        settings = self.main_window.get_hush_settings()
        self.immersive_appearance_config = ImmersiveAppearanceConfig.from_settings(
            settings
        )

        # Main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left navigation panel
        nav_panel = QFrame()
        nav_panel.setObjectName("settingsNavPanel")
        nav_panel.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(16, 20, 8, 20)
        nav_layout.setSpacing(4)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("settingsNavList")

        categories = [
            "常规",
            "外观",
            "播放",
            "歌词",
            "音乐库",
            "缓存",
            "更新",
            "关于"
        ]

        for cat in categories:
            item = QListWidgetItem(cat)
            self.nav_list.addItem(item)

        nav_layout.addWidget(self.nav_list)
        main_layout.addWidget(nav_panel)

        # Right content panel
        content_panel = QFrame()
        content_panel.setObjectName("settingsContentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Header
        header_frame = QFrame()
        header_frame.setObjectName("settingsContentHeader")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(32, 24, 32, 16)
        header_layout.setSpacing(0)

        self.content_title = QLabel("常规")
        self.content_title.setObjectName("settingsContentTitle")
        header_layout.addWidget(self.content_title)
        content_layout.addWidget(header_frame)

        # Scrollable content
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("settingsScrollArea")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.settings_scroll_content = QWidget()
        self.settings_content_layout = QVBoxLayout(self.settings_scroll_content)
        self.settings_content_layout.setContentsMargins(32, 16, 32, 32)
        self.settings_content_layout.setSpacing(24)

        # Create all category pages
        self.page_general = QWidget()
        self.page_appearance = QWidget()
        self.page_playback = QWidget()
        self.page_lyrics = QWidget()
        self.page_library = QWidget()
        self.page_cache = QWidget()
        self.page_updates = QWidget()
        self.page_about = QWidget()

        # Add pages to content layout (manual show/hide)
        self.pages = [
            self.page_general,
            self.page_appearance,
            self.page_playback,
            self.page_lyrics,
            self.page_library,
            self.page_cache,
            self.page_updates,
            self.page_about,
        ]

        for page in self.pages:
            page.setVisible(False)
            self.settings_content_layout.addWidget(page)

        self.pages[0].setVisible(True)
        self.settings_content_layout.addStretch(1)

        self.settings_scroll.setWidget(self.settings_scroll_content)
        content_layout.addWidget(self.settings_scroll, 1)

        # Footer with buttons
        footer_frame = QFrame()
        footer_frame.setObjectName("settingsContentFooter")
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(32, 12, 32, 20)
        footer_layout.setSpacing(12)
        footer_layout.addStretch(1)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("settingsSecondaryButton")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("settingsPrimaryButton")
        save_btn.clicked.connect(self.save_settings)

        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)
        content_layout.addWidget(footer_frame)

        main_layout.addWidget(content_panel, 1)

        # Initialize all controls in pages
        self._init_general_page(settings)
        self._init_appearance_page(settings)
        self._init_playback_page(settings)
        self._init_lyrics_page(settings)
        self._init_library_page(settings)
        self._init_cache_page(settings)
        self._init_updates_page(settings)
        self._init_about_page()

        # Connect navigation
        self.nav_list.currentRowChanged.connect(self._on_category_changed)

        # Connect signals
        self.update_service = getattr(self.main_window, "update_service", None)
        if self.update_service is not None:
            self.update_service.checkStarted.connect(self.on_update_check_started)
            self.update_service.checkCompleted.connect(self.on_update_check_completed)

        self.main_window.online_audio_cache.statisticsChanged.connect(
            self.refresh_audio_cache_status
        )
        self.main_window.theme_manager.themeChanged.connect(
            lambda _mode: self.apply_style()
        )

        # Wheel passthrough for controls
        self._settings_wheel_passthrough_controls = (
            self.alpha_slider,
            self.floating_color_combo,
            self.floating_opacity_slider,
            self.floating_font_slider,
            self.floating_width_slider,
            self.music_scan_import_mode_combo,
        )
        for control in self._settings_wheel_passthrough_controls:
            control.installEventFilter(self)

        self.nav_list.setCurrentRow(0)
        self.refresh_audio_cache_status()
        self.apply_style()

    def _on_category_changed(self, index: int) -> None:
        """Handle category navigation"""
        if index < 0 or index >= len(self.pages):
            return

        # Hide all pages
        for page in self.pages:
            page.setVisible(False)

        # Show selected page
        self.pages[index].setVisible(True)

        # Update title
        item = self.nav_list.item(index)
        if item:
            self.content_title.setText(item.text())

    def _init_general_page(self, settings: dict) -> None:
        """Initialize general settings page"""
        layout = QVBoxLayout(self.page_general)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # Startup behavior
        section_title = QLabel("启动行为")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        self.auto_scan_checkbox = QCheckBox("启动时自动扫描这些文件夹")
        self.auto_scan_checkbox.setChecked(bool(settings.get("auto_scan_music_folders_on_startup", True)))
        layout.addWidget(self.auto_scan_checkbox)

        self.floating_auto_open_checkbox = QCheckBox("启动时自动打开桌面歌词")
        self.floating_auto_open_checkbox.setChecked(bool(settings.get("floating_lyrics_auto_open", False)))
        layout.addWidget(self.floating_auto_open_checkbox)

    def _init_appearance_page(self, settings: dict) -> None:
        """Initialize appearance settings page"""
        layout = QVBoxLayout(self.page_appearance)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        section_title = QLabel("主题")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        hint = QLabel("切换后立即应用到已打开的窗口。跟随系统会使用 Windows 当前外观。")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.appearance_mode_combo = QComboBox()
        self.appearance_mode_combo.addItem("跟随系统", "system")
        self.appearance_mode_combo.addItem("浅色", "light")
        self.appearance_mode_combo.addItem("深色", "dark")
        appearance_mode = normalize_appearance_mode(settings.get("appearance_mode", "dark"))
        appearance_index = self.appearance_mode_combo.findData(appearance_mode)
        self.appearance_mode_combo.setCurrentIndex(max(0, appearance_index))
        self.appearance_mode_combo.currentIndexChanged.connect(self.apply_appearance_mode)
        layout.addWidget(self.appearance_mode_combo)

    def _init_playback_page(self, settings: dict) -> None:
        """Initialize playback settings page"""
        layout = QVBoxLayout(self.page_playback)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        section_title = QLabel("播放恢复")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        self.restore_checkbox = QCheckBox("启动时恢复上次播放的歌曲和进度")
        self.restore_checkbox.setChecked(bool(settings.get("restore_last_playback", True)))
        layout.addWidget(self.restore_checkbox)

    def _init_lyrics_page(self, settings: dict) -> None:
        """Initialize lyrics settings page"""
        layout = QVBoxLayout(self.page_lyrics)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # Immersive lyrics section
        immersive_title = QLabel("沉浸歌词")
        immersive_title.setObjectName("settingsSectionTitle")
        layout.addWidget(immersive_title)

        layout.addWidget(QLabel("背景模式"))
        self.immersive_background_mode_combo = QComboBox()
        self.immersive_background_mode_combo.addItem("封面模糊", "cover")
        self.immersive_background_mode_combo.addItem("纯色背景", "default")
        self.immersive_background_mode_combo.addItem("半透明背景", "translucent")
        self.immersive_background_mode_combo.addItem("自定义图片", "custom")
        immersive_mode_index = self.immersive_background_mode_combo.findData(
            self.immersive_appearance_config.background_mode
        )
        self.immersive_background_mode_combo.setCurrentIndex(max(0, immersive_mode_index))
        layout.addWidget(self.immersive_background_mode_combo)

        self.auto_hide_checkbox = QCheckBox("默认自动隐藏沉浸歌词 UI")
        self.auto_hide_checkbox.setChecked(bool(settings.get("immersive_auto_hide_ui", True)))
        layout.addWidget(self.auto_hide_checkbox)

        # Alpha slider
        alpha_row = QHBoxLayout()
        alpha_row.setSpacing(12)
        self.alpha_label = QLabel()
        self.alpha_label.setObjectName("settingsValueLabel")
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 90)
        self.alpha_slider.setValue(self.immersive_appearance_config.darkness)
        self.alpha_slider.valueChanged.connect(self.update_alpha_label)
        alpha_row.addWidget(QLabel("背景暗度"))
        alpha_row.addWidget(self.alpha_slider, 1)
        alpha_row.addWidget(self.alpha_label)
        layout.addLayout(alpha_row)
        self.update_alpha_label(self.alpha_slider.value())

        immersive_hint = QLabel("自定义图片、模糊、透明度、填充方式和歌词字号可在沉浸歌词右上角「显示设置」中调整。")
        immersive_hint.setWordWrap(True)
        immersive_hint.setObjectName("settingsHint")
        layout.addWidget(immersive_hint)

        # Spacing between sections
        layout.addSpacing(24)

        # Floating lyrics section
        floating_title = QLabel("桌面歌词")
        floating_title.setObjectName("settingsSectionTitle")
        layout.addWidget(floating_title)

        self.floating_color_combo = QComboBox()
        self.floating_color_combo.addItem("白色", "white")
        self.floating_color_combo.addItem("黑色", "black")
        self.floating_color_combo.addItem("黄色", "yellow")
        self.floating_color_combo.addItem("蓝色", "blue")
        self.floating_color_combo.addItem("绿色", "green")
        self.floating_color_combo.addItem("粉色", "pink")
        self.floating_color_combo.addItem("紫色", "purple")
        current_floating_color = str(settings.get("floating_lyrics_color", "white"))
        color_index = self.floating_color_combo.findData(current_floating_color)
        if color_index >= 0:
            self.floating_color_combo.setCurrentIndex(color_index)

        color_row = QHBoxLayout()
        color_row.setSpacing(12)
        color_row.addWidget(QLabel("默认歌词颜色"))
        color_row.addWidget(self.floating_color_combo, 1)
        layout.addLayout(color_row)

        # Opacity slider
        self.floating_opacity_label = QLabel()
        self.floating_opacity_label.setObjectName("settingsValueLabel")
        self.floating_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_opacity_slider.setRange(20, 100)
        self.floating_opacity_slider.setValue(int(settings.get("floating_lyrics_opacity", 100)))
        self.floating_opacity_slider.valueChanged.connect(self.update_floating_opacity_label)
        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(12)
        opacity_row.addWidget(QLabel("默认不透明度"))
        opacity_row.addWidget(self.floating_opacity_slider, 1)
        opacity_row.addWidget(self.floating_opacity_label)
        layout.addLayout(opacity_row)
        self.update_floating_opacity_label(self.floating_opacity_slider.value())

        # Font size slider
        self.floating_font_label = QLabel()
        self.floating_font_label.setObjectName("settingsValueLabel")
        self.floating_font_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_font_slider.setRange(22, 84)
        self.floating_font_slider.setValue(int(settings.get("floating_lyrics_font_size", 42)))
        self.floating_font_slider.valueChanged.connect(self.update_floating_font_label)
        font_row = QHBoxLayout()
        font_row.setSpacing(12)
        font_row.addWidget(QLabel("默认字号"))
        font_row.addWidget(self.floating_font_slider, 1)
        font_row.addWidget(self.floating_font_label)
        layout.addLayout(font_row)
        self.update_floating_font_label(self.floating_font_slider.value())

        # Width slider
        self.floating_width_label = QLabel()
        self.floating_width_label.setObjectName("settingsValueLabel")
        self.floating_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_width_slider.setRange(420, 1600)
        self.floating_width_slider.setValue(int(settings.get("floating_lyrics_width", 980)))
        self.floating_width_slider.valueChanged.connect(self.update_floating_width_label)
        width_row = QHBoxLayout()
        width_row.setSpacing(12)
        width_row.addWidget(QLabel("默认宽度"))
        width_row.addWidget(self.floating_width_slider, 1)
        width_row.addWidget(self.floating_width_label)
        layout.addLayout(width_row)
        self.update_floating_width_label(self.floating_width_slider.value())

        # Reset button
        reset_btn = QPushButton("重置桌面歌词位置")
        reset_btn.setObjectName("settingsSecondaryButton")
        reset_btn.clicked.connect(self.reset_floating_lyrics_position)
        layout.addWidget(reset_btn)

    def _init_library_page(self, settings: dict) -> None:
        """Initialize music library settings page"""
        layout = QVBoxLayout(self.page_library)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        section_title = QLabel("音乐文件夹 / 网盘同步目录")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        hint = QLabel("可以添加百度网盘同步空间、夸克网盘下载目录、OneDrive、NAS 或本地音乐文件夹。如果播放卡顿，建议在网盘客户端中把音乐文件设为本地可用。")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.music_scan_folder_list = QListWidget()
        self.music_scan_folder_list.setObjectName("settingsFolderList")
        self.music_scan_folder_list.setMinimumHeight(110)
        for folder in settings.get("music_scan_folders", []):
            if isinstance(folder, str) and folder.strip():
                self.music_scan_folder_list.addItem(folder.strip())
        layout.addWidget(self.music_scan_folder_list)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        add_btn = QPushButton("添加文件夹")
        add_btn.setObjectName("settingsSecondaryButton")
        add_btn.clicked.connect(self.add_music_scan_folder)

        remove_btn = QPushButton("移除选中文件夹")
        remove_btn.setObjectName("settingsSecondaryButton")
        remove_btn.clicked.connect(self.remove_music_scan_folder)

        scan_btn = QPushButton("手动重新扫描")
        scan_btn.setObjectName("settingsSecondaryButton")
        scan_btn.clicked.connect(self.scan_music_folders_now)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(scan_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Import mode
        import_row = QHBoxLayout()
        import_row.setSpacing(12)
        self.music_scan_import_mode_combo = QComboBox()
        self.music_scan_import_mode_combo.addItem("进入待导入列表，手动确认", "pending")
        self.music_scan_import_mode_combo.addItem("自动加入音乐库", "auto")
        current_import_mode = str(settings.get("music_scan_import_mode", "pending"))
        import_mode_index = self.music_scan_import_mode_combo.findData(current_import_mode)
        if import_mode_index >= 0:
            self.music_scan_import_mode_combo.setCurrentIndex(import_mode_index)
        import_row.addWidget(QLabel("扫描新音乐后的处理方式"))
        import_row.addWidget(self.music_scan_import_mode_combo, 1)
        layout.addLayout(import_row)

        cloud_hint = QLabel("推荐用百度网盘客户端的同步空间，或夸克网盘的下载目录，把音乐文件同步/下载到本地后由 HushPlayer 自动扫描。这样最稳定，也不需要登录网盘 API。")
        cloud_hint.setObjectName("settingsHint")
        cloud_hint.setWordWrap(True)
        layout.addWidget(cloud_hint)

    def _init_cache_page(self, settings: dict) -> None:
        """Initialize cache settings page"""
        layout = QVBoxLayout(self.page_cache)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # Metadata cache section
        metadata_title = QLabel("元数据缓存")
        metadata_title.setObjectName("settingsSectionTitle")
        layout.addWidget(metadata_title)

        metadata_hint = QLabel("如果之前某些歌封面或歌词搜不到，清理失败缓存后可以右键歌曲重新搜索。")
        metadata_hint.setObjectName("settingsHint")
        metadata_hint.setWordWrap(True)
        layout.addWidget(metadata_hint)

        clear_missing_btn = QPushButton("清理封面 / 歌词失败缓存")
        clear_missing_btn.setObjectName("settingsSecondaryButton")
        clear_missing_btn.clicked.connect(self.clear_missing_cache)
        layout.addWidget(clear_missing_btn)

        layout.addSpacing(24)

        # Audio cache section
        audio_title = QLabel("音频缓存")
        audio_title.setObjectName("settingsSectionTitle")
        layout.addWidget(audio_title)

        self.audio_cache_summary_label = QLabel()
        self.audio_cache_summary_label.setObjectName("settingsHint")
        self.audio_cache_summary_label.setWordWrap(True)
        layout.addWidget(self.audio_cache_summary_label)

        self.audio_cache_path_label = QLabel()
        self.audio_cache_path_label.setObjectName("settingsHint")
        self.audio_cache_path_label.setWordWrap(True)
        self.audio_cache_path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.audio_cache_path_label.setMinimumWidth(0)
        self.audio_cache_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.audio_cache_path_label)

        # Cache buttons
        cache_btn_row = QHBoxLayout()
        cache_btn_row.setSpacing(10)

        open_cache_btn = QPushButton("打开缓存目录")
        open_cache_btn.setObjectName("settingsSecondaryButton")
        open_cache_btn.clicked.connect(self.open_audio_cache_directory)

        clear_incomplete_btn = QPushButton("清理未完成缓存")
        clear_incomplete_btn.setObjectName("settingsSecondaryButton")
        clear_incomplete_btn.clicked.connect(self.clear_incomplete_audio_cache)

        clear_all_btn = QPushButton("清理全部音频缓存")
        clear_all_btn.setObjectName("settingsSecondaryButton")
        clear_all_btn.clicked.connect(self.clear_all_audio_cache)

        cache_btn_row.addWidget(open_cache_btn)
        cache_btn_row.addWidget(clear_incomplete_btn)
        cache_btn_row.addWidget(clear_all_btn)
        cache_btn_row.addStretch()
        layout.addLayout(cache_btn_row)

    def _init_updates_page(self, settings: dict) -> None:
        """Initialize updates settings page"""
        layout = QVBoxLayout(self.page_updates)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        section_title = QLabel("应用更新")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        version_label = QLabel(f"当前版本：{APP_VERSION}")
        version_label.setObjectName("settingsHint")
        layout.addWidget(version_label)

        self.auto_update_checkbox = QCheckBox("启动后自动检查更新")
        self.auto_update_checkbox.setChecked(bool(settings.get("auto_check_updates_on_startup", False)))
        layout.addWidget(self.auto_update_checkbox)

        # Update delay
        delay_row = QHBoxLayout()
        delay_row.setSpacing(12)
        delay_row.addWidget(QLabel("启动后延迟"))
        self.update_delay_combo = QComboBox()
        for seconds, label in ((5, "5 秒"), (15, "15 秒"), (30, "30 秒"), (60, "1 分钟")):
            self.update_delay_combo.addItem(label, seconds)
        configured_delay = normalize_update_check_delay_seconds(settings.get("update_check_delay_seconds", 15))
        delay_index = self.update_delay_combo.findData(configured_delay)
        if delay_index < 0:
            self.update_delay_combo.addItem(f"{configured_delay} 秒", configured_delay)
            delay_index = self.update_delay_combo.count() - 1
        self.update_delay_combo.setCurrentIndex(delay_index)
        delay_row.addWidget(self.update_delay_combo)
        delay_row.addStretch(1)
        layout.addLayout(delay_row)

        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.setObjectName("settingsSecondaryButton")
        self.check_update_button.clicked.connect(lambda: self.main_window.check_for_updates(manual=True))
        layout.addWidget(self.check_update_button)

    def _init_about_page(self) -> None:
        """Initialize about page"""
        layout = QVBoxLayout(self.page_about)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        app_name = QLabel("HushPlayer")
        app_name.setObjectName("settingsSectionTitle")
        layout.addWidget(app_name)

        version = QLabel(f"版本 {APP_VERSION}")
        version.setObjectName("settingsHint")
        layout.addWidget(version)

        description = QLabel("轻量级本地音乐播放器，支持沉浸歌词、桌面歌词和网盘音乐文件夹同步。")
        description.setObjectName("settingsHint")
        description.setWordWrap(True)
        layout.addWidget(description)

        self._settings_wheel_passthrough_controls = (
            self.alpha_slider,
            self.floating_color_combo,
            self.floating_opacity_slider,
            self.floating_font_slider,
            self.floating_width_slider,
            self.music_scan_import_mode_combo,
        )
        for control in self._settings_wheel_passthrough_controls:
            control.installEventFilter(self)

        self.main_window.theme_manager.themeChanged.connect(
            lambda _mode: self.apply_style()
        )
        self.apply_style()

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Wheel
            and watched in getattr(self, "_settings_wheel_passthrough_controls", ())
        ):
            scroll_bar = self.settings_scroll.verticalScrollBar()
            if scroll_bar.maximum() > scroll_bar.minimum():
                pixel_delta = int(event.pixelDelta().y())
                if pixel_delta:
                    distance = pixel_delta
                else:
                    angle_delta = int(event.angleDelta().y())
                    if not angle_delta:
                        return super().eventFilter(watched, event)
                    distance = int(
                        angle_delta
                        / 120
                        * max(30, scroll_bar.singleStep() * 3)
                    )
                scroll_bar.setValue(scroll_bar.value() - distance)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def apply_style(self) -> None:
        t = ACTIVE_THEME_TOKENS
        apply_dialog_style(
            self,
            f"QDialog#settingsDialog {{ background: {t['window_background']}; color: {t['text_primary']}; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'; }}"
            f"QDialog#settingsDialog QLabel {{ color: {t['text_secondary']}; }}"
            f"QLabel#settingsDialogTitle {{ color: {t['text_primary']}; font-size: 26px; font-weight: 900; }}"
            f"QLabel#settingsDialogSubtitle {{ color: {t['text_muted']}; font-size: 13px; }}"
            "QScrollArea#settingsScrollArea, QWidget#settingsScrollContent { background: transparent; border: none; }"
            f"QFrame#settingsCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 18px; }}"
            f"QLabel#settingsCardTitle {{ color: {t['text_primary']}; font-size: 16px; font-weight: 800; }}"
            f"QLabel#settingsHint {{ color: {t['text_muted']}; font-size: 12px; }}"
            f"QLabel#settingsValueLabel {{ color: {t['text_secondary']}; font-size: 12px; min-width: 42px; }}"
            f"QCheckBox {{ color: {t['text_secondary']}; font-size: 13px; spacing: 9px; }}"
            f"QCheckBox:disabled {{ color: {t['text_disabled']}; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {t['border_strong']}; background: {t['input_background']}; }}"
            f"QCheckBox::indicator:checked {{ background: {t['accent']}; border: 1px solid {t['accent']}; }}"
            f"QComboBox {{ background: {t['input_background']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 7px 10px; }}"
            f"QComboBox:hover, QComboBox:focus {{ border-color: {t['accent']}; }}"
            f"QComboBox:disabled {{ background: {t['window_background']}; color: {t['text_disabled']}; border-color: {t['border']}; }}"
            f"QComboBox QAbstractItemView {{ background: {t['surface_tertiary']}; color: {t['text_primary']}; border: 1px solid {t['border_strong']}; selection-background-color: {t['selection_background']}; selection-color: {t['selection_text']}; outline: none; }}"
            f"QListWidget#settingsFolderList {{ background: {t['input_background']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 7px; outline: none; }}"
            "QListWidget#settingsFolderList::item { padding: 8px 10px; border-radius: 9px; margin: 2px 0; }"
            f"QListWidget#settingsFolderList::item:hover {{ background: {t['surface_hover']}; }}"
            f"QListWidget#settingsFolderList::item:selected {{ background: {t['selection_background']}; color: {t['selection_text']}; border: 1px solid {t['selection_border']}; }}"
            f"QListWidget#settingsFolderList:disabled {{ background: {t['window_background']}; color: {t['text_disabled']}; border-color: {t['border']}; }}"
            f"QPushButton#settingsPrimaryButton {{ background: {t['accent']}; color: {t['on_accent']}; border: none; border-radius: 12px; padding: 10px 18px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton#settingsPrimaryButton:hover {{ background: {t['accent_hover']}; }}"
            f"QPushButton#settingsSecondaryButton {{ background: {t['control_overlay']}; color: {t['text_secondary']}; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }}"
            f"QPushButton#settingsSecondaryButton:hover {{ background: {t['control_overlay_hover']}; color: {t['text_primary']}; }}"
            f"QPushButton#settingsPrimaryButton:disabled, QPushButton#settingsSecondaryButton:disabled {{ background: {t['surface']}; color: {t['text_disabled']}; border: 1px solid {t['border']}; }}"
            f"QSlider::groove:horizontal {{ height: 5px; background: {t['slider_groove']}; border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; background: {t['slider_handle']}; border-radius: 8px; }}"
            f"QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 3px; }}"
            f"QSlider:disabled::groove:horizontal {{ background: {t['border']}; }}"
            f"QSlider:disabled::handle:horizontal {{ background: {t['text_disabled']}; }}"
            f"QSlider:disabled::sub-page:horizontal {{ background: {t['border_strong']}; }}"
        )

    def get_music_scan_folders_from_list(self) -> list[str]:
        folders = []
        seen = set()

        if not hasattr(self, "music_scan_folder_list"):
            return folders

        for index in range(self.music_scan_folder_list.count()):
            item = self.music_scan_folder_list.item(index)
            folder = item.text().strip() if item is not None else ""

            if not folder:
                continue

            key = folder.lower()

            if key in seen:
                continue

            seen.add(key)
            folders.append(folder)

        return folders

    def add_music_scan_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "添加音乐文件夹 / 网盘同步目录",
            str(Path.home()),
        )

        if not folder_path:
            return

        try:
            folder_path = str(Path(folder_path).resolve())
        except Exception:
            folder_path = str(folder_path)

        existing_folders = {folder.lower() for folder in self.get_music_scan_folders_from_list()}

        if folder_path.lower() in existing_folders:
            QMessageBox.information(self, "音乐文件夹", "这个文件夹已经在列表里。")
            return

        self.music_scan_folder_list.addItem(folder_path)

    def remove_music_scan_folder(self) -> None:
        row = self.music_scan_folder_list.currentRow()

        if row < 0:
            QMessageBox.information(self, "音乐文件夹", "请先选择要移除的文件夹。")
            return

        self.music_scan_folder_list.takeItem(row)

    def collect_settings_updates(self) -> dict:
        self.immersive_appearance_config = replace(
            self.immersive_appearance_config,
            background_mode=str(
                self.immersive_background_mode_combo.currentData() or "default"
            ),
            darkness=int(self.alpha_slider.value()),
        )
        updates = {
            "appearance_mode": normalize_appearance_mode(
                self.appearance_mode_combo.currentData()
            ),
            "auto_check_updates_on_startup": self.auto_update_checkbox.isChecked(),
            "update_check_delay_seconds": int(self.update_delay_combo.currentData()),
            "restore_last_playback": self.restore_checkbox.isChecked(),
            "immersive_auto_hide_ui": self.auto_hide_checkbox.isChecked(),
            "floating_lyrics_color": self.floating_color_combo.currentData(),
            "floating_lyrics_opacity": int(self.floating_opacity_slider.value()),
            "floating_lyrics_font_size": int(self.floating_font_slider.value()),
            "floating_lyrics_width": int(self.floating_width_slider.value()),
            "floating_lyrics_auto_open": self.floating_auto_open_checkbox.isChecked(),
            "music_scan_folders": self.get_music_scan_folders_from_list(),
            "auto_scan_music_folders_on_startup": self.auto_scan_checkbox.isChecked(),
            "music_scan_import_mode": self.music_scan_import_mode_combo.currentData(),
        }
        updates.update(self.immersive_appearance_config.to_settings())
        return updates

    def apply_appearance_mode(self, _index: int = -1) -> None:
        self.main_window.set_appearance_mode(
            self.appearance_mode_combo.currentData(),
            persist=True,
        )

    def on_update_check_started(self, _manual: bool) -> None:
        self.check_update_button.setText("正在检查更新…")
        self.check_update_button.setEnabled(False)

    def on_update_check_completed(self) -> None:
        self.check_update_button.setText("检查更新")
        self.check_update_button.setEnabled(
            self.update_service is not None
            and not self.update_service.is_downloading
        )

    def scan_music_folders_now(self) -> None:
        self.main_window.save_hush_settings(
            self.collect_settings_updates(),
            immediate=True,
        )
        self.main_window.scan_music_folders(manual=True)

    def update_alpha_label(self, value: int) -> None:
        self.alpha_label.setText(f"{int(value)}%")

    def update_floating_opacity_label(self, value: int) -> None:
        self.floating_opacity_label.setText(f"{int(value)}%")

    def update_floating_font_label(self, value: int) -> None:
        self.floating_font_label.setText(f"{int(value)}px")

    def update_floating_width_label(self, value: int) -> None:
        self.floating_width_label.setText(f"{int(value)}px")

    def reset_floating_lyrics_position(self) -> None:
        self.main_window.reset_floating_lyrics_position_settings()
        QMessageBox.information(self, "桌面歌词", "桌面歌词位置已重置。")

    def save_settings(self) -> None:
        updates = self.collect_settings_updates()
        self.main_window.save_hush_settings(updates, immediate=True)
        self.main_window.set_appearance_mode(updates["appearance_mode"], persist=False)
        self.main_window.apply_runtime_settings()
        QMessageBox.information(self, "设置", "设置已保存。")
        self.accept()

    def clear_missing_cache(self) -> None:
        removed_count = self.main_window.clear_missing_cache_files()
        QMessageBox.information(self, "缓存", f"已清理 {removed_count} 个失败缓存文件。")

    @staticmethod
    def format_cache_bytes(value: int) -> str:
        size = float(max(0, int(value or 0)))
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024.0 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return "0 B"

    def refresh_audio_cache_status(self) -> None:
        stats = self.main_window.online_audio_cache.statistics()
        self.audio_cache_summary_label.setText(
            "已缓存歌曲：{count} 首（{complete}）\n"
            "未完成缓存：{incomplete}".format(
                count=int(stats.get("complete_count") or 0),
                complete=self.format_cache_bytes(stats.get("complete_bytes") or 0),
                incomplete=self.format_cache_bytes(
                    stats.get("incomplete_bytes") or 0
                ),
            )
        )
        self.audio_cache_path_label.setText(
            f"缓存目录：{self.main_window.online_audio_cache.cache_root}"
        )

    def open_audio_cache_directory(self) -> None:
        self.main_window.open_online_audio_cache_directory()

    def clear_incomplete_audio_cache(self) -> None:
        removed = self.main_window.clear_incomplete_online_audio_cache()
        self.refresh_audio_cache_status()
        QMessageBox.information(self, "音频缓存", f"已清理 {removed} 个未完成缓存。")

    def clear_all_audio_cache(self) -> None:
        message = (
            "仅删除在线音频缓存，不会删除本地音乐、收藏、歌单、播放记录、"
            "歌词缓存、封面缓存或用户导入的音源配置。\n\n是否继续？"
        )
        result = QMessageBox.question(
            self,
            "清理全部音频缓存",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        outcome = self.main_window.clear_all_online_audio_cache()
        self.refresh_audio_cache_status()
        skipped = int(outcome.get("skipped") or 0)
        suffix = ""
        if skipped:
            suffix = "；当前正在播放的缓存已跳过"
        QMessageBox.information(
            self,
            "音频缓存",
            f"已清理 {int(outcome.get('removed') or 0)} 个缓存{suffix}。",
        )

