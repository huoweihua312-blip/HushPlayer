import ast
import json
import py_compile
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0511"


SETTINGS_DIALOG_CLASS = r'''class SettingsDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("HushPlayer 设置")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(520)

        settings = self.main_window.get_hush_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        title = QLabel("设置")
        title.setObjectName("settingsDialogTitle")

        subtitle = QLabel("先把常用设置收进来，后面我们再慢慢做成完整设置页。")
        subtitle.setObjectName("settingsDialogSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        playback_card = QFrame()
        playback_card.setObjectName("settingsCard")
        playback_layout = QVBoxLayout(playback_card)
        playback_layout.setContentsMargins(18, 16, 18, 16)
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
        immersive_layout.setContentsMargins(18, 16, 18, 16)
        immersive_layout.setSpacing(12)

        immersive_title = QLabel("沉浸歌词")
        immersive_title.setObjectName("settingsCardTitle")

        self.cover_background_checkbox = QCheckBox("默认使用封面模糊背景")
        self.cover_background_checkbox.setChecked(bool(settings.get("immersive_cover_background_enabled", True)))

        self.auto_hide_checkbox = QCheckBox("默认自动隐藏沉浸歌词 UI")
        self.auto_hide_checkbox.setChecked(bool(settings.get("immersive_auto_hide_ui", True)))

        alpha_row = QHBoxLayout()
        alpha_row.setContentsMargins(0, 0, 0, 0)
        alpha_row.setSpacing(12)

        self.alpha_label = QLabel()
        self.alpha_label.setObjectName("settingsValueLabel")

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(35, 100)
        self.alpha_slider.setValue(int(settings.get("immersive_background_alpha", 68)))
        self.alpha_slider.valueChanged.connect(self.update_alpha_label)

        alpha_row.addWidget(QLabel("遮罩不透明度"))
        alpha_row.addWidget(self.alpha_slider, 1)
        alpha_row.addWidget(self.alpha_label)

        self.update_alpha_label(self.alpha_slider.value())

        immersive_layout.addWidget(immersive_title)
        immersive_layout.addWidget(self.cover_background_checkbox)
        immersive_layout.addWidget(self.auto_hide_checkbox)
        immersive_layout.addLayout(alpha_row)

        cache_card = QFrame()
        cache_card.setObjectName("settingsCard")
        cache_layout = QVBoxLayout(cache_card)
        cache_layout.setContentsMargins(18, 16, 18, 16)
        cache_layout.setSpacing(12)

        cache_title = QLabel("缓存")
        cache_title.setObjectName("settingsCardTitle")

        cache_hint = QLabel("如果之前某些歌封面或歌词搜不到，清理失败缓存后可以右键歌曲重新搜索。")
        cache_hint.setObjectName("settingsHint")
        cache_hint.setWordWrap(True)

        clear_missing_btn = QPushButton("清理封面 / 歌词失败缓存")
        clear_missing_btn.setObjectName("settingsSecondaryButton")
        clear_missing_btn.clicked.connect(self.clear_missing_cache)

        cache_layout.addWidget(cache_title)
        cache_layout.addWidget(cache_hint)
        cache_layout.addWidget(clear_missing_btn)

        layout.addWidget(playback_card)
        layout.addWidget(immersive_card)
        layout.addWidget(cache_card)

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

        self.apply_style()

    def apply_style(self) -> None:
        self.setStyleSheet(
            "QDialog#settingsDialog { background: #101217; color: #e8ecf5; font-family: 'Microsoft YaHei UI'; }"
            "QLabel#settingsDialogTitle { color: #ffffff; font-size: 26px; font-weight: 900; }"
            "QLabel#settingsDialogSubtitle { color: #9ca5b5; font-size: 13px; }"
            "QFrame#settingsCard { background: #171a22; border: 1px solid #252a35; border-radius: 18px; }"
            "QLabel#settingsCardTitle { color: #ffffff; font-size: 16px; font-weight: 800; }"
            "QLabel#settingsHint { color: #9ca5b5; font-size: 12px; }"
            "QLabel#settingsValueLabel { color: #d9deea; font-size: 12px; min-width: 42px; }"
            "QCheckBox { color: #dfe4ee; font-size: 13px; spacing: 9px; }"
            "QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3c4352; background: #0f1218; }"
            "QCheckBox::indicator:checked { background: #2f68d8; border: 1px solid #2f68d8; }"
            "QPushButton#settingsPrimaryButton { background: #2f68d8; color: #ffffff; border: none; border-radius: 12px; padding: 10px 18px; font-size: 13px; font-weight: 700; }"
            "QPushButton#settingsPrimaryButton:hover { background: #3d7af0; }"
            "QPushButton#settingsSecondaryButton { background: #232833; color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#settingsSecondaryButton:hover { background: #303747; }"
            "QSlider::groove:horizontal { height: 5px; background: #303747; border-radius: 3px; }"
            "QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; background: #ffffff; border-radius: 8px; }"
            "QSlider::sub-page:horizontal { background: #2f68d8; border-radius: 3px; }"
        )

    def update_alpha_label(self, value: int) -> None:
        self.alpha_label.setText(f"{int(value)}%")

    def save_settings(self) -> None:
        updates = {
            "restore_last_playback": self.restore_checkbox.isChecked(),
            "immersive_cover_background_enabled": self.cover_background_checkbox.isChecked(),
            "immersive_auto_hide_ui": self.auto_hide_checkbox.isChecked(),
            "immersive_background_alpha": int(self.alpha_slider.value()),
        }

        self.main_window.save_hush_settings(updates)
        self.main_window.apply_runtime_settings()
        QMessageBox.information(self, "设置", "设置已保存。")
        self.accept()

    def clear_missing_cache(self) -> None:
        removed_count = self.main_window.clear_missing_cache_files()
        QMessageBox.information(self, "缓存", f"已清理 {removed_count} 个失败缓存文件。")
'''


