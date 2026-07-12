from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v040"


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

    if "HushPlayer/0.4.1" in text:
        print("当前文件看起来已经升级到 v0.4.1 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = replace_once(
        text,
        '''        self.current_session_listen_ms = 0
        self.play_count_marked = False

        self.http_headers = {
            "User-Agent": "HushPlayer/0.4.0 (local music player prototype)",
''',
        '''        self.current_session_listen_ms = 0
        self.play_count_marked = False

        self.current_library_view = "all"
        self.view_buttons = {}

        self.http_headers = {
            "User-Agent": "HushPlayer/0.4.1 (local music player prototype)",
''',
        "初始化音乐库视图",
    )

    text = replace_once(
        text,
        '''        self.update_play_mode_button()
        self.update_like_button()
''',
        '''        self.update_play_mode_button()
        self.update_like_button()
        self.update_view_buttons()
''',
        "初始化视图按钮状态",
    )

    view_methods = r'''    def _create_view_button(self, text: str, view_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("viewButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("active", view_name == self.current_library_view)
        button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))

        self.view_buttons[view_name] = button
        return button

    def set_library_view(self, view_name: str) -> None:
        if view_name not in {"all", "liked", "recent_played", "frequent", "recent_added"}:
            view_name = "all"

        self.current_library_view = view_name
        self.sort_song_list_for_current_view()
        self.filter_song_list(self.search_input.text())
        self.update_view_buttons()

        view_titles = {
            "all": "全部歌曲",
            "liked": "我喜欢",
            "recent_played": "最近播放",
            "frequent": "常听歌曲",
            "recent_added": "最近添加",
        }

        print("当前音乐库视图：", view_titles.get(view_name, "全部歌曲"))

    def update_view_buttons(self) -> None:
        if not hasattr(self, "view_buttons"):
            return

        for view_name, button in self.view_buttons.items():
            button.setProperty("active", view_name == self.current_library_view)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def song_matches_current_view(self, song_data: dict) -> bool:
        if not isinstance(song_data, dict):
            return True

        if song_data.get("demo"):
            return self.current_library_view == "all"

        path = song_data.get("path", "")
        normalized_path = self.normalize_song_path(path)

        if self.current_library_view == "all":
            return True

        if self.current_library_view == "liked":
            return self.is_song_liked(normalized_path)

        if self.current_library_view == "recent_played":
            stats = self.song_stats.get(normalized_path, {})
            return int(stats.get("last_played", 0)) > 0

        if self.current_library_view == "frequent":
            stats = self.song_stats.get(normalized_path, {})
            play_count = int(stats.get("play_count", 0))
            total_listen_time = int(stats.get("total_listen_time", 0))
            return play_count > 0 or total_listen_time > 0

        if self.current_library_view == "recent_added":
            return bool(normalized_path)

        return True

    def collect_song_data_from_list(self) -> list[dict]:
        songs = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                songs.append(dict(song_data))

        return songs

    def create_song_list_item(self, song_data: dict) -> QListWidgetItem:
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")

        item = QListWidgetItem(f"{title}    ·    {artist}    ·    {album}")
        item.setData(Qt.ItemDataRole.UserRole, song_data)
        return item

    def rebuild_song_list_from_data(self, songs: list[dict]) -> None:
        current_path = self.normalize_song_path(self.current_song_path)
        selected_row = -1

        self.song_list.clear()

        for row, song_data in enumerate(songs):
            item = self.create_song_list_item(song_data)
            self.song_list.addItem(item)

            song_path = self.normalize_song_path(song_data.get("path", ""))

            if current_path and song_path == current_path:
                selected_row = row

        self.filter_song_list(self.search_input.text())

        if selected_row >= 0:
            self.song_list.setCurrentRow(selected_row)

    def sort_song_list_for_current_view(self) -> None:
        songs = self.collect_song_data_from_list()

        if not songs:
            return

        def normalized_path(song_data: dict) -> str:
            return self.normalize_song_path(song_data.get("path", ""))

        def stats_for(song_data: dict) -> dict:
            return self.song_stats.get(
                normalized_path(song_data),
                {
                    "play_count": 0,
                    "total_listen_time": 0,
                    "last_played": 0,
                },
            )

        if self.current_library_view == "recent_played":
            songs.sort(
                key=lambda song: int(stats_for(song).get("last_played", 0)),
                reverse=True,
            )

        elif self.current_library_view == "frequent":
            songs.sort(
                key=lambda song: (
                    int(stats_for(song).get("play_count", 0)),
                    int(stats_for(song).get("total_listen_time", 0)),
                    int(stats_for(song).get("last_played", 0)),
                ),
                reverse=True,
            )

        elif self.current_library_view == "recent_added":
            songs.sort(
                key=lambda song: int(song.get("added_at", 0) or 0),
                reverse=True,
            )

        else:
            songs.sort(
                key=lambda song: int(song.get("added_at", 0) or 0),
            )

        self.rebuild_song_list_from_data(songs)

'''

    text = insert_before(
        text,
        '''    def _create_sidebar(self) -> QFrame:
''',
        view_methods,
        "插入音乐库视图方法",
    )

    text = replace_once(
        text,
        '''        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(clear_search_btn)

        self.song_list = QListWidget()
''',
        '''        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(clear_search_btn)

        view_layout = QHBoxLayout()
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(8)

        view_layout.addWidget(self._create_view_button("全部歌曲", "all"))
        view_layout.addWidget(self._create_view_button("我喜欢", "liked"))
        view_layout.addWidget(self._create_view_button("最近播放", "recent_played"))
        view_layout.addWidget(self._create_view_button("常听歌曲", "frequent"))
        view_layout.addWidget(self._create_view_button("最近添加", "recent_added"))
        view_layout.addStretch()

        self.song_list = QListWidget()
''',
        "添加视图切换按钮",
    )

    text = replace_once(
        text,
        '''        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addWidget(self.song_list, 1)
''',
        '''        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addLayout(view_layout)
        layout.addWidget(self.song_list, 1)
''',
        "把视图按钮加入布局",
    )

    text = replace_once(
        text,
        '''            should_show = not keyword or keyword in search_text

            item.setHidden(not should_show)
''',
        '''            matches_keyword = not keyword or keyword in search_text
            matches_view = self.song_matches_current_view(song_data)
            should_show = matches_keyword and matches_view

            item.setHidden(not should_show)
''',
        "搜索逻辑加入视图过滤",
    )

    text = replace_once(
        text,
        '''        if visible_rows:
            return visible_rows

        return list(range(self.song_list.count()))
''',
        '''        return visible_rows
''',
        "get_visible_rows 不再返回隐藏歌曲",
    )

    text = replace_once(
        text,
        '''                    "album": song_data.get("album", "未知专辑"),
                    "path": str(Path(path).resolve()),
                }
''',
        '''                    "album": song_data.get("album", "未知专辑"),
                    "path": str(Path(path).resolve()),
                    "added_at": int(song_data.get("added_at", 0) or 0),
                }
''',
        "保存 added_at",
    )

    text = replace_once(
        text,
        '''            title = song.get("title", "未知歌曲")
            artist = song.get("artist", "未知艺术家")
            album = song.get("album", "未知专辑")
''',
        '''            title = song.get("title", "未知歌曲")
            artist = song.get("artist", "未知艺术家")
            album = song.get("album", "未知专辑")
            added_at = int(song.get("added_at", 0) or 0)
''',
        "读取 added_at",
    )

    text = replace_once(
        text,
        '''                    "album": album,
                    "path": str(Path(path).resolve()),
                    "demo": False,
''',
        '''                    "album": album,
                    "path": str(Path(path).resolve()),
                    "added_at": added_at,
                    "demo": False,
''',
        "加载歌曲时写入 added_at",
    )

    text = replace_once(
        text,
        '''            title, artist, album = self._read_audio_metadata(path)

            item = QListWidgetItem(f"{title}    ·    {artist}    ·    {album}")
''',
        '''            title, artist, album = self._read_audio_metadata(path)
            added_at = int(time.time()) + len(added_items)

            item = QListWidgetItem(f"{title}    ·    {artist}    ·    {album}")
''',
        "导入时生成 added_at",
    )

    text = replace_once(
        text,
        '''                    "album": album,
                    "path": normalized_path,
                    "demo": False,
''',
        '''                    "album": album,
                    "path": normalized_path,
                    "added_at": added_at,
                    "demo": False,
''',
        "导入歌曲时保存 added_at",
    )

    text = replace_once(
        text,
        '''        self.save_playlists()
        self.update_like_button()
''',
        '''        self.save_playlists()
        self.update_like_button()

        if self.current_library_view == "liked":
            self.filter_song_list(self.search_input.text())
''',
        "收藏变化时刷新我喜欢视图",
    )

    text = replace_once(
        text,
        '''        QPushButton#secondaryButton:hover {
            background: #303746;
        }
''',
        '''        QPushButton#secondaryButton:hover {
            background: #303746;
        }

        QPushButton#viewButton {
            background: #20242d;
            color: #a7acb8;
            border-radius: 12px;
            padding: 8px 13px;
            font-size: 13px;
        }

        QPushButton#viewButton:hover {
            background: #2a303c;
            color: #ffffff;
        }

        QPushButton#viewButton[active="true"] {
            background: #2f68d8;
            color: #ffffff;
            font-weight: 700;
        }
''',
        "添加视图按钮样式",
    )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.1 音乐库视图已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()