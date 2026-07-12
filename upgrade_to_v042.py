from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v041"


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

    if "HushPlayer/0.4.2" in text:
        print("当前文件看起来已经升级到 v0.4.2 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = replace_once(
        text,
        '''    QFileDialog,
    QFrame,
''',
        '''    QFileDialog,
    QFrame,
    QInputDialog,
    QMessageBox,
''',
        "添加 QInputDialog / QMessageBox 导入",
    )

    text = replace_once(
        text,
        '''        self.current_library_view = "all"
        self.view_buttons = {}

        self.http_headers = {
            "User-Agent": "HushPlayer/0.4.1 (local music player prototype)",
''',
        '''        self.current_library_view = "all"
        self.view_buttons = {}
        self.custom_view_buttons = []

        self.http_headers = {
            "User-Agent": "HushPlayer/0.4.2 (local music player prototype)",
''',
        "初始化自定义歌单按钮",
    )

    playlist_override_methods = r'''    def _create_view_button(self, text: str, view_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("viewButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("active", view_name == self.current_library_view)
        button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))

        self.view_buttons[view_name] = button
        return button

    def get_playlist_name(self, playlist_id: str) -> str:
        playlist = self.playlists.get(playlist_id, {})

        if not isinstance(playlist, dict):
            return "未命名歌单"

        name = str(playlist.get("name", "")).strip()
        return name or "未命名歌单"

    def get_playlist_song_paths(self, playlist_id: str) -> list[str]:
        if playlist_id not in self.playlists or not isinstance(self.playlists.get(playlist_id), dict):
            self.playlists[playlist_id] = {
                "name": "未命名歌单",
                "songs": [],
                "fixed": False,
            }

        playlist = self.playlists[playlist_id]
        songs = playlist.setdefault("songs", [])

        if not isinstance(songs, list):
            playlist["songs"] = []
            songs = playlist["songs"]

        normalized_songs = []

        for path in songs:
            normalized_path = self.normalize_song_path(str(path))

            if normalized_path and normalized_path not in normalized_songs:
                normalized_songs.append(normalized_path)

        playlist["songs"] = normalized_songs
        return playlist["songs"]

    def get_custom_playlist_ids(self) -> list[str]:
        playlist_ids = []

        for playlist_id, playlist in self.playlists.items():
            if playlist_id == "liked":
                continue

            if not isinstance(playlist, dict):
                continue

            playlist_ids.append(playlist_id)

        playlist_ids.sort(
            key=lambda playlist_id: int(
                self.playlists.get(playlist_id, {}).get("created_at", 0) or 0
            )
        )

        return playlist_ids

    def create_playlist_id(self) -> str:
        base_id = f"playlist_{int(time.time() * 1000)}"
        playlist_id = base_id
        index = 1

        while playlist_id in self.playlists:
            playlist_id = f"{base_id}_{index}"
            index += 1

        return playlist_id

    def refresh_playlist_view_buttons(self) -> None:
        if not hasattr(self, "view_layout"):
            return

        for button in getattr(self, "custom_view_buttons", []):
            self.view_layout.removeWidget(button)
            button.deleteLater()

        self.custom_view_buttons = []

        for view_name in list(self.view_buttons.keys()):
            if view_name.startswith("playlist:"):
                self.view_buttons.pop(view_name, None)

        insert_index = max(0, self.view_layout.count() - 1)

        for playlist_id in self.get_custom_playlist_ids():
            playlist_name = self.get_playlist_name(playlist_id)
            view_name = f"playlist:{playlist_id}"

            button = self._create_view_button(playlist_name, view_name)
            button.setProperty("customPlaylistButton", True)

            self.view_layout.insertWidget(insert_index, button)
            self.custom_view_buttons.append(button)
            insert_index += 1

        self.update_view_buttons()

    def set_library_view(self, view_name: str) -> None:
        fixed_views = {"all", "liked", "recent_played", "frequent", "recent_added"}

        if view_name in fixed_views:
            self.current_library_view = view_name
        elif view_name.startswith("playlist:"):
            playlist_id = view_name.split("playlist:", 1)[1]

            if playlist_id in self.playlists:
                self.current_library_view = view_name
            else:
                self.current_library_view = "all"
        else:
            self.current_library_view = "all"

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

        if self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            view_title = self.get_playlist_name(playlist_id)
        else:
            view_title = view_titles.get(self.current_library_view, "全部歌曲")

        print("当前音乐库视图：", view_title)

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

        if self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            playlist_songs = self.get_playlist_song_paths(playlist_id)
            return normalized_path in playlist_songs

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

        elif self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            playlist_songs = self.get_playlist_song_paths(playlist_id)
            playlist_order = {
                path: index
                for index, path in enumerate(playlist_songs)
            }

            songs.sort(
                key=lambda song: playlist_order.get(normalized_path(song), 999999),
            )

        else:
            songs.sort(
                key=lambda song: int(song.get("added_at", 0) or 0),
            )

        self.rebuild_song_list_from_data(songs)

    def create_new_playlist(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "新建歌单",
            "输入歌单名称：",
        )

        if not ok:
            return

        name = name.strip()

        if not name:
            return

        playlist_id = self.create_playlist_id()

        self.playlists[playlist_id] = {
            "name": name,
            "songs": [],
            "fixed": False,
            "created_at": int(time.time()),
        }

        self.save_playlists()
        self.refresh_playlist_view_buttons()
        self.set_library_view(f"playlist:{playlist_id}")

        print("已新建歌单：", name)

    def rename_current_playlist(self) -> None:
        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到一个自定义歌单。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]

        if playlist_id not in self.playlists:
            return

        old_name = self.get_playlist_name(playlist_id)

        new_name, ok = QInputDialog.getText(
            self,
            "重命名歌单",
            "输入新的歌单名称：",
            text=old_name,
        )

        if not ok:
            return

        new_name = new_name.strip()

        if not new_name:
            return

        self.playlists[playlist_id]["name"] = new_name
        self.save_playlists()
        self.refresh_playlist_view_buttons()
        self.update_view_buttons()

        print(f"歌单已重命名：{old_name} -> {new_name}")

    def delete_current_playlist(self) -> None:
        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到一个自定义歌单。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]

        if playlist_id not in self.playlists:
            return

        playlist_name = self.get_playlist_name(playlist_id)

        result = QMessageBox.question(
            self,
            "删除歌单",
            f"确定删除歌单「{playlist_name}」吗？\\n这不会删除真实音乐文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self.playlists.pop(playlist_id, None)
        self.current_library_view = "all"

        self.save_playlists()
        self.refresh_playlist_view_buttons()
        self.set_library_view("all")

        print("已删除歌单：", playlist_name)

    def get_current_selected_song_path(self) -> str:
        item = self.song_list.currentItem()

        if not item:
            return self.normalize_song_path(self.current_song_path)

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return self.normalize_song_path(self.current_song_path)

        return self.normalize_song_path(song_data.get("path", ""))

    def add_current_song_to_playlist(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        custom_playlist_ids = self.get_custom_playlist_ids()

        if not custom_playlist_ids:
            result = QMessageBox.question(
                self,
                "还没有歌单",
                "你还没有自定义歌单，要现在新建一个吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if result == QMessageBox.StandardButton.Yes:
                self.create_new_playlist()

            return

        choices = []
        choice_to_id = {}

        for playlist_id in custom_playlist_ids:
            name = self.get_playlist_name(playlist_id)
            choices.append(name)
            choice_to_id[name] = playlist_id

        selected_name, ok = QInputDialog.getItem(
            self,
            "添加到歌单",
            "选择要加入的歌单：",
            choices,
            0,
            False,
        )

        if not ok:
            return

        playlist_id = choice_to_id.get(selected_name)

        if not playlist_id:
            return

        playlist_songs = self.get_playlist_song_paths(playlist_id)

        if song_path not in playlist_songs:
            playlist_songs.append(song_path)

        self.save_playlists()

        if self.current_library_view == f"playlist:{playlist_id}":
            self.filter_song_list(self.search_input.text())

        print(f"已添加到歌单「{selected_name}」：", song_path)

    def remove_current_song_from_current_playlist(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        if self.current_library_view == "liked":
            liked_songs = self.get_liked_song_paths()

            if song_path in liked_songs:
                liked_songs.remove(song_path)
                self.save_playlists()
                self.update_like_button()
                self.filter_song_list(self.search_input.text())

            return

        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到某个歌单视图。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]
        playlist_songs = self.get_playlist_song_paths(playlist_id)

        if song_path in playlist_songs:
            playlist_songs.remove(song_path)
            self.save_playlists()
            self.filter_song_list(self.search_input.text())

            print("已从当前歌单移除：", song_path)

'''

    text = insert_before(
        text,
        '''    def _create_sidebar(self) -> QFrame:
''',
        playlist_override_methods,
        "插入自定义歌单方法",
    )

    text = replace_once(
        text,
        '''        view_layout = QHBoxLayout()
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
        '''        self.view_layout = QHBoxLayout()
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_layout.setSpacing(8)

        self.view_layout.addWidget(self._create_view_button("全部歌曲", "all"))
        self.view_layout.addWidget(self._create_view_button("我喜欢", "liked"))
        self.view_layout.addWidget(self._create_view_button("最近播放", "recent_played"))
        self.view_layout.addWidget(self._create_view_button("常听歌曲", "frequent"))
        self.view_layout.addWidget(self._create_view_button("最近添加", "recent_added"))
        self.view_layout.addStretch()
        self.refresh_playlist_view_buttons()

        playlist_action_layout = QHBoxLayout()
        playlist_action_layout.setContentsMargins(0, 0, 0, 0)
        playlist_action_layout.setSpacing(8)

        new_playlist_btn = QPushButton("新建歌单")
        rename_playlist_btn = QPushButton("重命名歌单")
        delete_playlist_btn = QPushButton("删除歌单")
        add_to_playlist_btn = QPushButton("添加到歌单")
        remove_from_playlist_btn = QPushButton("移出当前歌单")

        new_playlist_btn.clicked.connect(self.create_new_playlist)
        rename_playlist_btn.clicked.connect(self.rename_current_playlist)
        delete_playlist_btn.clicked.connect(self.delete_current_playlist)
        add_to_playlist_btn.clicked.connect(self.add_current_song_to_playlist)
        remove_from_playlist_btn.clicked.connect(self.remove_current_song_from_current_playlist)

        for button in (
            new_playlist_btn,
            rename_playlist_btn,
            delete_playlist_btn,
            add_to_playlist_btn,
            remove_from_playlist_btn,
        ):
            button.setObjectName("playlistActionButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            playlist_action_layout.addWidget(button)

        playlist_action_layout.addStretch()

        self.song_list = QListWidget()
''',
        "替换视图布局并添加歌单操作按钮",
    )

    text = replace_once(
        text,
        '''        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addLayout(view_layout)
        layout.addWidget(self.song_list, 1)
''',
        '''        layout.addLayout(header_layout)
        layout.addLayout(search_layout)
        layout.addLayout(self.view_layout)
        layout.addLayout(playlist_action_layout)
        layout.addWidget(self.song_list, 1)
''',
        "加入歌单操作按钮布局",
    )

    text = replace_once(
        text,
        '''        if self.current_library_view == "liked":
            self.filter_song_list(self.search_input.text())
''',
        '''        if self.current_library_view == "liked":
            self.filter_song_list(self.search_input.text())
''',
        "保留收藏刷新逻辑",
    )

    text = replace_once(
        text,
        '''        QPushButton#viewButton[active="true"] {
            background: #2f68d8;
            color: #ffffff;
            font-weight: 700;
        }
''',
        '''        QPushButton#viewButton[active="true"] {
            background: #2f68d8;
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton#playlistActionButton {
            background: #1f232c;
            color: #cbd1dc;
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 12px;
        }

        QPushButton#playlistActionButton:hover {
            background: #2a303c;
            color: #ffffff;
        }
''',
        "添加歌单操作按钮样式",
    )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.2 自定义歌单系统已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()