SETTINGS_METHODS = r'''    def get_hush_settings(self) -> dict:
        settings = {}

        try:
            if hasattr(self, "settings_file") and self.settings_file.exists():
                with self.settings_file.open("r", encoding="utf-8") as file:
                    file_settings = json.load(file)

                if isinstance(file_settings, dict):
                    settings.update(file_settings)
        except Exception as error:
            print("读取设置文件失败：", error)

        if hasattr(self, "settings") and isinstance(self.settings, dict):
            settings.update(self.settings)

        return settings

    def get_user_setting(self, key: str, default=None):
        return self.get_hush_settings().get(key, default)

    def save_hush_settings(self, updates: dict) -> None:
        settings = self.get_hush_settings()
        settings.update(updates)

        self.settings = settings

        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)

            with self.settings_file.open("w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=False, indent=2)

            print("设置已保存：", self.settings_file)

        except Exception as error:
            print("保存设置失败：", error)
            QMessageBox.warning(self, "设置", f"保存设置失败：{error}")

    def apply_runtime_settings(self) -> None:
        immersive_window = getattr(self, "immersive_lyrics_window", None)

        if immersive_window is None:
            return

        immersive_window.cover_background_enabled = bool(
            self.get_user_setting("immersive_cover_background_enabled", True)
        )
        immersive_window.auto_hide_enabled = bool(
            self.get_user_setting("immersive_auto_hide_ui", True)
        )
        immersive_window.background_alpha = int(
            self.get_user_setting("immersive_background_alpha", 68)
        )

        if hasattr(immersive_window, "alpha_slider"):
            immersive_window.alpha_slider.blockSignals(True)
            immersive_window.alpha_slider.setValue(immersive_window.background_alpha)
            immersive_window.alpha_slider.blockSignals(False)

        if immersive_window.auto_hide_enabled:
            immersive_window.show_controls_temporarily()
        else:
            if hasattr(immersive_window, "hide_ui_timer"):
                immersive_window.hide_ui_timer.stop()

            if hasattr(immersive_window, "control_header"):
                immersive_window.control_header.show()

            if hasattr(immersive_window, "footer"):
                immersive_window.footer.show()

            immersive_window.ui_visible = True
            immersive_window.setCursor(Qt.CursorShape.ArrowCursor)

        immersive_window.apply_immersive_style()

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def install_settings_button_hook(self) -> None:
        for button in self.findChildren(QPushButton):
            button_text = button.text().strip()

            if button_text != "设置":
                continue

            if button.property("hushSettingsHooked"):
                continue

            try:
                button.clicked.disconnect()
            except Exception:
                pass

            button.clicked.connect(self.open_settings_dialog)
            button.setProperty("hushSettingsHooked", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    def clear_missing_cache_files(self) -> int:
        removed_count = 0
        cache_dirs = []

        for attr_name in ("cover_cache_dir", "lyrics_cache_dir"):
            cache_dir = getattr(self, attr_name, None)

            if cache_dir:
                cache_dirs.append(Path(cache_dir))

        for cache_dir in cache_dirs:
            if not cache_dir.exists():
                continue

            for missing_file in cache_dir.glob("*.missing"):
                try:
                    missing_file.unlink()
                    removed_count += 1
                except Exception as error:
                    print("删除失败缓存失败：", missing_file, error)

        return removed_count
'''


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    if not new_method.strip():
        return text[:match.start()] + "\n" + text[match.end():]

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, "\n" + content.rstrip() + "\n\n" + marker.lstrip("\n"), 1)


