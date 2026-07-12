import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0421"


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

    return text.replace(marker, content + marker, 1)


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.3" in text:
        print("当前文件看起来已经升级到 v0.4.3 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    if "import os" not in text:
        text = text.replace("import hashlib\n", "import os\nimport hashlib\n", 1)

    if "    QMenu,\n" not in text:
        text = replace_once(
            text,
            '''    QMessageBox,
    QPushButton,
''',
            '''    QMessageBox,
    QMenu,
    QPushButton,
''',
            "添加 QMenu 导入",
        )

    text = text.replace(
        "HushPlayer/0.4.2.1 (local music player prototype)",
        "HushPlayer/0.4.3 (local music player prototype)",
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
        music_library_btn.clicked.connect(lambda: self.set_library_view("all"))

        playlist_nav_btn = NavButton("播放列表")
        playlist_nav_btn.clicked.connect(lambda: self.set_library_view("liked"))

        lyrics_nav_btn = NavButton("歌词")
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
        liked_btn.clicked.connect(lambda: self.set_library_view("liked"))

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

        help_text = QLabel("右键歌曲可添加到歌单")
        help_text.setObjectName("sidebarHint")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        layout.addStretch()
        layout.addWidget(settings_nav_btn)

        return sidebar
'''

    new_create_library_panel = r'''    def _create_library_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("libraryPanel")
        panel.setAcceptDrops(True)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()

        title_box = QVBoxLayout()

        page_title = QLabel("音乐库")
        page_title.setObjectName("pageTitle")

        page_subtitle = QLabel("可以导入、搜索，也可以直接拖拽音乐文件或文件夹到窗口。")
        page_subtitle.setObjectName("pageSubtitle")

        title_box.addWidget(page_title)
        title_box.addWidget(page_subtitle)

        import_btn = QPushButton("导入音乐")
        import_btn.setObjectName("primaryButton")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self.import_music_files)

        import_folder_btn = QPushButton("导入文件夹")
        import_folder_btn.setObjectName("secondaryButton")
        import_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_folder_btn.clicked.connect(self.import_music_folder)

        remove_selected_btn = QPushButton("移除选中")
        remove_selected_btn.setObjectName("dangerButton")
        remove_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_selected_btn.clicked.connect(self.remove_selected_song)

        clean_missing_btn = QPushButton("清理失效")
        clean_missing_btn.setObjectName("secondaryButton")
        clean_missing_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clean_missing_btn.clicked.connect(self.clean_missing_songs)

        header_layout.addLayout(title_box)
        header_layout.addStretch()
        header_layout.addWidget(clean_missing_btn)
        header_layout.addWidget(remove_selected_btn)
        header_layout.addWidget(import_folder_btn)
        header_layout.addWidget(import_btn)

        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索歌曲、歌手或专辑")
        self.search_input.textChanged.connect(self.filter_song_list)

        clear_search_btn = QPushButton("清空")
        clear_search_btn.setObjectName("secondaryButton")
        clear_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_search_btn.clicked.connect(self.clear_search)

        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(clear_search_btn)

        self.view_layout = QHBoxLayout()
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_layout.setSpacing(8)

        self.view_layout.addWidget(self._create_view_button("全部歌曲", "all"))
        self.view_layout.addWidget(self._create_view_button("最近播放", "recent_played"))
        self.view_layout.addWidget(self._create_view_button("常听歌曲", "frequent"))
        self.view_layout.addWidget(self._create_view_button("最近添加", "recent_added"))
        self.view_layout.addStretch()

        self.song_list = QListWidget()
        self.song_list.setObjectName("songList")
        self.song_list.setAcceptDrops(False)
        self.song_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.song_list.customContextMenuRequested.connect(self.show_song_context_menu)
        self.song_list.itemClicked.connect(self.select_song)
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)

        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addLayout(self.view_layout)
        layout.addWidget(self.song_list, 1)

        return panel
