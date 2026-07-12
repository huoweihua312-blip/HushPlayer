import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0541"


NEW_FLOATING_CLASS = r'''class FloatingLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.locked = False
        self.drag_offset = None

        self.font_size = int(main_window.get_user_setting("floating_lyrics_font_size", 42))
        self.text_alpha = int(main_window.get_user_setting("floating_lyrics_opacity", 100))
        self.text_color_name = str(main_window.get_user_setting("floating_lyrics_color", "white"))

        self.color_map = {
            "white": ("白色", 255, 255, 255),
            "black": ("黑色", 0, 0, 0),
            "yellow": ("黄色", 255, 226, 96),
            "blue": ("蓝色", 105, 173, 255),
            "green": ("绿色", 120, 235, 166),
            "pink": ("粉色", 255, 130, 190),
            "purple": ("紫色", 190, 145, 255),
        }

        self.setWindowTitle("HushPlayer 桌面歌词")
        self.setObjectName("floatingLyricsWindow")
        self.setMinimumSize(520, 90)
        self.resize(980, 130)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(0)

        self.current_label = QLabel("桌面歌词已开启")
        self.current_label.setObjectName("floatingLyricCurrent")
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_label.setWordWrap(True)
        self.current_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout.addWidget(self.current_label, 1)

        self.apply_style()

    def get_rgba_color(self) -> str:
        color_key = self.text_color_name

        if color_key not in self.color_map:
            color_key = "white"

        _, red, green, blue = self.color_map[color_key]
        alpha = max(25, min(255, int(self.text_alpha / 100 * 255)))

        return f"rgba({red}, {green}, {blue}, {alpha})"

    def apply_style(self) -> None:
        self.setStyleSheet(
            "QWidget#floatingLyricsWindow { background: transparent; font-family: 'Microsoft YaHei UI'; }"
            f"QLabel#floatingLyricCurrent {{ color: {self.get_rgba_color()}; background: transparent; font-size: {self.font_size}px; font-weight: 950; padding: 0px; }}"
        )

    def save_preferences(self) -> None:
        self.main_window.save_hush_settings(
            {
                "floating_lyrics_font_size": int(self.font_size),
                "floating_lyrics_opacity": int(self.text_alpha),
                "floating_lyrics_color": self.text_color_name,
            }
        )

    def set_lines(self, previous_line: str, current_line: str, next_line: str) -> None:
        self.current_label.setText(current_line or "暂无歌词")

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        if self.locked:
            lock_action = menu.addAction("解锁位置")
        else:
            lock_action = menu.addAction("锁定位置")

        bigger_action = menu.addAction("放大歌词")
        smaller_action = menu.addAction("缩小歌词")

        menu.addSeparator()

        opacity_up_action = menu.addAction("提高不透明度")
        opacity_down_action = menu.addAction("降低不透明度")

        menu.addSeparator()

        color_menu = menu.addMenu("歌词颜色")

        color_actions = {}

        for color_key, (color_label, _, _, _) in self.color_map.items():
            action = color_menu.addAction(color_label)
            action.setCheckable(True)
            action.setChecked(color_key == self.text_color_name)
            color_actions[action] = color_key

        menu.addSeparator()

        close_action = menu.addAction("关闭桌面歌词")

        action = menu.exec(event.globalPos())

        if action == lock_action:
            self.locked = not self.locked
        elif action == bigger_action:
            self.font_size = min(84, self.font_size + 3)
            self.apply_style()
            self.save_preferences()
        elif action == smaller_action:
            self.font_size = max(22, self.font_size - 3)
            self.apply_style()
            self.save_preferences()
        elif action == opacity_up_action:
            self.text_alpha = min(100, self.text_alpha + 10)
            self.apply_style()
            self.save_preferences()
        elif action == opacity_down_action:
            self.text_alpha = max(20, self.text_alpha - 10)
            self.apply_style()
            self.save_preferences()
        elif action in color_actions:
            self.text_color_name = color_actions[action]
            self.apply_style()
            self.save_preferences()
        elif action == close_action:
            self.close()

    def mousePressEvent(self, event) -> None:
        if self.locked:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.locked:
            return

        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:
        if getattr(self.main_window, "floating_lyrics_window", None) is self:
            self.main_window.floating_lyrics_window = None

        try:
            self.main_window.update_floating_lyrics_button_state()
        except Exception:
            pass

        super().closeEvent(event)
'''


