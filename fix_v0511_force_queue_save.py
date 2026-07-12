import ast
import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v051_save_fix"


QUEUE_METHODS = r'''    def load_play_queue(self) -> list[str]:
        if not self.play_queue_file.exists():
            return []

        try:
            with self.play_queue_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            queue = []

            for song_path in data:
                normalized_path = self.normalize_song_path(str(song_path))

                if normalized_path and Path(normalized_path).exists():
                    queue.append(normalized_path)

            return queue

        except Exception as error:
            print("读取播放队列失败：", error)
            return []

    def save_play_queue(self) -> None:
        try:
            self.play_queue_file.parent.mkdir(parents=True, exist_ok=True)

            with self.play_queue_file.open("w", encoding="utf-8") as file:
                json.dump(self.play_queue, file, ensure_ascii=False, indent=2)

            print("播放队列已保存：", self.play_queue_file)

        except Exception as error:
            print("保存播放队列失败：", error)

    def get_song_title_for_queue(self, song_path: str) -> str:
        song_data = self.find_song_data_by_path(song_path) if hasattr(self, "find_song_data_by_path") else None

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            return f"{title} - {artist}"

        return Path(song_path).stem

    def queue_song_path(self, song_path: str | None, insert_next: bool = False) -> None:
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path:
            QMessageBox.information(self, "提示", "这首歌没有有效文件路径。")
            return

        if not Path(normalized_path).exists():
            QMessageBox.information(self, "提示", "这个音乐文件已经不存在。")
            return

        if not hasattr(self, "play_queue"):
            self.play_queue = []

        if insert_next:
            self.play_queue.insert(0, normalized_path)
            action_text = "已设为下一首播放"
        else:
            self.play_queue.append(normalized_path)
            action_text = "已加入播放队列"

        self.save_play_queue()

        song_text = self.get_song_title_for_queue(normalized_path)
        print(f"{action_text}：{song_text}")
        QMessageBox.information(self, "播放队列", f"{action_text}\\n\\n{song_text}")

    def queue_selected_song_next(self, selected_item=None) -> None:
        item = selected_item or self.song_list.currentItem()

        if not item:
            QMessageBox.information(self, "提示", "请先选择一首歌。")
            return

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "提示", "请选择一首真实歌曲。")
            return

        self.queue_song_path(song_data.get("path", ""), insert_next=True)

    def queue_selected_song_last(self, selected_item=None) -> None:
        item = selected_item or self.song_list.currentItem()

        if not item:
            QMessageBox.information(self, "提示", "请先选择一首歌。")
            return

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "提示", "请选择一首真实歌曲。")
            return

        self.queue_song_path(song_data.get("path", ""), insert_next=False)

    def show_play_queue(self) -> None:
        if not hasattr(self, "play_queue"):
            self.play_queue = []

        self.play_queue = [
            song_path
            for song_path in self.play_queue
            if song_path and Path(song_path).exists()
        ]
        self.save_play_queue()

        if not self.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列是空的。")
            return

        lines = []

        for index, song_path in enumerate(self.play_queue[:20], start=1):
            lines.append(f"{index}. {self.get_song_title_for_queue(song_path)}")

        if len(self.play_queue) > 20:
            lines.append(f"...还有 {len(self.play_queue) - 20} 首")

        QMessageBox.information(
            self,
            "播放队列",
            "\\n".join(lines),
        )

    def clear_play_queue(self) -> None:
        if not hasattr(self, "play_queue"):
            self.play_queue = []

        if not self.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列已经是空的。")
            self.save_play_queue()
            return

        self.play_queue.clear()
        self.save_play_queue()
        QMessageBox.information(self, "播放队列", "播放队列已清空。")
        print("播放队列已清空")

    def play_song_from_queue_path(self, song_path: str) -> bool:
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path or not Path(normalized_path).exists():
            return False

        item = self.find_song_item_by_path(normalized_path) if hasattr(self, "find_song_item_by_path") else None
        song_data = self.find_song_data_by_path(normalized_path) if hasattr(self, "find_song_data_by_path") else None

        if song_data is None and item is not None:
            item_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(item_data, dict):
                song_data = item_data

        if not song_data:
            return False

        if item is not None:
            self.song_list.setCurrentItem(item)

        self.browsing_song_path = normalized_path
        self.browsing_song_data = song_data

        self.load_song_for_playback(song_data)
        self.media_player.play()

        if hasattr(self, "play_button"):
            self.play_button.setText("暂停")

        try:
            self.save_play_queue()

            if hasattr(self, "save_playback_session"):
                self.save_playback_session()
        except Exception as error:
            print("播放队列歌曲后保存状态失败：", error)

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        print(f"正在播放队列歌曲：{title} - {artist}")

        return True

    def play_next_queued_song(self) -> bool:
        if not hasattr(self, "play_queue"):
            self.play_queue = []

        while self.play_queue:
            song_path = self.play_queue.pop(0)

            if self.play_song_from_queue_path(song_path):
                self.save_play_queue()
                return True

        self.save_play_queue()
        return False
'''


