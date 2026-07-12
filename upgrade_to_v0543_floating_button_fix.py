import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0542"


NEW_FLOATING_CLASS = r'''class FloatingLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.locked = False
        self.drag_offset = None

        self.font_size = int(main_window.get_user_setting("floating_lyrics_font_size", 42))
        self.text_alpha = int(main_window.get_user_setting("floating_lyrics_opacity", 100))
        self.text_color_name = str(main_window.get_user_setting("floating_lyrics_color", "white"))
        self.window_width = int(main_window.get_user_setting("floating_lyrics_width", 980))

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
        self.setMinimumSize(420, 80)
        self.resize(self.window_width, 135)

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
                "floating_lyrics_width": int(self.width()),
            }
        )

    def set_lines(self, previous_line: str, current_line: str, next_line: str) -> None:
        self.current_label.setText(current_line or "暂无歌词")

    def adjust_font_size(self, step: int) -> None:
        self.font_size = max(22, min(84, self.font_size + step))
        self.apply_style()
        self.save_preferences()

    def adjust_window_width(self, step: int) -> None:
        new_width = max(420, min(1600, self.width() + step))
        self.resize(new_width, self.height())
        self.save_preferences()

    def reset_size(self) -> None:
        self.font_size = 42
        self.resize(980, 135)
        self.apply_style()
        self.save_preferences()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        if self.locked:
            lock_action = menu.addAction("解锁位置")
        else:
            lock_action = menu.addAction("锁定位置")

        bigger_action = menu.addAction("放大歌词")
        smaller_action = menu.addAction("缩小歌词")
        wider_action = menu.addAction("加宽显示区域")
        narrower_action = menu.addAction("缩窄显示区域")
        reset_size_action = menu.addAction("重置大小")

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
            self.adjust_font_size(3)
        elif action == smaller_action:
            self.adjust_font_size(-3)
        elif action == wider_action:
            self.adjust_window_width(100)
        elif action == narrower_action:
            self.adjust_window_width(-100)
        elif action == reset_size_action:
            self.reset_size()
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

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()

        if delta == 0:
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if delta > 0:
                self.adjust_window_width(80)
            else:
                self.adjust_window_width(-80)
        else:
            if delta > 0:
                self.adjust_font_size(2)
            else:
                self.adjust_font_size(-2)

        event.accept()

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


NEW_INSTALL_BUTTON_METHOD = r'''    def install_floating_lyrics_button(self) -> None:
        existing_button = getattr(self, "floating_lyrics_button", None)

        if existing_button is None:
            self.floating_lyrics_button = QPushButton("桌面歌词")
            self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
            self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.floating_lyrics_button.setFixedHeight(34)
            self.floating_lyrics_button.setMinimumWidth(92)
            self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)
        else:
            old_parent = existing_button.parentWidget()

            if old_parent is not None:
                old_layout = old_parent.layout()

                if old_layout is not None:
                    old_layout.removeWidget(existing_button)

                existing_button.setParent(None)

        button = self.floating_lyrics_button

        def layout_contains_widget(layout, target_widget) -> bool:
            if layout is None or target_widget is None:
                return False

            for index in range(layout.count()):
                item = layout.itemAt(index)

                if item is None:
                    continue

                widget = item.widget()

                if widget is target_widget:
                    return True

                child_layout = item.layout()

                if child_layout is not None and layout_contains_widget(child_layout, target_widget):
                    return True

            return False

        def direct_widget_index(layout, target_widget) -> int:
            if layout is None or target_widget is None:
                return -1

            for index in range(layout.count()):
                item = layout.itemAt(index)

                if item is not None and item.widget() is target_widget:
                    return index

            return -1

        def find_button_by_text(text_candidates):
            for candidate_button in self.findChildren(QPushButton):
                text = candidate_button.text().strip()

                for candidate in text_candidates:
                    if candidate in text:
                        return candidate_button

            return None

        play_mode_button = getattr(self, "play_mode_button", None)

        if play_mode_button is None:
            play_mode_button = find_button_by_text(["列表循环", "单曲循环", "随机播放"])

        like_button = getattr(self, "like_button", None)

        if like_button is None:
            like_button = find_button_by_text(["收藏", "已收藏"])

        target_layout = None
        anchor_widget = None

        for anchor in (play_mode_button, like_button):
            widget = anchor

            while widget is not None:
                parent = widget.parentWidget()

                if parent is None:
                    break

                layout = parent.layout()

                if layout is not None and layout_contains_widget(layout, anchor):
                    layout_name = layout.__class__.__name__.lower()

                    if "box" in layout_name and "vbox" not in layout_name:
                        target_layout = layout
                        anchor_widget = anchor
                        break

                    if target_layout is None:
                        target_layout = layout
                        anchor_widget = anchor

                widget = parent

            if target_layout is not None and "vbox" not in target_layout.__class__.__name__.lower():
                break

        if target_layout is None:
            print("没有找到适合放桌面歌词按钮的底部横向布局，仍可用 Ctrl+Shift+D 打开。")
            return

        insert_index = direct_widget_index(target_layout, anchor_widget)

        if insert_index >= 0 and hasattr(target_layout, "insertWidget"):
            target_layout.insertWidget(insert_index + 1, button)
        else:
            target_layout.addWidget(button)

        self.update_floating_lyrics_button_state()
'''


NEW_UPDATE_BUTTON_METHOD = r'''    def update_floating_lyrics_button_state(self) -> None:
        button = getattr(self, "floating_lyrics_button", None)

        if button is None:
            return

        window = getattr(self, "floating_lyrics_window", None)
        is_active = window is not None and window.isVisible()

        if is_active:
            button.setText("桌面歌词开")
            button.setStyleSheet(
                "QPushButton#floatingLyricsToggleButton { background: #2f68d8; color: #ffffff; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; font-weight: 700; }"
                "QPushButton#floatingLyricsToggleButton:hover { background: #3d7af0; }"
            )
        else:
            button.setText("桌面歌词")
            button.setStyleSheet(
                "QPushButton#floatingLyricsToggleButton { background: #232833; color: #dfe4ee; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; }"
                "QPushButton#floatingLyricsToggleButton:hover { background: #303747; }"
            )
'''


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.4.2 (local music player prototype)",
        "HushPlayer/0.5.4.1 (local music player prototype)",
        "HushPlayer/0.5.4 (local music player prototype)",
        "HushPlayer/0.5.3.2 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.4.3 (local music player prototype)")

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


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def patch_immersive_bigger(text: str) -> str:
    replacements = [
        (
            r'"QLabel#lyricLine \{[^"]*\}"',
            '"QLabel#lyricLine { color: rgba(215,222,235,90); font-size: 24px; font-weight: 600; padding: 42px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'near\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'near\'] { color: rgba(236,240,248,155); font-size: 44px; font-weight: 800; padding: 70px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'current\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'current\'] { color: #ffffff; font-size: 118px; font-weight: 950; padding: 104px 10px; }"',
        ),
    ]

    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text)

        if count == 0:
            print("提示：没有匹配到某条沉浸歌词样式：", pattern)

    return text


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_version(text)

    text = replace_floating_class(text)

    text = replace_method(text, "install_floating_lyrics_button", NEW_INSTALL_BUTTON_METHOD)
    text = replace_method(text, "update_floating_lyrics_button_state", NEW_UPDATE_BUTTON_METHOD)
    text = patch_immersive_bigger(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.4.3 桌面歌词按钮位置 / 尺寸调节 / 更大沉浸歌词 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