FLOATING_BUTTON_METHODS = r'''    def install_floating_lyrics_button(self) -> None:
        if getattr(self, "floating_lyrics_button", None) is not None:
            return

        self.floating_lyrics_button = QPushButton("桌面歌词")
        self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
        self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.floating_lyrics_button.setFixedHeight(36)
        self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)

        target_layout = None

        anchor_names = [
            "like_button",
            "play_mode_button",
            "volume_slider",
            "volume_label",
        ]

        for attr_name in anchor_names:
            widget = getattr(self, attr_name, None)

            if widget is None:
                continue

            parent = widget.parentWidget()

            if parent is None:
                continue

            layout = parent.layout()

            if layout is not None:
                target_layout = layout
                break

        if target_layout is None:
            for button in self.findChildren(QPushButton):
                text = button.text().strip()

                if text in ("收藏", "已收藏", "♡ 收藏", "♥ 已收藏", "列表循环", "单曲循环", "随机播放"):
                    parent = button.parentWidget()

                    if parent and parent.layout():
                        target_layout = parent.layout()
                        break

        if target_layout is None:
            print("没有找到底部控制栏布局，桌面歌词按钮暂时无法加入。仍可用 Ctrl+Shift+D 打开。")
            return

        target_layout.addWidget(self.floating_lyrics_button)
        self.update_floating_lyrics_button_state()

    def update_floating_lyrics_button_state(self) -> None:
        button = getattr(self, "floating_lyrics_button", None)

        if button is None:
            return

        window = getattr(self, "floating_lyrics_window", None)

        if window is not None and window.isVisible():
            button.setText("关闭桌面歌词")
            button.setProperty("active", True)
        else:
            button.setText("桌面歌词")
            button.setProperty("active", False)

        button.style().unpolish(button)
        button.style().polish(button)
'''


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.4.1 (local music player prototype)",
        "HushPlayer/0.5.4 (local music player prototype)",
        "HushPlayer/0.5.3.2 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.4.2 (local music player prototype)")

    return text


def replace_floating_class(text: str) -> str:
    if "class FloatingLyricsWindow(QWidget):" not in text:
        raise RuntimeError("没有找到 FloatingLyricsWindow。请先确认已经升级到 v0.5.4。")

    next_markers = [
        "class PlayQueueDialog(QDialog):",
        "class SettingsDialog(QDialog):",
        "class ImmersiveLyricsWindow(QWidget):",
        "class MainWindow(QMainWindow):",
    ]

    for marker in next_markers:
        pattern = re.compile(
            r"\nclass FloatingLyricsWindow\(QWidget\):.*?\n\n" + re.escape(marker),
            flags=re.S,
        )

        if pattern.search(text):
            return pattern.sub("\n" + NEW_FLOATING_CLASS.strip() + "\n\n" + marker, text, count=1)

    raise RuntimeError("找到了 FloatingLyricsWindow，但没有找到它后面的类，无法安全替换。")


def insert_before_method(text: str, method_name: str, content: str) -> str:
    marker = f"\n    def {method_name}("

    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{method_name}")

    return text.replace(marker, "\n" + content.rstrip() + "\n" + marker, 1)


def add_floating_button_methods(text: str) -> str:
    if "def install_floating_lyrics_button" in text:
        return text

    markers = [
        "install_floating_lyrics_feature",
        "install_playlist_button_hook",
        "install_settings_button_hook",
        "toggle_floating_lyrics",
    ]

    for method_name in markers:
        if f"\n    def {method_name}(" in text:
            return insert_before_method(text, method_name, FLOATING_BUTTON_METHODS)

    raise RuntimeError("没有找到插入桌面歌词按钮方法的位置。")


