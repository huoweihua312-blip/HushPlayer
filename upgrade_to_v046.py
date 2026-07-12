import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0451"


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


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.6" in text:
        print("当前文件看起来已经升级到 v0.4.6 了，不需要重复升级。")
        return

    if "def start_lyrics_worker" not in text or "def show_song_context_menu" not in text:
        raise RuntimeError("没有找到 v0.4.5 之后的后台歌词/右键菜单代码。请先确认已经升级到 v0.4.5.1。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.5.1 (local music player prototype)",
        "HushPlayer/0.4.6 (local music player prototype)",
    )
    text = text.replace(
        "HushPlayer/0.4.5 (local music player prototype)",
        "HushPlayer/0.4.6 (local music player prototype)",
    )

    if "self.lyrics_bindings_file" not in text:
        text = replace_once(
            text,
            '''        self.lyrics_cache_dir = self.project_root / "cache" / "lyrics"
''',
            '''        self.lyrics_cache_dir = self.project_root / "cache" / "lyrics"
        self.lyrics_bindings_file = self.project_root / "data" / "lyrics_bindings.json"
''',
            "添加歌词绑定文件路径",
        )

    if "歌词绑定保存位置" not in text:
        text = replace_once(
            text,
            '''        print("歌词缓存位置：", self.lyrics_cache_dir)
''',
            '''        print("歌词缓存位置：", self.lyrics_cache_dir)
        print("歌词绑定保存位置：", self.lyrics_bindings_file)
''',
            "打印歌词绑定保存位置",
        )

    if "self.lyrics_bindings = self.load_lyrics_bindings()" not in text:
        text = replace_once(
            text,
            '''        self.song_stats = self.load_song_stats()
''',
            '''        self.song_stats = self.load_song_stats()
        self.lyrics_bindings = self.load_lyrics_bindings()
''',
            "初始化歌词绑定数据",
        )

    binding_methods = r'''    def load_lyrics_bindings(self) -> dict:
        if not self.lyrics_bindings_file.exists():
            return {}

        try:
            with self.lyrics_bindings_file.open("r", encoding="utf-8") as file:
                raw_bindings = json.load(file)

            if not isinstance(raw_bindings, dict):
                return {}

            bindings = {}

            for song_path, lyric_path in raw_bindings.items():
                normalized_song_path = self.normalize_song_path(str(song_path))
                normalized_lyric_path = self.normalize_song_path(str(lyric_path))

                if not normalized_song_path or not normalized_lyric_path:
                    continue

                if not Path(normalized_lyric_path).exists():
                    continue

                bindings[normalized_song_path] = normalized_lyric_path

            return bindings

        except Exception as error:
            print("读取歌词绑定失败：", error)
            return {}

    def save_lyrics_bindings(self) -> None:
        self.lyrics_bindings_file.parent.mkdir(parents=True, exist_ok=True)

        with self.lyrics_bindings_file.open("w", encoding="utf-8") as file:
            json.dump(self.lyrics_bindings, file, ensure_ascii=False, indent=2)

        print("歌词绑定已保存：", self.lyrics_bindings_file)

    def get_bound_lyrics_path(self, song_path: str | None) -> str:
        normalized_song_path = self.normalize_song_path(song_path)

        if not normalized_song_path:
            return ""

        lyric_path = self.lyrics_bindings.get(normalized_song_path, "")

        if not lyric_path:
            return ""

        normalized_lyric_path = self.normalize_song_path(lyric_path)

        if not Path(normalized_lyric_path).exists():
            self.lyrics_bindings.pop(normalized_song_path, None)
            self.save_lyrics_bindings()
            return ""

        return normalized_lyric_path

    def get_song_cache_path(self, song_path: str | None, cache_dir: Path, suffix: str) -> Path | None:
        normalized_song_path = self.normalize_song_path(song_path)

        if not normalized_song_path:
            return None

        digest = hashlib.sha1(normalized_song_path.lower().encode("utf-8")).hexdigest()
        return cache_dir / f"{digest}{suffix}"

    def clear_lyrics_cache_for_song(self, song_path: str | None) -> None:
        cache_path = self.get_song_cache_path(song_path, self.lyrics_cache_dir, ".lrc")

        if not cache_path:
            return

        missing_path = cache_path.with_suffix(".missing")

        for path in (cache_path, missing_path):
            try:
                if path.exists():
                    path.unlink()
                    print("已删除歌词缓存：", path)
            except Exception as error:
                print("删除歌词缓存失败：", error)

    def clear_cover_cache_for_song(self, song_path: str | None) -> None:
        cache_path = self.get_song_cache_path(song_path, self.cover_cache_dir, ".jpg")

        if not cache_path:
            return

        missing_path = cache_path.with_suffix(".missing")

        for path in (cache_path, missing_path):
            try:
                if path.exists():
                    path.unlink()
                    print("已删除封面缓存：", path)
            except Exception as error:
                print("删除封面缓存失败：", error)

    def get_selected_real_song_data(self) -> dict | None:
        item = self.song_list.currentItem()
        return self.get_song_data_from_item(item)

    def reload_selected_song_lyrics(self, ignore_binding: bool = False) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")

        self.load_lyrics_for_song(
            file_path=song_path,
            title=title,
            artist=artist,
            ignore_binding=ignore_binding,
        )

    def bind_selected_song_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            QMessageBox.information(self, "提示", "这首歌没有有效文件路径。")
            return

        lyric_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 LRC 歌词文件",
            str(Path(song_path).parent),
            "LRC Lyrics (*.lrc);;All Files (*)",
        )

        if not lyric_file:
            return

        lyric_path = self.normalize_song_path(lyric_file)
        lyrics = self.parse_lrc_file(Path(lyric_path))

        if not lyrics:
            QMessageBox.warning(
                self,
                "歌词不可用",
                "这个 .lrc 文件没有解析出有效时间轴，请换一个带时间轴的 LRC 文件。",
            )
            return

        self.lyrics_bindings[song_path] = lyric_path
        self.save_lyrics_bindings()
        self.clear_lyrics_cache_for_song(song_path)

        self.current_lyrics = lyrics
        self.displayed_lyrics_song_path = song_path
        self.lyrics_view.set_lyrics(self.current_lyrics)
        self.set_lyrics_status("已手动绑定歌词")

        QMessageBox.information(self, "绑定成功", "已为当前歌曲绑定这个 LRC 歌词文件。")
        print("已手动绑定歌词：", song_path, "->", lyric_path)

    def unbind_selected_song_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            return

        if song_path not in self.lyrics_bindings:
            QMessageBox.information(self, "提示", "这首歌当前没有手动绑定歌词。")
            return

        self.lyrics_bindings.pop(song_path, None)
        self.save_lyrics_bindings()

        self.set_lyrics_status("已取消手动歌词绑定")
        self.reload_selected_song_lyrics(ignore_binding=True)

        print("已取消歌词绑定：", song_path)

    def force_search_selected_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        self.clear_lyrics_cache_for_song(song_path)
        self.reload_selected_song_lyrics(ignore_binding=True)

        print("已清除歌词缓存并重新搜索：", song_path)

    def force_search_selected_cover(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")

        self.clear_cover_cache_for_song(song_path)

        self.update_cover(
            file_path=song_path,
            title=title,
            artist=artist,
            album=album,
        )

        print("已清除封面缓存并重新搜索：", song_path)
'''

    if "def bind_selected_song_lyrics" not in text:
        text = insert_before(
            text,
            '''    def save_settings(self) -> None:
''',
            binding_methods,
            "插入歌词绑定和重新搜索方法",
        )

    new_load_lyrics_for_song = r'''    def load_lyrics_for_song(
        self,
        file_path: str | None,
        title: str,
        artist: str,
        ignore_binding: bool = False,
    ) -> None:
        self.current_lyrics = []
        self.displayed_lyrics_song_path = self.normalize_song_path(file_path)
        self.lyrics_view.set_placeholder("正在查找歌词", "优先手动绑定，其次本地歌词，然后缓存和联网")
        self.set_lyrics_status("正在查找歌词")

        if not file_path:
            self.lyrics_view.set_placeholder("歌词功能还没有接入演示歌曲", "")
            self.set_lyrics_status("演示歌曲无歌词")
            return

        normalized_file_path = self.normalize_song_path(file_path)

        if not ignore_binding:
            bound_lyrics_path = self.get_bound_lyrics_path(normalized_file_path)

            if bound_lyrics_path:
                self.set_lyrics_status("正在读取手动绑定歌词")
                lyrics = self.parse_lrc_file(Path(bound_lyrics_path))

                if lyrics:
                    self.current_lyrics = lyrics
                    self.displayed_lyrics_song_path = normalized_file_path
                    self.lyrics_view.set_lyrics(self.current_lyrics)
                    self.set_lyrics_status("已加载手动绑定歌词")

                    print("已加载手动绑定歌词：", bound_lyrics_path)
                    print("歌词行数：", len(self.current_lyrics))
                    return

                self.set_lyrics_status("手动绑定歌词解析失败，继续自动查找")
                print("手动绑定歌词解析失败：", bound_lyrics_path)

        album = "未知专辑"
        current_item = self.song_list.currentItem()

        if current_item:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                album = song_data.get("album", "未知专辑")

        self.start_lyrics_worker(
            file_path=normalized_file_path,
            title=title,
            artist=artist,
            album=album,
        )
'''

    text = replace_method(text, "load_lyrics_for_song", new_load_lyrics_for_song)

    new_show_song_context_menu = r'''    def show_song_context_menu(self, position) -> None:
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

        bind_lyrics_action = menu.addAction("手动绑定歌词")
        bind_lyrics_action.triggered.connect(self.bind_selected_song_lyrics)

        if self.get_bound_lyrics_path(song_path):
            unbind_lyrics_action = menu.addAction("取消歌词绑定")
            unbind_lyrics_action.triggered.connect(self.unbind_selected_song_lyrics)

        retry_lyrics_action = menu.addAction("重新搜索歌词")
        retry_lyrics_action.triggered.connect(self.force_search_selected_lyrics)

        retry_cover_action = menu.addAction("重新搜索封面")
        retry_cover_action.triggered.connect(self.force_search_selected_cover)

        menu.addSeparator()

        open_folder_action = menu.addAction("打开文件夹")
        open_folder_action.triggered.connect(self.open_selected_song_folder)

        song_info_action = menu.addAction("查看歌曲信息")
        song_info_action.triggered.connect(self.show_selected_song_info)

        menu.addSeparator()

        remove_from_library_action = menu.addAction("从音乐库移除")
        remove_from_library_action.triggered.connect(self.remove_selected_song)

        menu.exec(self.song_list.mapToGlobal(position))
'''

    text = replace_method(text, "show_song_context_menu", new_show_song_context_menu)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.6 手动绑定歌词 + 重新搜索歌词/封面 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
