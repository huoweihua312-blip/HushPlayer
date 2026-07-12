import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0532"


FLOATING_LYRICS_CLASS = r'''class FloatingLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.locked = False
        self.font_size = 28
        self.drag_offset = None

        self.setWindowTitle("HushPlayer 桌面歌词")
        self.setObjectName("floatingLyricsWindow")
        self.setMinimumSize(620, 150)
        self.resize(860, 180)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self.panel = QFrame()
        self.panel.setObjectName("floatingLyricsPanel")

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(26, 18, 26, 18)
        panel_layout.setSpacing(8)

        self.prev_label = QLabel("")
        self.prev_label.setObjectName("floatingLyricPrev")
        self.prev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_label.setWordWrap(True)

        self.current_label = QLabel("桌面歌词已开启")
        self.current_label.setObjectName("floatingLyricCurrent")
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_label.setWordWrap(True)

        self.next_label = QLabel("播放一首有歌词的歌后，这里会自动显示")
        self.next_label.setObjectName("floatingLyricNext")
        self.next_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_label.setWordWrap(True)

        panel_layout.addWidget(self.prev_label)
        panel_layout.addWidget(self.current_label)
        panel_layout.addWidget(self.next_label)

        layout.addWidget(self.panel)

        self.apply_style()

    def apply_style(self) -> None:
        prev_size = max(12, self.font_size - 10)
        next_size = max(12, self.font_size - 10)

        self.setStyleSheet(
            "QWidget#floatingLyricsWindow { background: transparent; font-family: 'Microsoft YaHei UI'; }"
            "QFrame#floatingLyricsPanel { background: rgba(5, 6, 9, 175); border: 1px solid rgba(255,255,255,35); border-radius: 24px; }"
            f"QLabel#floatingLyricPrev {{ color: rgba(230,235,245,120); font-size: {prev_size}px; font-weight: 600; }}"
            f"QLabel#floatingLyricCurrent {{ color: #ffffff; font-size: {self.font_size}px; font-weight: 900; }}"
            f"QLabel#floatingLyricNext {{ color: rgba(230,235,245,135); font-size: {next_size}px; font-weight: 600; }}"
        )

    def set_lines(self, previous_line: str, current_line: str, next_line: str) -> None:
        self.prev_label.setText(previous_line or "")
        self.current_label.setText(current_line or "暂无歌词")
        self.next_label.setText(next_line or "")

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        if self.locked:
            lock_action = menu.addAction("解锁位置")
        else:
            lock_action = menu.addAction("锁定位置")

        bigger_action = menu.addAction("放大歌词")
        smaller_action = menu.addAction("缩小歌词")
        close_action = menu.addAction("关闭桌面歌词")

        action = menu.exec(event.globalPos())

        if action == lock_action:
            self.locked = not self.locked
        elif action == bigger_action:
            self.font_size = min(54, self.font_size + 2)
            self.apply_style()
        elif action == smaller_action:
            self.font_size = max(18, self.font_size - 2)
            self.apply_style()
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

        super().closeEvent(event)
'''


