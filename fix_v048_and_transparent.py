import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v048_transparent_fix"


IMMERSIVE_CLASS = r"""
class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.transparent_mode = True

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(900, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(46, 34, 46, 34)
        layout.setSpacing(22)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(7)

        self.song_title = ElidedLabel("还没有播放音乐")
        self.song_title.setObjectName("immersiveSongTitle")
        self.song_title.setMinimumWidth(520)

        self.song_artist = ElidedLabel("双击歌曲或右键播放后打开沉浸歌词")
        self.song_artist.setObjectName("immersiveSongArtist")
        self.song_artist.setMinimumWidth(520)

        self.status_label = QLabel("等待播放歌曲")
        self.status_label.setObjectName("immersiveStatus")

        title_box.addWidget(self.song_title)
        title_box.addWidget(self.song_artist)
        title_box.addWidget(self.status_label)

        self.fullscreen_btn = QPushButton("副屏全屏")
        self.fullscreen_btn.setObjectName("immersiveButton")
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self.show_on_best_screen)

        self.window_btn = QPushButton("窗口模式")
        self.window_btn.setObjectName("immersiveButton")
        self.window_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.window_btn.clicked.connect(self.show_windowed)

        self.transparent_btn = QPushButton("切换纯黑")
        self.transparent_btn.setObjectName("immersiveButton")
        self.transparent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transparent_btn.clicked.connect(self.toggle_transparent_mode)

        self.close_btn = QPushButton("退出沉浸")
        self.close_btn.setObjectName("immersiveButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        button_box = QHBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(self.fullscreen_btn)
        button_box.addWidget(self.window_btn)
        button_box.addWidget(self.transparent_btn)
        button_box.addWidget(self.close_btn)

        header.addLayout(title_box, 1)
        header.addLayout(button_box)

        self.lyrics_view = LyricsView()
        self.lyrics_view.setObjectName("immersiveLyricsView")
        self.lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "播放一首歌后，这里会显示沉浸歌词",
        )

        self.footer = QLabel("Esc 退出沉浸 · 默认半透明背景 · 有副屏会优先全屏到副屏")
        self.footer.setObjectName("immersiveFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.footer)

        self.apply_immersive_style()

    def apply_immersive_style(self) -> None:
        if self.transparent_mode:
            background = "rgba(5, 6, 9, 178)"
            footer_text = "Esc 退出沉浸 · 当前：半透明背景 · 有副屏会优先全屏到副屏"
            button_text = "切换纯黑"
        else:
            background = "#050609"
            footer_text = "Esc 退出沉浸 · 当前：纯黑背景 · 有副屏会优先全屏到副屏"
            button_text = "切换半透明"

        if hasattr(self, "footer"):
            self.footer.setText(footer_text)

        if hasattr(self, "transparent_btn"):
            self.transparent_btn.setText(button_text)

        self.setStyleSheet(
            f"QWidget#immersiveLyricsWindow {{ background: {background}; color: #ffffff; font-family: 'Microsoft YaHei UI'; }}"
            "QLabel#immersiveSongTitle { color: #ffffff; font-size: 30px; font-weight: 900; }"
            "QLabel#immersiveSongArtist { color: #aab1bf; font-size: 15px; }"
            "QLabel#immersiveStatus { color: #667085; font-size: 12px; }"
            "QLabel#immersiveFooter { color: #555e6d; font-size: 12px; }"
            "QPushButton#immersiveButton { background: rgba(31, 35, 44, 185); color: #dfe3ec; border: none; border-radius: 12px; padding: 10px 14px; font-size: 13px; }"
            "QPushButton#immersiveButton:hover { background: #2f68d8; color: #ffffff; }"
            "QScrollArea#immersiveLyricsView, QScrollArea#lyricsView { background: transparent; border: none; }"
            "QWidget#lyricsContent { background: transparent; }"
            "QLabel#lyricPlaceholderTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#lyricPlaceholderSubtitle { color: #777e8d; font-size: 15px; }"
            "QLabel#lyricLine { color: #5f6878; font-size: 24px; font-weight: 600; padding: 4px 10px; }"
            "QLabel#lyricLine[lyricState='near'] { color: #c4cad6; font-size: 31px; font-weight: 800; }"
            "QLabel#lyricLine[lyricState='current'] { color: #ffffff; font-size: 48px; font-weight: 950; }"
        )

    def toggle_transparent_mode(self) -> None:
        self.transparent_mode = not self.transparent_mode
        self.apply_immersive_style()

    def show_on_best_screen(self) -> None:
        screens = QApplication.screens()
        target_screen = None

        if len(screens) >= 2:
            target_screen = screens[1]
        elif screens:
            target_screen = screens[0]

        if target_screen:
            self.setGeometry(target_screen.availableGeometry())

        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def show_windowed(self) -> None:
        self.showNormal()
        self.resize(1100, 720)
        self.raise_()
        self.activateWindow()

    def update_song_info(self, title: str, artist_album: str, status: str) -> None:
        self.song_title.setText(title)
        self.song_artist.setText(artist_album)
        self.status_label.setText(status)

    def set_lyrics(self, lyrics: list[tuple[int, str]]) -> None:
        if lyrics:
            self.lyrics_view.set_lyrics(lyrics)
        else:
            self.lyrics_view.set_placeholder(
                "当前歌曲暂无歌词",
                "可以右键歌曲手动绑定歌词，或者重新搜索歌词",
            )

    def update_position(self, position: int, lyrics: list[tuple[int, str]]) -> None:
        self.lyrics_view.update_by_position(position, lyrics)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if getattr(self.main_window, "immersive_lyrics_window", None) is self:
            self.main_window.immersive_lyrics_window = None

        super().closeEvent(event)
"""


