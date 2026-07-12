import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v046"


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, content.rstrip() + "\n\n" + marker, 1)


def add_line_after_unique(text: str, needle: str, new_line: str) -> str:
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


def add_sync_after_lyrics_set(text: str) -> str:
    lines = text.splitlines()
    result = []

    for index, line in enumerate(lines):
        result.append(line)

        if "self.lyrics_view.set_lyrics(self.current_lyrics)" not in line:
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ""

        if "self.sync_full_lyrics_from_current()" in next_line:
            continue

        indent = line[: len(line) - len(line.lstrip())]
        result.append(indent + "self.sync_full_lyrics_from_current()")

    return "\n".join(result) + "\n"


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.7" in text:
        print("当前文件看起来已经升级到 v0.4.7 了，不需要重复升级。")
        return

    if "def bind_selected_song_lyrics" not in text or "def start_lyrics_worker" not in text:
        raise RuntimeError("没有找到 v0.4.6 的歌词绑定/后台歌词代码。请先确认已经升级到 v0.4.6。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.6 (local music player prototype)",
        "HushPlayer/0.4.7 (local music player prototype)",
    )

    if "    QStackedWidget,\n" not in text:
        text = text.replace(
            "    QSlider,\n",
            "    QSlider,\n    QStackedWidget,\n",
            1,
        )

    old_body = '''        sidebar = self._create_sidebar()
        library_panel = self._create_library_panel()
        now_playing_panel = self._create_now_playing_panel()

        body_layout.addWidget(sidebar)
        body_layout.addWidget(library_panel, 1)
        body_layout.addWidget(now_playing_panel)
'''

    new_body = '''        sidebar = self._create_sidebar()
        library_panel = self._create_library_panel()
        full_lyrics_page = self._create_full_lyrics_page()
        now_playing_panel = self._create_now_playing_panel()

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        self.content_stack.addWidget(library_panel)
        self.content_stack.addWidget(full_lyrics_page)

        body_layout.addWidget(sidebar)
        body_layout.addWidget(self.content_stack, 1)
        body_layout.addWidget(now_playing_panel)
'''

    if old_body in text:
        text = text.replace(old_body, new_body, 1)
    elif "self.content_stack = QStackedWidget()" not in text:
        raise RuntimeError("没有找到主界面 body_layout 的替换位置。")

    page_methods = r'''    def _create_full_lyrics_page(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("fullLyricsPage")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(44, 34, 44, 34)
        layout.setSpacing(18)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(7)

        page_title = QLabel("歌词")
        page_title.setObjectName("fullLyricsPageTitle")

        page_subtitle = QLabel("这里显示正在播放歌曲的歌词。单击音乐库里的其他歌不会影响这个页面。")
        page_subtitle.setObjectName("fullLyricsPageSubtitle")

        self.full_lyrics_title = ElidedLabel("还没有播放音乐")
        self.full_lyrics_title.setObjectName("fullLyricsSongTitle")
        self.full_lyrics_title.setMinimumWidth(360)

        self.full_lyrics_artist = ElidedLabel("双击歌曲或右键播放后，这里会显示正在播放的歌词")
        self.full_lyrics_artist.setObjectName("fullLyricsArtist")
        self.full_lyrics_artist.setMinimumWidth(360)

        self.full_lyrics_status = QLabel("等待播放歌曲")
        self.full_lyrics_status.setObjectName("fullLyricsStatus")
        self.full_lyrics_status.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title_box.addWidget(page_title)
        title_box.addWidget(page_subtitle)
        title_box.addSpacing(8)
        title_box.addWidget(self.full_lyrics_title)
        title_box.addWidget(self.full_lyrics_artist)
        title_box.addWidget(self.full_lyrics_status)

        back_btn = QPushButton("返回音乐库")
        back_btn.setObjectName("secondaryButton")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.show_library_page)

        header_layout.addLayout(title_box, 1)
        header_layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignTop)

        self.full_lyrics_view = LyricsView()
        self.full_lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "双击一首歌播放，然后点击左侧“歌词”查看大歌词页面",
        )

        layout.addLayout(header_layout)
        layout.addWidget(self.full_lyrics_view, 1)

        return panel

    def show_library_page(self) -> None:
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentIndex(0)

    def show_liked_playlist_page(self) -> None:
        self.show_library_page()
        self.set_library_view("liked")

    def show_full_lyrics_page(self) -> None:
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentIndex(1)

        self.refresh_full_lyrics_page()

    def find_song_data_by_path(self, song_path: str | None) -> dict | None:
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path:
            return None

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            item_path = self.normalize_song_path(song_data.get("path", ""))

            if item_path == normalized_path:
                return song_data

        return None

    def refresh_full_lyrics_page(self) -> None:
        if not hasattr(self, "full_lyrics_view"):
            return

        playing_path = self.normalize_song_path(self.current_song_path)

        if not playing_path:
            self.full_lyrics_title.setText("还没有播放音乐")
            self.full_lyrics_artist.setText("双击歌曲或右键播放后，这里会显示正在播放的歌词")
            self.full_lyrics_status.setText("等待播放歌曲")
            self.full_lyrics_view.set_placeholder(
                "还没有正在播放的歌词",
                "双击一首歌播放，然后点击左侧“歌词”查看大歌词页面",
            )
            return

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
        else:
            title = Path(playing_path).stem
            artist = "未知艺术家"
            album = "未知专辑"

        self.full_lyrics_title.setText(title)
        self.full_lyrics_artist.setText(f"{artist} · {album}")

        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if displayed_path == playing_path and self.current_lyrics:
            self.sync_full_lyrics_from_current()
            return

        self.full_lyrics_status.setText("正在加载正在播放歌曲的歌词")
        self.full_lyrics_view.set_placeholder(
            "正在加载歌词",
            "优先手动绑定歌词、本地歌词，其次缓存和联网歌词",
        )

        self.load_lyrics_for_song(
            file_path=playing_path,
            title=title,
            artist=artist,
        )

    def sync_full_lyrics_from_current(self) -> None:
        if not hasattr(self, "full_lyrics_view"):
            return

        playing_path = self.normalize_song_path(self.current_song_path)
        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if not playing_path:
            return

        if displayed_path != playing_path:
            return

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
            self.full_lyrics_title.setText(title)
            self.full_lyrics_artist.setText(f"{artist} · {album}")

        if self.current_lyrics:
            self.full_lyrics_view.set_lyrics(self.current_lyrics)
            self.full_lyrics_view.update_by_position(
                self.media_player.position(),
                self.current_lyrics,
            )
            self.full_lyrics_status.setText("正在显示播放中的歌词")
        else:
            self.full_lyrics_view.set_placeholder(
                "当前歌曲暂无歌词",
                "可以右键歌曲手动绑定歌词，或者重新搜索歌词",
            )
            self.full_lyrics_status.setText("当前歌曲暂无歌词")
'''

    if "def _create_full_lyrics_page" not in text:
        text = insert_before(
            text,
            '''    def _create_sidebar(self) -> QFrame:
''',
            page_methods,
            "插入完整歌词页方法",
        )

    new_create_sidebar = r'''    def _create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)

        title = QLabel("HushPlayer")
        title.setObjectName("appTitle")

        subtitle = QLabel("Local Music Player")
        subtitle.setObjectName("appSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(22)

        music_library_btn = NavButton("音乐库", active=True)
        music_library_btn.clicked.connect(self.show_library_page)

        playlist_nav_btn = NavButton("播放列表")
        playlist_nav_btn.clicked.connect(self.show_liked_playlist_page)

        lyrics_nav_btn = NavButton("歌词")
        lyrics_nav_btn.clicked.connect(self.show_full_lyrics_page)

        settings_nav_btn = NavButton("设置")

        layout.addWidget(music_library_btn)
        layout.addWidget(playlist_nav_btn)
        layout.addWidget(lyrics_nav_btn)

        layout.addSpacing(12)

        playlist_title = QLabel("歌单")
        playlist_title.setObjectName("sidebarSectionTitle")
        layout.addWidget(playlist_title)

        liked_btn = QPushButton("♥ 我喜欢")
        liked_btn.setObjectName("playlistSidebarButton")
        liked_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        liked_btn.setProperty("active", self.current_library_view == "liked")
        liked_btn.clicked.connect(self.show_liked_playlist_page)

        self.view_buttons["liked"] = liked_btn
        layout.addWidget(liked_btn)

        self.sidebar_playlist_box = QFrame()
        self.sidebar_playlist_box.setObjectName("sidebarPlaylistBox")

        self.sidebar_playlist_layout = QVBoxLayout(self.sidebar_playlist_box)
        self.sidebar_playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_playlist_layout.setSpacing(7)

        layout.addWidget(self.sidebar_playlist_box)

        self.refresh_playlist_view_buttons()

        layout.addSpacing(8)

        new_playlist_btn = QPushButton("+ 新建歌单")
        new_playlist_btn.setObjectName("sidebarWideButton")
        new_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_playlist_btn.clicked.connect(self.create_new_playlist)

        edit_row = QHBoxLayout()
        edit_row.setContentsMargins(0, 0, 0, 0)
        edit_row.setSpacing(8)

        rename_playlist_btn = QPushButton("重命名")
        rename_playlist_btn.setObjectName("sidebarMiniButton")
        rename_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_playlist_btn.clicked.connect(self.rename_current_playlist)

        delete_playlist_btn = QPushButton("删除")
        delete_playlist_btn.setObjectName("sidebarMiniButton")
        delete_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_playlist_btn.clicked.connect(self.delete_current_playlist)

        edit_row.addWidget(rename_playlist_btn)
        edit_row.addWidget(delete_playlist_btn)

        layout.addWidget(new_playlist_btn)
        layout.addLayout(edit_row)

        help_text = QLabel("右键歌曲可添加到歌单、绑定歌词或重新搜索封面")
        help_text.setObjectName("sidebarHint")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        layout.addStretch()
        layout.addWidget(settings_nav_btn)

        return sidebar
'''

    text = replace_method(text, "_create_sidebar", new_create_sidebar)

    if "full_lyrics_status" in text and "def set_lyrics_status" in text:
        old_status_snippet = '''        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText(f"歌词：{message}")

        QApplication.processEvents()
'''
        new_status_snippet = '''        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText(f"歌词：{message}")

        if hasattr(self, "full_lyrics_status"):
            self.full_lyrics_status.setText(message)

        QApplication.processEvents()
'''
        if old_status_snippet in text and "self.full_lyrics_status.setText(message)" not in text:
            text = text.replace(old_status_snippet, new_status_snippet, 1)

    text = add_sync_after_lyrics_set(text)

    # 只要右侧歌词随着播放进度更新，大歌词页也一起更新。v0.4.5 已经保证只有“显示的是正在播放歌曲歌词”时才会滚动。
    text = add_line_after_unique(
        text,
        "self.lyrics_view.update_by_position(position, self.current_lyrics)",
        '''if hasattr(self, "full_lyrics_view"):
                self.full_lyrics_view.update_by_position(position, self.current_lyrics)''',
    )

    if "QFrame#fullLyricsPage" not in text:
        style_marker = '''        QFrame#libraryPanel {
            background: #181a20;
        }
'''
        full_lyrics_style = '''        QFrame#fullLyricsPage {
            background: #181a20;
        }

        QLabel#fullLyricsPageTitle {
            color: #ffffff;
            font-size: 30px;
            font-weight: 800;
        }

        QLabel#fullLyricsPageSubtitle {
            color: #8d93a1;
            font-size: 13px;
        }

        QLabel#fullLyricsSongTitle {
            color: #ffffff;
            font-size: 26px;
            font-weight: 800;
        }

        QLabel#fullLyricsArtist {
            color: #aab1bf;
            font-size: 14px;
        }

        QLabel#fullLyricsStatus {
            color: #6f7786;
            font-size: 12px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine {
            font-size: 20px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine[lyricState="near"] {
            font-size: 24px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine[lyricState="current"] {
            font-size: 34px;
            font-weight: 900;
        }
'''
        text = replace_once(
            text,
            style_marker,
            style_marker + "\n" + full_lyrics_style,
            "添加完整歌词页样式",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.7 单独歌词页面已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
