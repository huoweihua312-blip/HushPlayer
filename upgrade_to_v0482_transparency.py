import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0481"


NEW_IMMERSIVE_CLASS = r"""class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.transparent_mode = True

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(900, 620)

        # Windows 下只用 rgba 背景有时看起来仍然像纯黑。
        # 这里同时使用窗口透明度，确保“半透明”和“纯黑”能明显区分。
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

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

        self.footer = QLabel("Esc 退出沉浸 · 当前：半透明背景 · 有副屏会优先全屏到副屏")
        self.footer.setObjectName("immersiveFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.footer)

        self.apply_immersive_style()

    def apply_immersive_style(self) -> None:
        if self.transparent_mode:
            # 关键：setWindowOpacity 才是更明显的“真透明”兜底。
            # 数值越低越透明；0.78 是能明显看到背后，又不至于歌词看不清。
            self.setWindowOpacity(0.78)
            background = "rgba(5, 6, 9, 60)"
            button_background = "rgba(31, 35, 44, 120)"
            footer_text = "Esc 退出沉浸 · 当前：半透明背景 · 如果背后是黑色桌面，看起来仍会偏黑"
            button_text = "切换纯黑"
        else:
            self.setWindowOpacity(1.0)
            background = "#050609"
            button_background = "#1f232c"
            footer_text = "Esc 退出沉浸 · 当前：纯黑背景"
            button_text = "切换半透明"

        self.footer.setText(footer_text)
        self.transparent_btn.setText(button_text)

        self.setStyleSheet(
            f"QWidget#immersiveLyricsWindow {{ background: {background}; color: #ffffff; font-family: 'Microsoft YaHei UI'; }}"
            "QLabel#immersiveSongTitle { color: #ffffff; font-size: 30px; font-weight: 900; }"
            "QLabel#immersiveSongArtist { color: #d0d5df; font-size: 15px; }"
            "QLabel#immersiveStatus { color: #9aa3b2; font-size: 12px; }"
            "QLabel#immersiveFooter { color: #8e96a5; font-size: 12px; }"
            f"QPushButton#immersiveButton {{ background: {button_background}; color: #dfe3ec; border: none; border-radius: 12px; padding: 10px 14px; font-size: 13px; }}"
            "QPushButton#immersiveButton:hover { background: #2f68d8; color: #ffffff; }"
            "QScrollArea#immersiveLyricsView, QScrollArea#lyricsView { background: transparent; border: none; }"
            "QWidget#lyricsContent { background: transparent; }"
            "QLabel#lyricPlaceholderTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#lyricPlaceholderSubtitle { color: #c1c7d2; font-size: 15px; }"
            "QLabel#lyricLine { color: #8a92a3; font-size: 24px; font-weight: 600; padding: 4px 10px; }"
            "QLabel#lyricLine[lyricState='near'] { color: #d3d8e2; font-size: 31px; font-weight: 800; }"
            "QLabel#lyricLine[lyricState='current'] { color: #ffffff; font-size: 48px; font-weight: 950; }"
        )

    def toggle_transparent_mode(self) -> None:
        self.transparent_mode = not self.transparent_mode
        self.apply_immersive_style()

        # 某些显卡/Windows 组合在全屏窗口切透明度时不会立即刷新。
        # 重新 raise/activate 一下，强制刷新合成状态。
        self.raise_()
        self.activateWindow()

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
        self.setWindowOpacity(1.0)

        if getattr(self.main_window, "immersive_lyrics_window", None) is self:
            self.main_window.immersive_lyrics_window = None

        super().closeEvent(event)
"""


def replace_immersive_class(text: str) -> str:
    pattern = re.compile(
        r"\nclass ImmersiveLyricsWindow\(QWidget\):.*?\n\nclass MainWindow\(QMainWindow\):",
        flags=re.S,
    )

    if not pattern.search(text):
        raise RuntimeError("没有找到 ImmersiveLyricsWindow 类。请先确认已经升级到 v0.4.8 或 v0.4.8.1。")

    return pattern.sub("\n" + NEW_IMMERSIVE_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):", text, count=1)


def ensure_version(text: str) -> str:
    old_versions = (
        "HushPlayer/0.4.8.1 (local music player prototype)",
        "HushPlayer/0.4.8 (local music player prototype)",
        "HushPlayer/0.4.7.3 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.4.8.2 (local music player prototype)")

    return text


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.8.2" in text:
        print("当前文件看起来已经升级到 v0.4.8.2 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_version(text)
    text = replace_immersive_class(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
    print("升级完成：v0.4.8.2 已改成更明显的真半透明窗口。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
