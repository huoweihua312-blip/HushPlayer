import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0473"


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, content.rstrip() + "\n\n" + marker, 1)


def insert_after_line_containing(text: str, needle: str, new_line: str) -> str:
    lines = text.splitlines()
    result = []
    changed = False

    for index, line in enumerate(lines):
        result.append(line)

        if needle not in line:
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ""

        if new_line.strip() in next_line:
            continue

        indent = line[: len(line) - len(line.lstrip())]
        result.append(indent + new_line.strip())
        changed = True

    if not changed:
        return text

    return "\n".join(result) + "\n"


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.8" in text:
        print("当前文件看起来已经升级到 v0.4.8 了，不需要重复升级。")
        return

    if "def _create_full_lyrics_page" not in text or "def sync_full_lyrics_from_current" not in text:
        raise RuntimeError("没有找到 v0.4.7 的单独歌词页面代码。请先确认已经升级到 v0.4.7.3。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    for old_version in (
        "HushPlayer/0.4.7.3 (local music player prototype)",
        "HushPlayer/0.4.7.2 (local music player prototype)",
        "HushPlayer/0.4.7.1 (local music player prototype)",
        "HushPlayer/0.4.7 (local music player prototype)",
    ):
        text = text.replace(old_version, "HushPlayer/0.4.8 (local music player prototype)")

    immersive_class = r'''class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(900, 620)

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

        self.close_btn = QPushButton("退出沉浸")
        self.close_btn.setObjectName("immersiveButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        button_box = QHBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(self.fullscreen_btn)
        button_box.addWidget(self.window_btn)
        button_box.addWidget(self.close_btn)

        header.addLayout(title_box, 1)
        header.addLayout(button_box)

        self.lyrics_view = LyricsView()
        self.lyrics_view.setObjectName("immersiveLyricsView")
        self.lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "播放一首歌后，这里会显示沉浸歌词",
        )

        footer = QLabel("Esc 退出沉浸 · 如果有副屏，会优先全屏到副屏")
        footer.setObjectName("immersiveFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(footer)

        self.setStyleSheet(
            "QWidget#immersiveLyricsWindow { background: #050609; color: #ffffff; font-family: 'Microsoft YaHei UI'; }"
            "QLabel#immersiveSongTitle { color: #ffffff; font-size: 30px; font-weight: 900; }"
            "QLabel#immersiveSongArtist { color: #aab1bf; font-size: 15px; }"
            "QLabel#immersiveStatus { color: #667085; font-size: 12px; }"
            "QLabel#immersiveFooter { color: #555e6d; font-size: 12px; }"
            "QPushButton#immersiveButton { background: #1f232c; color: #dfe3ec; border: none; border-radius: 12px; padding: 10px 14px; font-size: 13px; }"
            "QPushButton#immersiveButton:hover { background: #2f68d8; color: #ffffff; }"
            "QScrollArea#immersiveLyricsView, QScrollArea#lyricsView { background: transparent; border: none; }"
            "QWidget#lyricsContent { background: transparent; }"
            "QLabel#lyricPlaceholderTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#lyricPlaceholderSubtitle { color: #777e8d; font-size: 15px; }"
            "QLabel#lyricLine { color: #4f5868; font-size: 24px; font-weight: 600; padding: 4px 10px; }"
            "QLabel#lyricLine[lyricState='near'] { color: #aab1bf; font-size: 31px; font-weight: 800; }"
            "QLabel#lyricLine[lyricState='current'] { color: #ffffff; font-size: 48px; font-weight: 950; }"
        )

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
'''

    if "class ImmersiveLyricsWindow(QWidget):" not in text:
        text = insert_before(
            text,
            "class MainWindow(QMainWindow):",
            immersive_class,
            "插入沉浸歌词窗口类",
        )

    if "self.immersive_lyrics_window" not in text:
        text = replace_once(
            text,
            '''        self.displayed_lyrics_song_path: str | None = None
''',
            '''        self.displayed_lyrics_song_path: str | None = None
        self.immersive_lyrics_window: ImmersiveLyricsWindow | None = None
''',
            "添加沉浸歌词窗口状态",
        )

    immersive_methods = r'''    def open_immersive_lyrics_window(self) -> None:
        if self.immersive_lyrics_window is None:
            self.immersive_lyrics_window = ImmersiveLyricsWindow(self)

        self.sync_immersive_lyrics()
        self.immersive_lyrics_window.show_on_best_screen()

    def get_playing_song_display_data(self) -> tuple[str, str, str]:
        playing_path = self.normalize_song_path(self.current_song_path)

        if not playing_path:
            return "还没有播放音乐", "双击歌曲或右键播放后打开沉浸歌词", "等待播放歌曲"

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
        else:
            title = Path(playing_path).stem
            artist = "未知艺术家"
            album = "未知专辑"

        if hasattr(self, "lyrics_status_label"):
            status = self.lyrics_status_label.text().replace("歌词：", "").strip()
        else:
            status = "歌词状态未知"

        return str(title), f"{artist} · {album}", status or "歌词状态未知"

    def sync_immersive_lyrics(self) -> None:
        if self.immersive_lyrics_window is None:
            return

        title, artist_album, status = self.get_playing_song_display_data()
        self.immersive_lyrics_window.update_song_info(title, artist_album, status)

        playing_path = self.normalize_song_path(self.current_song_path)
        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if playing_path and displayed_path == playing_path and self.current_lyrics:
            self.immersive_lyrics_window.set_lyrics(self.current_lyrics)
            self.immersive_lyrics_window.update_position(
                self.media_player.position(),
                self.current_lyrics,
            )
        else:
            self.immersive_lyrics_window.set_lyrics([])
'''

    if "def open_immersive_lyrics_window" not in text:
        text = insert_before(
            text,
            '''    def _create_full_lyrics_page(self) -> QFrame:
''',
            immersive_methods,
            "插入沉浸歌词控制方法",
        )

    old_button_block = '''        back_btn = QPushButton("返回音乐库")
        back_btn.setObjectName("secondaryButton")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.show_library_page)

        header_layout.addLayout(title_box, 1)
        header_layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignTop)
'''

    new_button_block = '''        immersive_btn = QPushButton("打开沉浸歌词")
        immersive_btn.setObjectName("primaryButton")
        immersive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        immersive_btn.clicked.connect(self.open_immersive_lyrics_window)

        back_btn = QPushButton("返回音乐库")
        back_btn.setObjectName("secondaryButton")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.show_library_page)

        button_box = QVBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(immersive_btn)
        button_box.addWidget(back_btn)

        header_layout.addLayout(title_box, 1)
        header_layout.addLayout(button_box)
'''

    if old_button_block in text:
        text = text.replace(old_button_block, new_button_block, 1)
    elif "打开沉浸歌词" not in text:
        raise RuntimeError("没有找到大歌词页按钮区域。")

    old_status_snippet = '''        if hasattr(self, "side_lyrics_status_value"):
            self.side_lyrics_status_value.setText(message)

        QApplication.processEvents()
'''

    new_status_snippet = '''        if hasattr(self, "side_lyrics_status_value"):
            self.side_lyrics_status_value.setText(message)

        self.sync_immersive_lyrics()

        QApplication.processEvents()
'''

    if old_status_snippet in text:
        text = text.replace(old_status_snippet, new_status_snippet, 1)

    text = insert_after_line_containing(
        text,
        'self.full_lyrics_status.setText("正在显示播放中的歌词")',
        "self.sync_immersive_lyrics()",
    )
    text = insert_after_line_containing(
        text,
        'self.full_lyrics_status.setText("当前歌曲暂无歌词")',
        "self.sync_immersive_lyrics()",
    )

    text = insert_after_line_containing(
        text,
        "self.full_lyrics_view.update_by_position(position, self.current_lyrics)",
        '''if self.immersive_lyrics_window is not None:
                self.immersive_lyrics_window.update_position(position, self.current_lyrics)''',
    )

    text = insert_after_line_containing(
        text,
        "print(\"已切换播放器当前歌曲：\", title, \"-\", artist)",
        "self.sync_immersive_lyrics()",
    )

    if "self.immersive_lyrics_window.close()" not in text:
        text = replace_once(
            text,
            '''    def closeEvent(self, event) -> None:
        self.flush_current_listen_time()
        self.save_song_stats()
        super().closeEvent(event)
''',
            '''    def closeEvent(self, event) -> None:
        self.flush_current_listen_time()
        self.save_song_stats()

        if self.immersive_lyrics_window is not None:
            self.immersive_lyrics_window.close()
            self.immersive_lyrics_window = None

        super().closeEvent(event)
''',
            "主窗口关闭时关闭沉浸歌词窗口",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.8 沉浸式副屏歌词窗口已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
