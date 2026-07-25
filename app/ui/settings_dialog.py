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

APP_VERSION = "0.5.0-beta.7"

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
        self.setMinimumWidth(520)

        settings = self.main_window.get_hush_settings()
        self.immersive_appearance_config = ImmersiveAppearanceConfig.from_settings(
            settings
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        title = QLabel("设置")
        title.setObjectName("settingsDialogTitle")

        subtitle = QLabel("管理应用更新、播放恢复、歌词显示与本地音乐文件夹。")
        subtitle.setObjectName("settingsDialogSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.settings_scroll = QScrollArea(self)
        self.settings_scroll.setObjectName("settingsScrollArea")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.settings_scroll_content = QWidget()
        self.settings_scroll_content.setObjectName("settingsScrollContent")
        self.settings_scroll_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.settings_content_layout = QVBoxLayout(self.settings_scroll_content)
        self.settings_content_layout.setContentsMargins(0, 0, 8, 0)
        self.settings_content_layout.setSpacing(18)
        self.settings_scroll.setWidget(self.settings_scroll_content)
        layout.addWidget(self.settings_scroll, 1)

        appearance_card = QFrame()
        appearance_card.setObjectName("settingsCard")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(16, 16, 16, 16)
        appearance_layout.setSpacing(12)
        appearance_title = QLabel("外观")
        appearance_title.setObjectName("settingsCardTitle")
        appearance_hint = QLabel("切换后立即应用到已打开的窗口。跟随系统会使用 Windows 当前外观。")
        appearance_hint.setObjectName("settingsHint")
        appearance_hint.setWordWrap(True)
        self.appearance_mode_combo = QComboBox()
        self.appearance_mode_combo.addItem("跟随系统", "system")
        self.appearance_mode_combo.addItem("浅色", "light")
        self.appearance_mode_combo.addItem("深色", "dark")
        appearance_mode = normalize_appearance_mode(
            settings.get("appearance_mode", "dark")
        )
        appearance_index = self.appearance_mode_combo.findData(appearance_mode)
        self.appearance_mode_combo.setCurrentIndex(max(0, appearance_index))
        self.appearance_mode_combo.currentIndexChanged.connect(
            self.apply_appearance_mode
        )
        appearance_layout.addWidget(appearance_title)
        appearance_layout.addWidget(QLabel("主题"))
        appearance_layout.addWidget(self.appearance_mode_combo)
        appearance_layout.addWidget(appearance_hint)

        playback_card = QFrame()
        playback_card.setObjectName("settingsCard")
        playback_layout = QVBoxLayout(playback_card)
        playback_layout.setContentsMargins(16, 16, 16, 16)
        playback_layout.setSpacing(12)

        playback_title = QLabel("播放")
        playback_title.setObjectName("settingsCardTitle")

        self.restore_checkbox = QCheckBox("启动时恢复上次播放的歌曲和进度")
        self.restore_checkbox.setChecked(bool(settings.get("restore_last_playback", True)))

        playback_layout.addWidget(playback_title)
        playback_layout.addWidget(self.restore_checkbox)

        immersive_card = QFrame()
        immersive_card.setObjectName("settingsCard")
        immersive_layout = QVBoxLayout(immersive_card)
        immersive_layout.setContentsMargins(16, 16, 16, 16)
        immersive_layout.setSpacing(12)

        immersive_title = QLabel("沉浸歌词")
        immersive_title.setObjectName("settingsCardTitle")

        self.immersive_background_mode_combo = QComboBox()
        self.immersive_background_mode_combo.addItem("封面模糊", "cover")
        self.immersive_background_mode_combo.addItem("纯色背景", "default")
        self.immersive_background_mode_combo.addItem("半透明背景", "translucent")
        self.immersive_background_mode_combo.addItem("自定义图片", "custom")
        immersive_mode_index = self.immersive_background_mode_combo.findData(
            self.immersive_appearance_config.background_mode
        )
        self.immersive_background_mode_combo.setCurrentIndex(
            max(0, immersive_mode_index)
        )

        self.auto_hide_checkbox = QCheckBox("默认自动隐藏沉浸歌词 UI")
        self.auto_hide_checkbox.setChecked(bool(settings.get("immersive_auto_hide_ui", True)))

        alpha_row = QHBoxLayout()
        alpha_row.setContentsMargins(0, 0, 0, 0)
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

        self.update_alpha_label(self.alpha_slider.value())

        immersive_layout.addWidget(immersive_title)
        immersive_layout.addWidget(QLabel("背景模式"))
        immersive_layout.addWidget(self.immersive_background_mode_combo)
        immersive_layout.addWidget(self.auto_hide_checkbox)
        immersive_layout.addLayout(alpha_row)
        immersive_hint = QLabel("自定义图片、模糊、透明度、填充方式和歌词字号可在沉浸歌词右上角“显示设置”中调整。")
        immersive_hint.setWordWrap(True)
        immersive_hint.setObjectName("settingsHint")
        immersive_layout.addWidget(immersive_hint)

        floating_card = QFrame()
        floating_card.setObjectName("settingsCard")
        floating_layout = QVBoxLayout(floating_card)
        floating_layout.setContentsMargins(16, 16, 16, 16)
        floating_layout.setSpacing(12)

        floating_title = QLabel("桌面歌词")
        floating_title.setObjectName("settingsCardTitle")

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

        floating_color_row = QHBoxLayout()
        floating_color_row.setContentsMargins(0, 0, 0, 0)
        floating_color_row.setSpacing(12)
        floating_color_row.addWidget(QLabel("默认歌词颜色"))
        floating_color_row.addWidget(self.floating_color_combo, 1)

        floating_opacity_row = QHBoxLayout()
        floating_opacity_row.setContentsMargins(0, 0, 0, 0)
        floating_opacity_row.setSpacing(12)

        self.floating_opacity_label = QLabel()
        self.floating_opacity_label.setObjectName("settingsValueLabel")

        self.floating_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_opacity_slider.setRange(20, 100)
        self.floating_opacity_slider.setValue(int(settings.get("floating_lyrics_opacity", 100)))
        self.floating_opacity_slider.valueChanged.connect(self.update_floating_opacity_label)

        floating_opacity_row.addWidget(QLabel("默认不透明度"))
        floating_opacity_row.addWidget(self.floating_opacity_slider, 1)
        floating_opacity_row.addWidget(self.floating_opacity_label)

        floating_font_row = QHBoxLayout()
        floating_font_row.setContentsMargins(0, 0, 0, 0)
        floating_font_row.setSpacing(12)

        self.floating_font_label = QLabel()
        self.floating_font_label.setObjectName("settingsValueLabel")

        self.floating_font_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_font_slider.setRange(22, 84)
        self.floating_font_slider.setValue(int(settings.get("floating_lyrics_font_size", 42)))
        self.floating_font_slider.valueChanged.connect(self.update_floating_font_label)

        floating_font_row.addWidget(QLabel("默认字号"))
        floating_font_row.addWidget(self.floating_font_slider, 1)
        floating_font_row.addWidget(self.floating_font_label)

        floating_width_row = QHBoxLayout()
        floating_width_row.setContentsMargins(0, 0, 0, 0)
        floating_width_row.setSpacing(12)

        self.floating_width_label = QLabel()
        self.floating_width_label.setObjectName("settingsValueLabel")

        self.floating_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_width_slider.setRange(420, 1600)
        self.floating_width_slider.setValue(int(settings.get("floating_lyrics_width", 980)))
        self.floating_width_slider.valueChanged.connect(self.update_floating_width_label)

        floating_width_row.addWidget(QLabel("默认宽度"))
        floating_width_row.addWidget(self.floating_width_slider, 1)
        floating_width_row.addWidget(self.floating_width_label)

        self.floating_auto_open_checkbox = QCheckBox("启动时自动打开桌面歌词")
        self.floating_auto_open_checkbox.setChecked(bool(settings.get("floating_lyrics_auto_open", False)))

        reset_floating_position_btn = QPushButton("重置桌面歌词位置")
        reset_floating_position_btn.setObjectName("settingsSecondaryButton")
        reset_floating_position_btn.clicked.connect(self.reset_floating_lyrics_position)

        floating_layout.addWidget(floating_title)
        floating_layout.addLayout(floating_color_row)
        floating_layout.addLayout(floating_opacity_row)
        floating_layout.addLayout(floating_font_row)
        floating_layout.addLayout(floating_width_row)
        floating_layout.addWidget(self.floating_auto_open_checkbox)
        floating_layout.addWidget(reset_floating_position_btn)

        self.update_floating_opacity_label(self.floating_opacity_slider.value())
        self.update_floating_font_label(self.floating_font_slider.value())
        self.update_floating_width_label(self.floating_width_slider.value())

        scan_card = QFrame()
        scan_card.setObjectName("settingsCard")
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(16, 16, 16, 16)
        scan_layout.setSpacing(12)

        scan_title = QLabel("音乐文件夹 / 网盘同步目录")
        scan_title.setObjectName("settingsCardTitle")

        scan_hint = QLabel("可以添加百度网盘同步空间、夸克网盘下载目录、OneDrive、NAS 或本地音乐文件夹。如果播放卡顿，建议在网盘客户端中把音乐文件设为本地可用。")
        scan_hint.setObjectName("settingsHint")
        scan_hint.setWordWrap(True)

        self.music_scan_folder_list = QListWidget()
        self.music_scan_folder_list.setObjectName("settingsFolderList")
        self.music_scan_folder_list.setMinimumHeight(110)

        for folder in settings.get("music_scan_folders", []):
            if isinstance(folder, str) and folder.strip():
                self.music_scan_folder_list.addItem(folder.strip())

        scan_button_row = QHBoxLayout()
        scan_button_row.setContentsMargins(0, 0, 0, 0)
        scan_button_row.setSpacing(10)

        add_scan_folder_btn = QPushButton("添加文件夹")
        add_scan_folder_btn.setObjectName("settingsSecondaryButton")
        add_scan_folder_btn.clicked.connect(self.add_music_scan_folder)

        remove_scan_folder_btn = QPushButton("移除选中文件夹")
        remove_scan_folder_btn.setObjectName("settingsSecondaryButton")
        remove_scan_folder_btn.clicked.connect(self.remove_music_scan_folder)

        scan_now_btn = QPushButton("手动重新扫描")
        scan_now_btn.setObjectName("settingsSecondaryButton")
        scan_now_btn.clicked.connect(self.scan_music_folders_now)

        scan_button_row.addWidget(add_scan_folder_btn)
        scan_button_row.addWidget(remove_scan_folder_btn)
        scan_button_row.addWidget(scan_now_btn)
        scan_button_row.addStretch(1)

        self.auto_scan_checkbox = QCheckBox("启动时自动扫描这些文件夹")
        self.auto_scan_checkbox.setChecked(bool(settings.get("auto_scan_music_folders_on_startup", True)))

        import_mode_row = QHBoxLayout()
        import_mode_row.setContentsMargins(0, 0, 0, 0)
        import_mode_row.setSpacing(12)

        self.music_scan_import_mode_combo = QComboBox()
        self.music_scan_import_mode_combo.addItem("进入待导入列表，手动确认", "pending")
        self.music_scan_import_mode_combo.addItem("自动加入音乐库", "auto")
        current_import_mode = str(settings.get("music_scan_import_mode", "pending"))
        import_mode_index = self.music_scan_import_mode_combo.findData(current_import_mode)

        if import_mode_index >= 0:
            self.music_scan_import_mode_combo.setCurrentIndex(import_mode_index)

        import_mode_row.addWidget(QLabel("扫描新音乐后的处理方式"))
        import_mode_row.addWidget(self.music_scan_import_mode_combo, 1)
        scan_cloud_hint = QLabel("推荐用百度网盘客户端的同步空间，或夸克网盘的下载目录，把音乐文件同步/下载到本地后由 HushPlayer 自动扫描。这样最稳定，也不需要登录网盘 API。")
        scan_cloud_hint.setObjectName("settingsHint")
        scan_cloud_hint.setWordWrap(True)

        scan_layout.addWidget(scan_title)
        scan_layout.addWidget(scan_hint)
        scan_layout.addWidget(self.music_scan_folder_list)
        scan_layout.addLayout(scan_button_row)
        scan_layout.addWidget(self.auto_scan_checkbox)
        scan_layout.addLayout(import_mode_row)
        scan_layout.addWidget(scan_cloud_hint)
        cache_card = QFrame()
        cache_card.setObjectName("settingsCard")
        cache_layout = QVBoxLayout(cache_card)
        cache_layout.setContentsMargins(16, 16, 16, 16)
        cache_layout.setSpacing(12)

        cache_title = QLabel("缓存")
        cache_title.setObjectName("settingsCardTitle")

        cache_hint = QLabel("如果之前某些歌封面或歌词搜不到，清理失败缓存后可以右键歌曲重新搜索。")
        cache_hint.setObjectName("settingsHint")
        cache_hint.setWordWrap(True)

        clear_missing_btn = QPushButton("清理封面 / 歌词失败缓存")
        clear_missing_btn.setObjectName("settingsSecondaryButton")
        clear_missing_btn.clicked.connect(self.clear_missing_cache)

        audio_cache_title = QLabel("音频缓存")
        audio_cache_title.setObjectName("settingsCardTitle")

        self.audio_cache_summary_label = QLabel()
        self.audio_cache_summary_label.setObjectName("settingsHint")
        self.audio_cache_summary_label.setWordWrap(True)

        self.audio_cache_path_label = QLabel()
        self.audio_cache_path_label.setObjectName("settingsHint")
        self.audio_cache_path_label.setWordWrap(True)
        self.audio_cache_path_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.audio_cache_path_label.setMinimumWidth(0)
        self.audio_cache_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        audio_cache_button_row = QHBoxLayout()
        audio_cache_button_row.setContentsMargins(0, 0, 0, 0)
        audio_cache_button_row.setSpacing(10)

        open_audio_cache_btn = QPushButton("打开缓存目录")
        open_audio_cache_btn.setObjectName("settingsSecondaryButton")
        open_audio_cache_btn.clicked.connect(self.open_audio_cache_directory)

        clear_incomplete_audio_cache_btn = QPushButton("清理未完成缓存")
        clear_incomplete_audio_cache_btn.setObjectName("settingsSecondaryButton")
        clear_incomplete_audio_cache_btn.clicked.connect(
            self.clear_incomplete_audio_cache
        )

        clear_all_audio_cache_btn = QPushButton("清理全部音频缓存")
        clear_all_audio_cache_btn.setObjectName("settingsSecondaryButton")
        clear_all_audio_cache_btn.clicked.connect(self.clear_all_audio_cache)

        audio_cache_button_row.addWidget(open_audio_cache_btn)
        audio_cache_button_row.addWidget(clear_incomplete_audio_cache_btn)
        audio_cache_button_row.addWidget(clear_all_audio_cache_btn)
        audio_cache_button_row.addStretch()

        cache_layout.addWidget(cache_title)
        cache_layout.addWidget(cache_hint)
        cache_layout.addWidget(clear_missing_btn)
        cache_layout.addSpacing(4)
        cache_layout.addWidget(audio_cache_title)
        cache_layout.addWidget(self.audio_cache_summary_label)
        cache_layout.addWidget(self.audio_cache_path_label)
        cache_layout.addLayout(audio_cache_button_row)

        update_card = QFrame()
        update_card.setObjectName("settingsCard")
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(16, 16, 16, 16)
        update_layout.setSpacing(12)

        update_title = QLabel("应用更新")
        update_title.setObjectName("settingsCardTitle")
        update_version = QLabel(f"当前版本：{APP_VERSION}")
        update_version.setObjectName("settingsHint")
        self.auto_update_checkbox = QCheckBox("启动后自动检查更新")
        self.auto_update_checkbox.setChecked(
            bool(settings.get("auto_check_updates_on_startup", False))
        )

        update_delay_row = QHBoxLayout()
        update_delay_row.setContentsMargins(0, 0, 0, 0)
        update_delay_row.setSpacing(12)
        update_delay_row.addWidget(QLabel("启动后延迟"))
        self.update_delay_combo = QComboBox()
        for seconds, label in (
            (5, "5 秒"),
            (15, "15 秒"),
            (30, "30 秒"),
            (60, "1 分钟"),
        ):
            self.update_delay_combo.addItem(label, seconds)
        configured_delay = normalize_update_check_delay_seconds(
            settings.get("update_check_delay_seconds", 15)
        )
        delay_index = self.update_delay_combo.findData(configured_delay)
        if delay_index < 0:
            self.update_delay_combo.addItem(f"{configured_delay} 秒", configured_delay)
            delay_index = self.update_delay_combo.count() - 1
        self.update_delay_combo.setCurrentIndex(delay_index)
        update_delay_row.addWidget(self.update_delay_combo)
        update_delay_row.addStretch(1)

        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.setObjectName("settingsSecondaryButton")
        self.update_service = getattr(self.main_window, "update_service", None)
        if self.update_service is None:
            update_card.hide()
        else:
            self.check_update_button.clicked.connect(
                lambda: self.main_window.check_for_updates(manual=True)
            )
            self.check_update_button.setEnabled(
                not self.update_service.is_checking
                and not self.update_service.is_downloading
            )
            self.update_service.checkStarted.connect(self.on_update_check_started)
            self.update_service.checkCompleted.connect(self.on_update_check_completed)

        update_layout.addWidget(update_title)
        update_layout.addWidget(update_version)
        update_layout.addWidget(self.auto_update_checkbox)
        update_layout.addLayout(update_delay_row)
        update_layout.addWidget(self.check_update_button)

        self.main_window.online_audio_cache.statisticsChanged.connect(
            self.refresh_audio_cache_status
        )
        self.refresh_audio_cache_status()

        self.settings_content_layout.addWidget(appearance_card)
        self.settings_content_layout.addWidget(playback_card)
        self.settings_content_layout.addWidget(immersive_card)
        self.settings_content_layout.addWidget(floating_card)
        self.settings_content_layout.addWidget(scan_card)
        self.settings_content_layout.addWidget(cache_card)
        self.settings_content_layout.addWidget(update_card)
        self.settings_content_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.setSpacing(12)

        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("settingsPrimaryButton")
        save_btn.clicked.connect(self.save_settings)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("settingsSecondaryButton")
        cancel_btn.clicked.connect(self.reject)

        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)

        layout.addLayout(button_row)

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