FLOATING_LYRICS_METHODS = r'''    def install_floating_lyrics_feature(self) -> None:
        if not hasattr(self, "floating_lyrics_window"):
            self.floating_lyrics_window = None

        if not hasattr(self, "floating_lyrics_shortcut"):
            self.floating_lyrics_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
            self.floating_lyrics_shortcut.activated.connect(self.toggle_floating_lyrics)

        if not hasattr(self, "floating_lyrics_timer"):
            self.floating_lyrics_timer = QTimer(self)
            self.floating_lyrics_timer.timeout.connect(self.sync_floating_lyrics)
            self.floating_lyrics_timer.start(220)

    def toggle_floating_lyrics(self) -> None:
        if self.floating_lyrics_window is not None and self.floating_lyrics_window.isVisible():
            self.floating_lyrics_window.close()
            self.floating_lyrics_window = None
            return

        self.show_floating_lyrics()

    def show_floating_lyrics(self) -> None:
        if self.floating_lyrics_window is None:
            self.floating_lyrics_window = FloatingLyricsWindow(self)

        self.sync_floating_lyrics()

        screen = QApplication.primaryScreen()

        if screen:
            geometry = screen.availableGeometry()
            width = self.floating_lyrics_window.width()
            height = self.floating_lyrics_window.height()
            x = geometry.x() + (geometry.width() - width) // 2
            y = geometry.y() + geometry.height() - height - 80
            self.floating_lyrics_window.move(x, y)

        self.floating_lyrics_window.show()
        self.floating_lyrics_window.raise_()

    def get_lyric_context_by_position(self, position: int, lyrics: list[tuple[int, str]]) -> tuple[str, str, str]:
        if not lyrics:
            return "", "暂无歌词", ""

        current_index = 0

        for index, (start_time, line_text) in enumerate(lyrics):
            if position >= start_time:
                current_index = index
            else:
                break

        previous_line = ""
        current_line = lyrics[current_index][1]
        next_line = ""

        if current_index > 0:
            previous_line = lyrics[current_index - 1][1]

        if current_index + 1 < len(lyrics):
            next_line = lyrics[current_index + 1][1]

        return previous_line, current_line, next_line

    def sync_floating_lyrics(self) -> None:
        window = getattr(self, "floating_lyrics_window", None)

        if window is None or not window.isVisible():
            return

        current_song_path = self.normalize_song_path(getattr(self, "current_song_path", ""))
        displayed_lyrics_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if not current_song_path:
            window.set_lines("", "还没有播放音乐", "播放一首歌后，这里会显示桌面歌词")
            return

        if displayed_lyrics_path != current_song_path or not getattr(self, "current_lyrics", None):
            title, artist_album, status = self.get_playing_song_display_data()
            window.set_lines("", title, "当前歌曲暂无同步歌词")
            return

        position = self.media_player.position()
        previous_line, current_line, next_line = self.get_lyric_context_by_position(
            position,
            self.current_lyrics,
        )
        window.set_lines(previous_line, current_line, next_line)
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
    text = ensure_import_names(
        text,
        "PySide6.QtWidgets",
        [
            "QApplication",
            "QFrame",
            "QMenu",
            "QWidget",
        ],
    )

    text = ensure_import_names(
        text,
        "PySide6.QtGui",
        [
            "QKeySequence",
            "QShortcut",
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
        "HushPlayer/0.5.3.2 (local music player prototype)",
        "HushPlayer/0.5.3.1 (local music player prototype)",
        "HushPlayer/0.5.3 (local music player prototype)",
        "HushPlayer/0.5.2 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.4 (local music player prototype)")

    return text


def insert_floating_class(text: str) -> str:
    if "class FloatingLyricsWindow(QWidget):" in text:
        return text

    markers = [
        "\nclass PlayQueueDialog(QDialog):",
        "\nclass SettingsDialog(QDialog):",
        "\nclass ImmersiveLyricsWindow(QWidget):",
        "\nclass MainWindow(QMainWindow):",
    ]

    for marker in markers:
        if marker in text:
            return text.replace(marker, "\n" + FLOATING_LYRICS_CLASS.strip() + "\n\n" + marker.lstrip("\n"), 1)

    raise RuntimeError("没有找到插入桌面歌词窗口类的位置。")


def insert_before_method(text: str, method_name: str, content: str) -> str:
    marker = f"\n    def {method_name}("

    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{method_name}")

    return text.replace(marker, "\n" + content.rstrip() + "\n" + marker, 1)


def insert_methods(text: str) -> str:
    if "def install_floating_lyrics_feature" in text:
        return text

    markers = [
        "install_playlist_button_hook",
        "install_settings_button_hook",
        "show_full_lyrics_page",
        "show_play_queue",
        "toggle_play_pause",
    ]

    for method_name in markers:
        if f"\n    def {method_name}(" in text:
            return insert_before_method(text, method_name, FLOATING_LYRICS_METHODS)

    raise RuntimeError("没有找到插入桌面歌词方法的位置。")


def patch_init_call(text: str) -> str:
    if "self.install_floating_lyrics_feature" in text:
        return text

    preferred_markers = [
        "        QTimer.singleShot(0, self.install_playlist_button_hook)\n",
        "        QTimer.singleShot(0, self.install_settings_button_hook)\n",
    ]

    for marker in preferred_markers:
        if marker in text:
            return text.replace(
                marker,
                marker + "        QTimer.singleShot(0, self.install_floating_lyrics_feature)\n",
                1,
            )

    pattern = re.compile(
        r"(\n    def __init__\(self.*?\):\n.*?)(\n    def )",
        flags=re.S,
    )
    match = pattern.search(text)

    if not match:
        raise RuntimeError("没有找到 MainWindow.__init__，无法安装桌面歌词功能。")

    init_text = match.group(1).rstrip() + "\n\n        QTimer.singleShot(0, self.install_floating_lyrics_feature)\n"
    return text[:match.start(1)] + init_text + text[match.start(2):]


def patch_context_menu(text: str) -> str:
    if "打开/关闭桌面歌词" in text:
        return text

    marker = "play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))"

    if marker not in text:
        print("没有找到右键菜单播放按钮连接，跳过右键菜单里的桌面歌词入口。")
        return text

    lines = text.splitlines()
    result = []
    inserted = False

    for line in lines:
        result.append(line)

        if marker in line and not inserted:
            indent = line[: len(line) - len(line.lstrip())]
            result.extend([
                "",
                f'{indent}floating_lyrics_action = menu.addAction("打开/关闭桌面歌词")',
                f"{indent}floating_lyrics_action.triggered.connect(self.toggle_floating_lyrics)",
            ])
            inserted = True

    return "\n".join(result) + "\n"


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = insert_floating_class(text)
    text = insert_methods(text)
    text = patch_init_call(text)
    text = patch_context_menu(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.4 桌面悬浮歌词已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