NEW_CONTEXT_MENU = r'''    def show_song_context_menu(self, position) -> None:
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

        next_queue_action = menu.addAction("下一首播放")
        next_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_next(selected_item))

        add_queue_action = menu.addAction("加入播放队列")
        add_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_last(selected_item))

        show_queue_action = menu.addAction("查看播放队列")
        show_queue_action.triggered.connect(self.show_play_queue)

        clear_queue_action = menu.addAction("清空播放队列")
        clear_queue_action.triggered.connect(self.clear_play_queue)

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


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def insert_before_method(text: str, marker_method_name: str, content: str) -> str:
    marker = f"\n    def {marker_method_name}("
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{marker_method_name}")

    return text.replace(marker, "\n" + content.rstrip() + "\n" + marker, 1)


def ensure_imports(text: str) -> str:
    if "import json" not in text:
        text = "import json\n" + text

    return text


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.1 (local music player prototype)",
        "HushPlayer/0.5.0 (local music player prototype)",
        "HushPlayer/0.4.9.1 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.1.1 (local music player prototype)")

    return text


def add_queue_file_path(text: str) -> str:
    if "self.play_queue_file" in text:
        return text

    for field in ("self.playback_session_file", "self.lyrics_bindings_file", "self.settings_file"):
        pattern = re.compile(rf"^([ \t]*){re.escape(field)} = .*$", flags=re.M)
        match = pattern.search(text)

        if match:
            indent = match.group(1)
            inserted = match.group(0) + f'\n{indent}self.play_queue_file = self.project_root / "data" / "play_queue.json"'
            return text[:match.start()] + inserted + text[match.end():]

    raise RuntimeError("没有找到添加 play_queue_file 的位置。")


def add_queue_init(text: str) -> str:
    if "self.play_queue = self.load_play_queue()" in text:
        return text

    for field in ("self.playback_session", "self.lyrics_bindings", "self.song_stats"):
        pattern = re.compile(rf"^([ \t]*){re.escape(field)} = .*$", flags=re.M)
        match = pattern.search(text)

        if match:
            indent = match.group(1)
            inserted = match.group(0) + f"\n{indent}self.play_queue = self.load_play_queue()"
            return text[:match.start()] + inserted + text[match.end():]

    raise RuntimeError("没有找到初始化 play_queue 的位置。")


def upsert_queue_methods(text: str) -> str:
    method_names = [
        "load_play_queue",
        "save_play_queue",
        "get_song_title_for_queue",
        "queue_song_path",
        "queue_selected_song_next",
        "queue_selected_song_last",
        "show_play_queue",
        "clear_play_queue",
        "play_song_from_queue_path",
        "play_next_queued_song",
    ]

    for method_name in method_names:
        if f"def {method_name}" in text:
            text = replace_method(text, method_name, "")

    if "def load_playback_session" in text:
        return insert_before_method(text, "load_playback_session", QUEUE_METHODS)

    if "def load_settings" in text:
        return insert_before_method(text, "load_settings", QUEUE_METHODS)

    raise RuntimeError("没有找到插入播放队列方法的位置。")


def guess_next_method_name(text: str) -> str:
    tree = ast.parse(text)
    method_names = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            method_names = [
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef)
            ]
            break

    for candidate in ("play_next_song", "next_song", "play_next", "next_track", "play_next_track"):
        if candidate in method_names:
            return candidate

    for pattern in (
        r"next_button\.clicked\.connect\(self\.(\w+)\)",
        r"next_btn\.clicked\.connect\(self\.(\w+)\)",
    ):
        match = re.search(pattern, text)

        if match and match.group(1) in method_names:
            return match.group(1)

    next_like_methods = [
        name
        for name in method_names
        if "next" in name.lower() and "queue" not in name.lower()
    ]

    if next_like_methods:
        next_like_methods.sort(key=lambda name: (0 if "song" in name.lower() else 1, len(name)))
        return next_like_methods[0]

    raise RuntimeError("没有找到下一首函数。")


def patch_next_method(text: str) -> str:
    if "if self.play_next_queued_song():\n            return" in text:
        return text

    method_name = guess_next_method_name(text)
    tree = ast.parse(text)

    target_function = None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    target_function = item
                    break

    if target_function is None or not target_function.body:
        raise RuntimeError(f"无法定位下一首函数：{method_name}")

    lines = text.splitlines()
    first_body_index = target_function.body[0].lineno - 1
    body_line = lines[first_body_index]
    indent = body_line[: len(body_line) - len(body_line.lstrip())]

    patch_lines = [
        f"{indent}if self.play_next_queued_song():",
        f"{indent}    return",
        "",
    ]

    lines[first_body_index:first_body_index] = patch_lines
    print(f"已把播放队列接入下一首函数：{method_name}")

    return "\n".join(lines) + "\n"


def patch_context_menu(text: str) -> str:
    return replace_method(text, "show_song_context_menu", NEW_CONTEXT_MENU)


def add_close_save(text: str) -> str:
    if "self.save_play_queue()" in text:
        return text

    if "self.save_playback_session()" in text:
        return text.replace(
            "        self.save_playback_session()\n",
            "        self.save_playback_session()\n        self.save_play_queue()\n",
            1,
        )

    if "self.save_song_stats()" in text:
        return text.replace(
            "        self.save_song_stats()\n",
            "        self.save_song_stats()\n        self.save_play_queue()\n",
            1,
        )

    return text


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = add_queue_file_path(text)
    text = add_queue_init(text)
    text = upsert_queue_methods(text)
    text = patch_next_method(text)
    text = patch_context_menu(text)
    text = add_close_save(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("修复完成：v0.5.1.1 已强制修复播放队列保存。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
