"""
Complete redesign of SettingsDialog with left navigation + right content
"""
import sys
from pathlib import Path

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Read original file
original = Path('app/ui/settings_dialog.py').read_text(encoding='utf-8')
lines = original.split('\n')

# Find __init__ method start
init_start = None
for i, line in enumerate(lines):
    if 'def __init__(self, main_window) -> None:' in line:
        init_start = i
        break

# Find where __init__ ends (next method definition)
init_end = None
for i in range(init_start + 1, len(lines)):
    if lines[i].strip().startswith('def ') and not lines[i].strip().startswith('def __'):
        init_end = i
        break

print(f"Found __init__ from line {init_start + 1} to {init_end}")

# Extract everything before __init__
header = lines[:init_start]

# Extract everything after __init__ (all helper methods)
helpers = lines[init_end:]

# Build new __init__ with navigation layout
new_init = '''    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("HushPlayer 设置")
        self.setObjectName("settingsDialog")
        self.setMinimumSize(900, 600)

        settings = self.main_window.get_hush_settings()
        self.immersive_appearance_config = ImmersiveAppearanceConfig.from_settings(settings)

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
        header = QFrame()
        header.setObjectName("settingsContentHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(32, 24, 32, 16)
        header_layout.setSpacing(0)

        self.content_title = QLabel("常规")
        self.content_title.setObjectName("settingsContentTitle")
        header_layout.addWidget(self.content_title)
        content_layout.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setObjectName("settingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.content_stack = QWidget()
        stack_layout = QVBoxLayout(self.content_stack)
        stack_layout.setContentsMargins(32, 16, 32, 32)
        stack_layout.setSpacing(24)

        # Create all category pages
        self.page_general = QWidget()
        self.page_appearance = QWidget()
        self.page_lyrics = QWidget()
        self.page_library = QWidget()
        self.page_cache = QWidget()
        self.page_updates = QWidget()
        self.page_about = QWidget()

        # Stack to hold pages (we'll use manual show/hide instead of QStackedWidget)
        self.pages = [
            self.page_general,
            self.page_appearance,
            self.page_lyrics,
            self.page_library,
            self.page_cache,
            self.page_updates,
            self.page_about,
        ]

        for page in self.pages:
            page.setVisible(False)
            stack_layout.addWidget(page)

        self.pages[0].setVisible(True)  # Show first page
        stack_layout.addStretch(1)

        scroll.setWidget(self.content_stack)
        content_layout.addWidget(scroll, 1)

        # Footer with buttons
        footer = QFrame()
        footer.setObjectName("settingsContentFooter")
        footer_layout = QHBoxLayout(footer)
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
        content_layout.addWidget(footer)

        main_layout.addWidget(content_panel, 1)

        # Initialize all controls in pages
        self._init_general_page(settings)
        self._init_appearance_page(settings)
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

        self.restore_checkbox = QCheckBox("启动时恢复上次播放的歌曲和进度")
        self.restore_checkbox.setChecked(bool(settings.get("restore_last_playback", True)))
        layout.addWidget(self.restore_checkbox)

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

        immersive_hint = QLabel("自定义图片、模糊、透明度、填充方式和歌词字号可在沉浸歌词右上角"显示设置"中调整。")
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
        if self.update_service is None:
            self.check_update_button.setVisible(False)
        else:
            self.check_update_button.clicked.connect(lambda: self.main_window.check_for_updates(manual=True))
            self.check_update_button.setEnabled(
                not self.update_service.is_checking and not self.update_service.is_downloading
            )
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
'''

# Combine everything
new_content = '\n'.join(header) + '\n' + new_init + '\n' + '\n'.join(helpers)

# Write new file
Path('app/ui/settings_dialog.py').write_text(new_content, encoding='utf-8')

print("Redesigned settings_dialog.py with navigation layout")
print(f"New file: {len(new_content.split(chr(10)))} lines")
