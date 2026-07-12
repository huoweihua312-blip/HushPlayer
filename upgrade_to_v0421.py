import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v042"


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


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.2.1" in text:
        print("当前文件看起来已经升级到 v0.4.2.1 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.2 (local music player prototype)",
        "HushPlayer/0.4.2.1 (local music player prototype)",
    )

    new_refresh_playlist_view_buttons = r'''    def refresh_playlist_view_buttons(self) -> None:
        if not hasattr(self, "sidebar_playlist_layout"):
            return

        for button in getattr(self, "custom_view_buttons", []):
            self.sidebar_playlist_layout.removeWidget(button)
            button.deleteLater()

        self.custom_view_buttons = []

        for view_name in list(self.view_buttons.keys()):
            if view_name.startswith("playlist:"):
                self.view_buttons.pop(view_name, None)

        for playlist_id in self.get_custom_playlist_ids():
            playlist_name = self.get_playlist_name(playlist_id)
            view_name = f"playlist:{playlist_id}"

            button = QPushButton(playlist_name)
            button.setObjectName("playlistSidebarButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("active", view_name == self.current_library_view)
            button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))

            self.sidebar_playlist_layout.addWidget(button)
            self.custom_view_buttons.append(button)
            self.view_buttons[view_name] = button

        self.update_view_buttons()
'''

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

        add_to_playlist_btn = QPushButton("添加当前歌曲到歌单")
        add_to_playlist_btn.setObjectName("sidebarWideButton")
        add_to_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_to_playlist_btn.clicked.connect(self.add_current_song_to_playlist)

        remove_from_playlist_btn = QPushButton("移出当前歌单")
        remove_from_playlist_btn.setObjectName("sidebarWideButton")
        remove_from_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_from_playlist_btn.clicked.connect(self.remove_current_song_from_current_playlist)

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
        layout.addWidget(add_to_playlist_btn)
        layout.addWidget(remove_from_playlist_btn)
        layout.addLayout(edit_row)

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
        self.song_list.itemClicked.connect(self.select_song)
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)

        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addLayout(self.view_layout)
        layout.addWidget(self.song_list, 1)

        return panel
'''

    text = replace_method(text, "refresh_playlist_view_buttons", new_refresh_playlist_view_buttons)
    text = replace_method(text, "_create_sidebar", new_create_sidebar)
    text = replace_method(text, "_create_library_panel", new_create_library_panel)

    style_marker = '''        QPushButton#viewButton[active="true"] {
            background: #2f68d8;
            color: #ffffff;
            font-weight: 700;
        }
'''

    sidebar_styles = '''        QLabel#sidebarSectionTitle {
            color: #6f7786;
            font-size: 12px;
            font-weight: 700;
            padding: 8px 4px 2px 4px;
        }

        QFrame#sidebarPlaylistBox {
            background: transparent;
        }

        QPushButton#playlistSidebarButton {
            background: transparent;
            color: #a7acb8;
            text-align: left;
            border-radius: 10px;
            padding: 9px 12px;
            font-size: 13px;
        }

        QPushButton#playlistSidebarButton:hover {
            background: #20242d;
            color: #ffffff;
        }

        QPushButton#playlistSidebarButton[active="true"] {
            background: #2f68d8;
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton#sidebarWideButton {
            background: #1f232c;
            color: #cbd1dc;
            border-radius: 10px;
            padding: 9px 12px;
            font-size: 12px;
            text-align: left;
        }

        QPushButton#sidebarWideButton:hover {
            background: #2a303c;
            color: #ffffff;
        }

        QPushButton#sidebarMiniButton {
            background: #1f232c;
            color: #cbd1dc;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 12px;
        }

        QPushButton#sidebarMiniButton:hover {
            background: #2a303c;
            color: #ffffff;
        }
'''

    if "QPushButton#playlistSidebarButton" not in text:
        text = replace_once(
            text,
            style_marker,
            style_marker + "\n" + sidebar_styles,
            "添加侧边栏歌单样式",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.2.1 歌单已移动到左侧侧边栏。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()