def ensure_import_names(text: str, module: str, names_to_add: list[str]) -> str:
    pattern = re.compile(rf"from {re.escape(module)} import \((.*?)\)", flags=re.S)
    match = pattern.search(text)

    if match:
        raw = match.group(1)
        names = [line.strip().rstrip(",") for line in raw.splitlines() if line.strip()]

        for name in names_to_add:
            if name not in names:
                names.append(name)

        names = sorted(set(names), key=lambda item: item.lower())
        new_import = f"from {module} import (\n" + "".join(f"    {name},\n" for name in names) + ")"
        return text[:match.start()] + new_import + text[match.end():]

    pattern = re.compile(rf"from {re.escape(module)} import ([^\n]+)")
    match = pattern.search(text)

    if match:
        names = [name.strip() for name in match.group(1).split(",")]

        for name in names_to_add:
            if name not in names:
                names.append(name)

        new_import = f"from {module} import " + ", ".join(sorted(set(names), key=lambda item: item.lower()))
        return text[:match.start()] + new_import + text[match.end():]

    raise RuntimeError(f"没有找到导入：{module}")


def ensure_imports(text: str) -> str:
    if "import json" not in text:
        text = "import json\n" + text

    text = ensure_import_names(
        text,
        "PySide6.QtWidgets",
        [
            "QCheckBox",
            "QDialog",
        ],
    )

    text = ensure_import_names(
        text,
        "PySide6.QtCore",
        [
            "QTimer",
        ],
    )

    return text


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.1.1 (local music player prototype)",
        "HushPlayer/0.5.1 (local music player prototype)",
        "HushPlayer/0.5.0 (local music player prototype)",
        "HushPlayer/0.4.9.1 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.2 (local music player prototype)")

    return text


def insert_settings_dialog_class(text: str) -> str:
    if "class SettingsDialog(QDialog):" in text:
        return text

    marker = "\nclass ImmersiveLyricsWindow(QWidget):"

    if marker in text:
        return insert_before(text, marker, SETTINGS_DIALOG_CLASS, "SettingsDialog before ImmersiveLyricsWindow")

    marker = "\nclass MainWindow(QMainWindow):"

    if marker in text:
        return insert_before(text, marker, SETTINGS_DIALOG_CLASS, "SettingsDialog before MainWindow")

    raise RuntimeError("没有找到类插入位置。")


def insert_settings_methods(text: str) -> str:
    if "def get_hush_settings" in text:
        return text

    if "\n    def load_play_queue(" in text:
        return insert_before(text, "\n    def load_play_queue(", SETTINGS_METHODS, "settings methods before load_play_queue")

    if "\n    def load_playback_session(" in text:
        return insert_before(text, "\n    def load_playback_session(", SETTINGS_METHODS, "settings methods before load_playback_session")

    if "\n    def load_settings(" in text:
        return insert_before(text, "\n    def load_settings(", SETTINGS_METHODS, "settings methods before load_settings")

    raise RuntimeError("没有找到设置方法插入位置。")


def append_call_to_mainwindow_init(text: str) -> str:
    if "self.install_settings_button_hook()" in text:
        return text

    tree = ast.parse(text)
    init_node = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "MainWindow":
            continue

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                init_node = item
                break

    if init_node is None:
        raise RuntimeError("没有找到 MainWindow.__init__。")

    lines = text.splitlines()
    insert_index = init_node.end_lineno

    call_lines = [
        "",
        "        QTimer.singleShot(0, self.install_settings_button_hook)",
    ]

    lines[insert_index:insert_index] = call_lines
    return "\n".join(lines) + "\n"


def patch_immersive_defaults(text: str) -> str:
    replacements = {
        "        self.cover_background_enabled = True\n": (
            "        self.cover_background_enabled = bool(\n"
            "            main_window.get_user_setting(\"immersive_cover_background_enabled\", True)\n"
            "        )\n"
        ),
        "        self.background_alpha = 68\n": (
            "        self.background_alpha = int(\n"
            "            main_window.get_user_setting(\"immersive_background_alpha\", 68)\n"
            "        )\n"
        ),
        "        self.auto_hide_enabled = True\n": (
            "        self.auto_hide_enabled = bool(\n"
            "            main_window.get_user_setting(\"immersive_auto_hide_ui\", True)\n"
            "        )\n"
        ),
    }

    for old, new in replacements.items():
        if old in text and new not in text:
            text = text.replace(old, new, 1)

    return text


def patch_restore_session_guard(text: str) -> str:
    if "restore_last_playback" in text and "def restore_playback_session" in text:
        return text

    target = '''        self.restored_playback_session = True

'''
    patch = '''        self.restored_playback_session = True

        if not self.get_user_setting("restore_last_playback", True):
            return

'''

    if target in text:
        return text.replace(target, patch, 1)

    return text


def add_settings_dialog_style_to_main_stylesheet(text: str) -> str:
    # SettingsDialog 自己带 stylesheet，不强行插入主样式。
    return text


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = insert_settings_dialog_class(text)
    text = insert_settings_methods(text)
    text = append_call_to_mainwindow_init(text)
    text = patch_immersive_defaults(text)
    text = patch_restore_session_guard(text)
    text = add_settings_dialog_style_to_main_stylesheet(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.2 设置面板已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
