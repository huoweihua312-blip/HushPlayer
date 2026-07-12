import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0543"


NEW_INSTALL_BUTTON_METHOD = r'''    def install_floating_lyrics_button(self) -> None:
        if getattr(self, "floating_lyrics_button", None) is None:
            self.floating_lyrics_button = QPushButton("桌面歌词")
            self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
            self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.floating_lyrics_button.setFixedHeight(34)
            self.floating_lyrics_button.setMinimumWidth(92)
            self.floating_lyrics_button.setToolTip("打开 / 关闭桌面歌词")
            self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)

        floating_button = self.floating_lyrics_button

        def find_button_by_text(text_candidates):
            for candidate_button in self.findChildren(QPushButton):
                button_text = candidate_button.text().strip()

                for candidate in text_candidates:
                    if candidate in button_text:
                        return candidate_button

            return None

        like_button = getattr(self, "like_button", None)

        if like_button is None:
            like_button = find_button_by_text(["收藏", "已收藏", "♡", "♥"])

        play_mode_button = getattr(self, "play_mode_button", None)

        if play_mode_button is None:
            play_mode_button = find_button_by_text(["列表循环", "单曲循环", "随机播放"])

        if like_button is None or play_mode_button is None:
            print("没有找到收藏按钮或播放模式按钮，桌面歌词按钮无法强制排到同一行。")
            return

        buttons = [like_button, play_mode_button, floating_button]

        for button in buttons:
            button.setFixedHeight(34)
            button.setMinimumWidth(82)
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        play_mode_button.setMinimumWidth(92)
        floating_button.setMinimumWidth(92)

        def direct_layout(widget):
            parent = widget.parentWidget()

            if parent is None:
                return None

            return parent.layout()

        def layout_index(layout, target_widget) -> int:
            if layout is None or target_widget is None:
                return -1

            for index in range(layout.count()):
                item = layout.itemAt(index)

                if item is not None and item.widget() is target_widget:
                    return index

            return -1

        def remove_from_parent_layout(widget):
            parent = widget.parentWidget()

            if parent is None:
                return

            layout = parent.layout()

            if layout is not None:
                layout.removeWidget(widget)

        like_layout = direct_layout(like_button)
        play_mode_layout = direct_layout(play_mode_button)

        # 最理想情况：收藏和播放模式本来就在同一行。
        # 这时只需要把桌面歌词按钮也插进这一行，放在播放模式按钮后面。
        if like_layout is not None and like_layout is play_mode_layout and hasattr(like_layout, "insertWidget"):
            remove_from_parent_layout(floating_button)
            floating_button.setParent(None)

            existing_index = layout_index(like_layout, floating_button)

            if existing_index >= 0:
                like_layout.removeWidget(floating_button)

            play_mode_index = layout_index(like_layout, play_mode_button)

            if play_mode_index < 0:
                like_layout.addWidget(floating_button)
            else:
                like_layout.insertWidget(play_mode_index + 1, floating_button)

            self.update_floating_lyrics_button_state()
            return

        # 如果三个按钮被拆到了不同的行，就强制创建一个横向按钮行。
        if getattr(self, "bottom_action_row_widget", None) is None:
            self.bottom_action_row_widget = QWidget()
            self.bottom_action_row_widget.setObjectName("bottomActionRowWidget")

            self.bottom_action_row_layout = QHBoxLayout(self.bottom_action_row_widget)
            self.bottom_action_row_layout.setContentsMargins(0, 0, 0, 0)
            self.bottom_action_row_layout.setSpacing(8)
        else:
            row_layout = self.bottom_action_row_widget.layout()

            while row_layout is not None and row_layout.count():
                item = row_layout.takeAt(0)
                widget = item.widget()

                if widget is not None:
                    widget.setParent(None)

            self.bottom_action_row_layout = row_layout

        row_widget = self.bottom_action_row_widget
        row_layout = self.bottom_action_row_layout

        # 找一个最接近收藏/播放模式按钮的纵向父布局，把整行按钮塞回去。
        target_layout = None
        target_index = -1

        for anchor in (play_mode_button, like_button):
            child = anchor
            parent = anchor.parentWidget()

            while parent is not None:
                grand_parent = parent.parentWidget()

                if grand_parent is not None and grand_parent.layout() is not None:
                    layout = grand_parent.layout()
                    index = layout_index(layout, parent)

                    if index >= 0:
                        target_layout = layout
                        target_index = index
                        break

                child = parent
                parent = parent.parentWidget()

            if target_layout is not None:
                break

        if target_layout is None:
            # 兜底：如果实在找不到，就直接放进播放模式按钮所在布局。
            target_layout = play_mode_layout or like_layout
            target_index = -1

        if target_layout is None:
            print("没有找到底部按钮区域布局，桌面歌词按钮仍可用 Ctrl+Shift+D 打开。")
            return

        for button in buttons:
            remove_from_parent_layout(button)
            button.setParent(None)
            row_layout.addWidget(button)

        row_layout.addStretch(1)

        old_parent = row_widget.parentWidget()

        if old_parent is not None and old_parent.layout() is not None:
            old_parent.layout().removeWidget(row_widget)

        row_widget.setParent(None)

        if target_index >= 0 and hasattr(target_layout, "insertWidget"):
            target_layout.insertWidget(target_index, row_widget)
        else:
            target_layout.addWidget(row_widget)

        row_widget.show()
        self.update_floating_lyrics_button_state()
'''


NEW_UPDATE_BUTTON_METHOD = r'''    def update_floating_lyrics_button_state(self) -> None:
        button = getattr(self, "floating_lyrics_button", None)

        if button is None:
            return

        window = getattr(self, "floating_lyrics_window", None)
        is_active = window is not None and window.isVisible()

        button.setText("桌面歌词")

        if is_active:
            button.setStyleSheet(
                "QPushButton#floatingLyricsToggleButton { background: #2f68d8; color: #ffffff; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; font-weight: 700; }"
                "QPushButton#floatingLyricsToggleButton:hover { background: #3d7af0; }"
            )
        else:
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
    return ensure_import_names(
        text,
        "PySide6.QtWidgets",
        [
            "QHBoxLayout",
            "QSizePolicy",
            "QWidget",
        ],
    )


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.4.3 (local music player prototype)",
        "HushPlayer/0.5.4.2 (local music player prototype)",
        "HushPlayer/0.5.4.1 (local music player prototype)",
        "HushPlayer/0.5.4 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.4.4 (local music player prototype)")

    return text


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    if "def install_floating_lyrics_button" not in text:
        raise RuntimeError("没有找到 install_floating_lyrics_button。请先确认桌面歌词按钮功能已经实现。")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = replace_method(text, "install_floating_lyrics_button", NEW_INSTALL_BUTTON_METHOD)
    text = replace_method(text, "update_floating_lyrics_button_state", NEW_UPDATE_BUTTON_METHOD)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.4.4 已强制把 收藏 / 播放模式 / 桌面歌词 做成同一行。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