def patch_init_or_feature_install(text: str) -> str:
    if "self.install_floating_lyrics_button()" in text:
        return text

    marker = "        QTimer.singleShot(0, self.install_floating_lyrics_feature)\n"

    if marker in text:
        return text.replace(
            marker,
            marker + "        QTimer.singleShot(0, self.install_floating_lyrics_button)\n",
            1,
        )

    marker = "        QTimer.singleShot(0, self.install_playlist_button_hook)\n"

    if marker in text:
        return text.replace(
            marker,
            marker + "        QTimer.singleShot(0, self.install_floating_lyrics_button)\n",
            1,
        )

    pattern = re.compile(
        r"(\n    def __init__\(self.*?\):\n.*?)(\n    def )",
        flags=re.S,
    )
    match = pattern.search(text)

    if not match:
        raise RuntimeError("没有找到 MainWindow.__init__，无法安装桌面歌词按钮。")

    init_text = match.group(1).rstrip() + "\n\n        QTimer.singleShot(0, self.install_floating_lyrics_button)\n"
    return text[:match.start(1)] + init_text + text[match.start(2):]


def patch_toggle_and_show_state(text: str) -> str:
    if "self.update_floating_lyrics_button_state()" in text and "def show_floating_lyrics" in text:
        return text

    # 给 toggle_floating_lyrics 的关闭分支加按钮状态刷新。
    old = '''            self.floating_lyrics_window.close()
            self.floating_lyrics_window = None
            return
'''
    new = '''            self.floating_lyrics_window.close()
            self.floating_lyrics_window = None
            self.update_floating_lyrics_button_state()
            return
'''
    if old in text:
        text = text.replace(old, new, 1)

    old = '''        self.floating_lyrics_window.show()
        self.floating_lyrics_window.raise_()
'''
    new = '''        self.floating_lyrics_window.show()
        self.floating_lyrics_window.raise_()
        self.update_floating_lyrics_button_state()
'''
    if old in text:
        text = text.replace(old, new, 1)

    return text


def patch_immersive_bigger(text: str) -> str:
    replacements = [
        (
            r'"QLabel#lyricLine \{[^"]*\}"',
            '"QLabel#lyricLine { color: rgba(215,222,235,100); font-size: 24px; font-weight: 600; padding: 34px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'near\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'near\'] { color: rgba(236,240,248,170); font-size: 40px; font-weight: 800; padding: 54px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'current\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'current\'] { color: #ffffff; font-size: 104px; font-weight: 950; padding: 82px 10px; }"',
        ),
    ]

    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text)

        if count == 0:
            print("提示：没有匹配到某条沉浸歌词样式：", pattern)

    return text


def patch_button_style(text: str) -> str:
    if "QPushButton#floatingLyricsToggleButton" in text:
        return text

    style_piece = (
        '"QPushButton#floatingLyricsToggleButton { background: #232833; color: #dfe4ee; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; }"'
        '"QPushButton#floatingLyricsToggleButton:hover { background: #303747; }"'
        '"QPushButton#floatingLyricsToggleButton[active=true] { background: #2f68d8; color: #ffffff; }"'
    )

    # 尽量塞进主 stylesheet 末尾；塞不到也不影响功能。
    marker = 'self.setStyleSheet('

    if marker not in text:
        return text

    # 追加到最后一个 setStyleSheet 字符串比较难精准，先不强行改全局样式。
    return text


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_version(text)
    text = replace_floating_class(text)
    text = add_floating_button_methods(text)
    text = patch_init_or_feature_install(text)
    text = patch_toggle_and_show_state(text)
    text = patch_immersive_bigger(text)
    text = patch_button_style(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.4.2 桌面歌词按钮 / 颜色透明度 / 更大沉浸歌词 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