def replace_immersive_class(text: str) -> str:
    pattern = re.compile(
        r"\nclass ImmersiveLyricsWindow\(QWidget\):.*?\n\nclass MainWindow\(QMainWindow\):",
        flags=re.S,
    )

    if pattern.search(text):
        return pattern.sub("\n" + IMMERSIVE_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):", text, count=1)

    if "class MainWindow(QMainWindow):" not in text:
        raise RuntimeError("没有找到 MainWindow 类，无法插入沉浸歌词窗口。")

    return text.replace(
        "class MainWindow(QMainWindow):",
        IMMERSIVE_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):",
        1,
    )


def fix_bad_indent(text: str) -> str:
    lines = text.splitlines()
    result = []

    for index, line in enumerate(lines):
        result.append(line)

        if "if self.immersive_lyrics_window is not None:" not in line:
            continue

        if index + 1 >= len(lines):
            continue

        next_line = lines[index + 1]

        if "self.immersive_lyrics_window.update_position(position, self.current_lyrics)" not in next_line:
            continue

        current_indent = line[: len(line) - len(line.lstrip())]
        fixed_next_line = current_indent + "    self.immersive_lyrics_window.update_position(position, self.current_lyrics)"

        result[-1] = line
        lines[index + 1] = fixed_next_line

    return "\n".join(lines) + "\n"


def ensure_version(text: str) -> str:
    old_versions = (
        "HushPlayer/0.4.8 (local music player prototype)",
        "HushPlayer/0.4.7.3 (local music player prototype)",
        "HushPlayer/0.4.7.2 (local music player prototype)",
        "HushPlayer/0.4.7.1 (local music player prototype)",
        "HushPlayer/0.4.7 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.4.8.1 (local music player prototype)")

    return text


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_version(text)
    text = replace_immersive_class(text)
    text = fix_bad_indent(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    try:
        py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
        print("升级完成：v0.4.8.1 已修复沉浸歌词报错，并加入半透明背景切换。")
        print("现在可以运行：python main.py")
    except Exception as error:
        print("语法检查仍未通过，新的错误如下：")
        print(error)
        raise


if __name__ == "__main__":
    main()