'''

    context_menu_methods = r'''    def get_song_data_from_item(self, item: QListWidgetItem | None) -> dict | None:
        if item is None:
            return None

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return None

        if song_data.get("demo"):
            return None

        path = self.normalize_song_path(song_data.get("path", ""))

        if not path:
            return None

        return song_data

    def show_song_context_menu(self, position) -> None:
        item = self.song_list.itemAt(position)

        if item is None:
            return

        self.song_list.setCurrentItem(item)

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        menu = QMenu(self)
        menu.setObjectName("songContextMenu")

        play_action = menu.addAction("播放")
        play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))

        menu.addSeparator()

        if self.is_song_liked(song_path):
            like_action = menu.addAction("取消收藏")
        else:
            like_action = menu.addAction("添加到我喜欢")

        like_action.triggered.connect(lambda checked=False, selected_item=item: self.toggle_like_selected_song(selected_item))

        add_to_playlist_action = menu.addAction("添加到歌单")
        add_to_playlist_action.triggered.connect(self.add_current_song_to_playlist)

        if self.current_library_view == "liked":
            remove_from_playlist_action = menu.addAction("从我喜欢移除")
            remove_from_playlist_action.triggered.connect(self.remove_current_song_from_current_playlist)
        elif self.current_library_view.startswith("playlist:"):
            remove_from_playlist_action = menu.addAction("从当前歌单移除")
            remove_from_playlist_action.triggered.connect(self.remove_current_song_from_current_playlist)

        menu.addSeparator()

        open_folder_action = menu.addAction("打开文件夹")
        open_folder_action.triggered.connect(self.open_selected_song_folder)

        song_info_action = menu.addAction("查看歌曲信息")
        song_info_action.triggered.connect(self.show_selected_song_info)

        menu.addSeparator()

        remove_from_library_action = menu.addAction("从音乐库移除")
        remove_from_library_action.triggered.connect(self.remove_selected_song)

        menu.exec(self.song_list.mapToGlobal(position))

    def toggle_like_selected_song(self, item: QListWidgetItem | None) -> None:
        song_data = self.get_song_data_from_item(item)

        if not song_data:
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            return

        liked_songs = self.get_liked_song_paths()

        if song_path in liked_songs:
            liked_songs.remove(song_path)
            print("已取消收藏：", song_path)
        else:
            liked_songs.append(song_path)
            print("已加入我喜欢：", song_path)

        self.save_playlists()

        if self.current_song_path and self.normalize_song_path(self.current_song_path) == song_path:
            self.update_like_button()

        if self.current_library_view == "liked":
            self.filter_song_list(self.search_input.text())

    def open_selected_song_folder(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        path = Path(song_path)

        if not path.exists():
            QMessageBox.warning(self, "文件不存在", "这个音乐文件已经不存在。")
            return

        try:
            os.startfile(str(path.parent))
        except Exception as error:
            QMessageBox.warning(self, "打开失败", str(error))

    def show_selected_song_info(self) -> None:
        item = self.song_list.currentItem()
        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")
        path = self.normalize_song_path(song_data.get("path", ""))

        stats = self.song_stats.get(
            path,
            {
                "play_count": 0,
                "total_listen_time": 0,
                "last_played": 0,
            },
        )

        play_count = int(stats.get("play_count", 0))
        total_time = self.format_listen_time(int(stats.get("total_listen_time", 0)))
        liked_text = "是" if self.is_song_liked(path) else "否"

        info = (
            f"歌曲：{title}\\n"
            f"歌手：{artist}\\n"
            f"专辑：{album}\\n"
            f"已收藏：{liked_text}\\n"
            f"播放次数：{play_count}\\n"
            f"累计时长：{total_time}\\n\\n"
            f"文件路径：\\n{path}"
        )

        QMessageBox.information(self, "歌曲信息", info)

'''

    text = replace_method(text, "_create_sidebar", new_create_sidebar)
    text = replace_method(text, "_create_library_panel", new_create_library_panel)

    if "def show_song_context_menu" not in text:
        text = insert_before(
            text,
            '''    def closeEvent(self, event) -> None:
''',
            context_menu_methods,
            "插入右键菜单方法",
        )

    style_marker = '''        QPushButton#sidebarMiniButton:hover {
            background: #2a303c;
            color: #ffffff;
        }
'''

    extra_styles = '''        QLabel#sidebarHint {
            color: #68707f;
            font-size: 11px;
            padding: 2px 4px;
        }

        QMenu#songContextMenu {
            background: #181a20;
            color: #dfe3ec;
            border: 1px solid #303541;
            border-radius: 10px;
            padding: 6px;
        }

        QMenu#songContextMenu::item {
            padding: 8px 24px;
            border-radius: 7px;
        }

        QMenu#songContextMenu::item:selected {
            background: #2f68d8;
            color: #ffffff;
        }

        QMenu#songContextMenu::separator {
            height: 1px;
            background: #303541;
            margin: 6px 8px;
        }
'''

    if "QMenu#songContextMenu" not in text:
        text = replace_once(
            text,
            style_marker,
            style_marker + "\n" + extra_styles,
            "添加右键菜单样式",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.3 右键菜单已加入，左侧歌单按钮已简化。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()