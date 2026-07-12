import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v050"


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
        self.play_queue_file.parent.mkdir(parents=True, exist_ok=True)

        with self.play_queue_file.open("w", encoding="utf-8") as file:
            json.dump(self.play_queue, file, ensure_ascii=False, indent=2)

    def get_song_title_for_queue(self, song_path: str) -> str:
        song_data = self.find_song_data_by_path(song_path)

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
        if not self.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列已经是空的。")
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
            self.save_playback_session()
        except Exception:
            pass

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        print(f"正在播放队列歌曲：{title} - {artist}")

        return True

    def play_next_queued_song(self) -> bool:
        while self.play_queue:
            song_path = self.play_queue.pop(0)

            if self.play_song_from_queue_path(song_path):
                self.save_play_queue()
                return True

        self.save_play_queue()
        return False
'''


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


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
    old_versions = (
        "HushPlayer/0.5.0 (local music player prototype)",
        "HushPlayer/0.4.9.1 (local music player prototype)",
        "HushPlayer/0.4.9 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.5.1 (local music player prototype)")

    return text


def add_queue_file_path(text: str) -> str:
    if "self.play_queue_file" in text:
        return text

    if "self.playback_session_file" in text:
        pattern = re.compile(r"^([ \t]*)self\.playback_session_file = .*$", flags=re.M)
        match = pattern.search(text)

        if match:
            indent = match.group(1)
            insert_text = match.group(0) + f"\n{indent}self.play_queue_file = self.project_root / \"data\" / \"play_queue.json\""
            return text[:match.start()] + insert_text + text[match.end():]

    if "self.lyrics_bindings_file" in text:
        return replace_once(
            text,
            '''        self.lyrics_bindings_file = self.project_root / "data" / "lyrics_bindings.json"
''',
            '''        self.lyrics_bindings_file = self.project_root / "data" / "lyrics_bindings.json"
        self.play_queue_file = self.project_root / "data" / "play_queue.json"
''',
            "添加播放队列文件路径",
        )

    raise RuntimeError("没有找到适合添加 play_queue_file 的位置。")


def add_queue_init(text: str) -> str:
    if "self.play_queue = self.load_play_queue()" in text:
        return text

    if "self.playback_session = self.load_playback_session()" in text:
        pattern = re.compile(r"^([ \t]*)self\.playback_session = self\.load_playback_session\(\).*$", flags=re.M)
        match = pattern.search(text)

        if match:
            indent = match.group(1)
            insert_text = match.group(0) + f"\n{indent}self.play_queue = self.load_play_queue()"
            return text[:match.start()] + insert_text + text[match.end():]

    if "self.lyrics_bindings = self.load_lyrics_bindings()" in text:
        return replace_once(
            text,
            '''        self.lyrics_bindings = self.load_lyrics_bindings()
''',
            '''        self.lyrics_bindings = self.load_lyrics_bindings()
        self.play_queue = self.load_play_queue()
''',
            "初始化播放队列",
        )

    raise RuntimeError("没有找到适合初始化 play_queue 的位置。")


def add_queue_methods(text: str) -> str:
    if "def load_play_queue" in text:
        return text

    if "def load_playback_session" in text:
        return insert_before_method(text, "load_playback_session", QUEUE_METHODS)

    if "def load_settings" in text:
        return insert_before_method(text, "load_settings", QUEUE_METHODS)

    raise RuntimeError("没有找到适合插入播放队列方法的位置。")


def patch_next_method(text: str) -> str:
    if "self.play_next_queued_song()" in text:
        return text

    candidates = [
        "play_next_song",
        "next_song",
        "play_next",
        "next_track",
    ]

    for method_name in candidates:
        pattern = re.compile(
            rf"(\n    def {method_name}\(.*?\):\n)([ \t]*)(.*?)(?=\n    def |\Z)",
            flags=re.S,
        )
        match = pattern.search(text)

        if not match:
            continue

        method_header = match.group(1)
        body_indent = match.group(2)

        if not body_indent:
            body_indent = "        "

        insert_code = (
            f"{method_header}"
            f"{body_indent}if self.play_next_queued_song():\n"
            f"{body_indent}    return\n\n"
        )

        new_method_text = insert_code + text[match.start(3):match.end(3)]
        return text[:match.start()] + new_method_text + text[match.end():]

    raise RuntimeError("没有找到下一首方法。请把 main_window.py 里“下一首”相关函数名发我，我再给你补丁。")


def patch_context_menu(text: str) -> str:
    if "queue_selected_song_next" in text and "queue_selected_song_last" in text and "show_play_queue" in text:
        return text

    marker = '''        play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))
'''

    if marker not in text:
        marker = '''        play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))
'''

    if marker not in text:
        raise RuntimeError("没有找到右键菜单里的播放 action。")

    queue_block = '''        next_queue_action = menu.addAction("下一首播放")
        next_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_next(selected_item))

        add_queue_action = menu.addAction("加入播放队列")
        add_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_last(selected_item))

        show_queue_action = menu.addAction("查看播放队列")
        show_queue_action.triggered.connect(self.show_play_queue)

        clear_queue_action = menu.addAction("清空播放队列")
        clear_queue_action.triggered.connect(self.clear_play_queue)

'''

    return text.replace(marker, marker + "\n" + queue_block, 1)


def add_close_save_queue(text: str) -> str:
    if "self.save_play_queue()" in text and "def closeEvent" in text:
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

    if "HushPlayer/0.5.1" in text:
        print("当前文件看起来已经升级到 v0.5.1 了，不需要重复升级。")
        return

    if "def show_song_context_menu" not in text:
        raise RuntimeError("没有找到右键菜单方法。请先确认已经升级到 v0.4.3 之后的版本。")

    if "def load_song_for_playback" not in text:
        raise RuntimeError("没有找到 load_song_for_playback，无法接入播放队列。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = add_queue_file_path(text)
    text = add_queue_init(text)
    text = add_queue_methods(text)
    text = patch_next_method(text)
    text = patch_context_menu(text)
    text = add_close_save_queue(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
    print("升级完成：v0.5.1 播放队列 / 下一首播放 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
