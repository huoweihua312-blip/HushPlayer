import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v054"


NEW_FLOATING_CLASS = r'''class FloatingLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.locked = False
        self.font_size = 40
        self.drag_offset = None

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

    def apply_style(self) -> None:
        self.setStyleSheet(
            "QWidget#floatingLyricsWindow { background: transparent; font-family: 'Microsoft YaHei UI'; }"
            f"QLabel#floatingLyricCurrent {{ color: #ffffff; background: transparent; font-size: {self.font_size}px; font-weight: 950; padding: 0px; }}"
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
        close_action = menu.addAction("关闭桌面歌词")

        action = menu.exec(event.globalPos())

        if action == lock_action:
            self.locked = not self.locked
        elif action == bigger_action:
            self.font_size = min(72, self.font_size + 3)
            self.apply_style()
        elif action == smaller_action:
            self.font_size = max(22, self.font_size - 3)
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


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.4 (local music player prototype)",
        "HushPlayer/0.5.3.2 (local music player prototype)",
        "HushPlayer/0.5.3.1 (local music player prototype)",
        "HushPlayer/0.5.3 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.4.1 (local music player prototype)")

    return text


def replace_floating_class(text: str) -> str:
    if "class FloatingLyricsWindow(QWidget):" not in text:
        raise RuntimeError("没有找到 FloatingLyricsWindow。请先确认已经升级到 v0.5.4 桌面歌词。")

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


def patch_immersive_lyric_styles(text: str) -> str:
    replacements = [
        (
            r'"QLabel#lyricLine \{[^"]*\}"',
            '"QLabel#lyricLine { color: rgba(215,222,235,115); font-size: 24px; font-weight: 600; padding: 24px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'near\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'near\'] { color: rgba(236,240,248,185); font-size: 36px; font-weight: 800; padding: 36px 10px; }"',
        ),
        (
            r'"QLabel#lyricLine\[lyricState=\'current\'\] \{[^"]*\}"',
            '"QLabel#lyricLine[lyricState=\'current\'] { color: #ffffff; font-size: 82px; font-weight: 950; padding: 58px 10px; }"',
        ),
    ]

    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text)

        if count == 0:
            print("提示：没有匹配到某条歌词样式，可能之前已经改过：", pattern)

    return text


def patch_immersive_window_min_size(text: str) -> str:
    text = text.replace(
        "        self.setMinimumSize(900, 620)\n",
        "        self.setMinimumSize(1000, 700)\n",
        1,
    )
    return text


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_version(text)
    text = replace_floating_class(text)
    text = patch_immersive_lyric_styles(text)
    text = patch_immersive_window_min_size(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.4.1 极简桌面歌词 + 大字号沉浸歌词 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
