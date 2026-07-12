import ast
import json
import re
import shutil
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
V050_BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v050"
BROKEN_BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_broken_v051"


QUEUE_METHODS = r"""
    def load_play_queue(self) -> list[str]:
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

            if hasattr(self, "save_playback_session"):
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
"""


def restore_from_v050_backup() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    if not V050_BACKUP_FILE.exists():
        raise FileNotFoundError(
            "找不到 v0.5.0 备份文件：app/ui/main_window.py.bak_v050\n"
            "请把这个报错发给我，我会按你当前文件继续修。"
        )

    shutil.copy2(MAIN_WINDOW_FILE, BROKEN_BACKUP_FILE)
    shutil.copy2(V050_BACKUP_FILE, MAIN_WINDOW_FILE)

    print(f"已备份出错文件：{BROKEN_BACKUP_FILE}")
    print(f"已从备份恢复：{V050_BACKUP_FILE}")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.0 (local music player prototype)",
        "HushPlayer/0.4.9.1 (local music player prototype)",
        "HushPlayer/0.4.9 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.1 (local music player prototype)")

    return text


def add_queue_file_path(text: str) -> str:
    if "self.play_queue_file" in text:
        return text

    pattern = re.compile(r"^([ \t]*)self\.playback_session_file = .*$", flags=re.M)
    match = pattern.search(text)

    if match:
        indent = match.group(1)
        inserted = match.group(0) + f'\n{indent}self.play_queue_file = self.project_root / "data" / "play_queue.json"'
        return text[:match.start()] + inserted + text[match.end():]

    pattern = re.compile(r"^([ \t]*)self\.lyrics_bindings_file = .*$", flags=re.M)
    match = pattern.search(text)

    if match:
        indent = match.group(1)
        inserted = match.group(0) + f'\n{indent}self.play_queue_file = self.project_root / "data" / "play_queue.json"'
        return text[:match.start()] + inserted + text[match.end():]

    raise RuntimeError("没有找到添加 play_queue_file 的位置。")


def add_queue_init(text: str) -> str:
    if "self.play_queue = self.load_play_queue()" in text:
        return text

    pattern = re.compile(r"^([ \t]*)self\.playback_session = self\.load_playback_session\(\).*$", flags=re.M)
    match = pattern.search(text)

    if match:
        indent = match.group(1)
        inserted = match.group(0) + f"\n{indent}self.play_queue = self.load_play_queue()"
        return text[:match.start()] + inserted + text[match.end():]

    pattern = re.compile(r"^([ \t]*)self\.lyrics_bindings = self\.load_lyrics_bindings\(\).*$", flags=re.M)
    match = pattern.search(text)

    if match:
        indent = match.group(1)
        inserted = match.group(0) + f"\n{indent}self.play_queue = self.load_play_queue()"
        return text[:match.start()] + inserted + text[match.end():]

    raise RuntimeError("没有找到初始化 play_queue 的位置。")


def insert_queue_methods(text: str) -> str:
    if "def load_play_queue" in text:
        return text

    marker = "\n    def load_playback_session("

    if marker in text:
        return text.replace(marker, "\n" + QUEUE_METHODS.rstrip() + "\n" + marker, 1)

    marker = "\n    def load_settings("

    if marker in text:
        return text.replace(marker, "\n" + QUEUE_METHODS.rstrip() + "\n" + marker, 1)

    raise RuntimeError("没有找到插入播放队列方法的位置。")


def find_main_window_method_line(text: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(text)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        if node.name != "MainWindow":
            continue

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                if not item.body:
                    return None

                return item.lineno, item.body[0].lineno

    return None


def guess_next_method_name(text: str) -> str:
    exact_candidates = [
        "play_next_song",
        "next_song",
        "play_next",
        "next_track",
        "play_next_track",
    ]

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

    for candidate in exact_candidates:
        if candidate in method_names:
            return candidate

    # 从按钮连接里猜
    for pattern in (
        r"next_button\.clicked\.connect\(self\.(\w+)\)",
        r"next_btn\.clicked\.connect\(self\.(\w+)\)",
        r"下一首.*?clicked\.connect\(self\.(\w+)\)",
    ):
        match = re.search(pattern, text, flags=re.S)

        if match:
            name = match.group(1)

            if name in method_names:
                return name

    next_like_methods = [
        name
        for name in method_names
        if "next" in name.lower() and "queue" not in name.lower()
    ]

    if next_like_methods:
        next_like_methods.sort(key=lambda name: (0 if "song" in name.lower() else 1, len(name)))
        return next_like_methods[0]

    raise RuntimeError("没有找到下一首函数。请把 main_window.py 里下一首按钮连接那几行发我。")


def patch_next_method(text: str) -> str:
    if "if self.play_next_queued_song():\n            return" in text:
        return text

    method_name = guess_next_method_name(text)
    line_info = find_main_window_method_line(text, method_name)

    if line_info is None:
        raise RuntimeError(f"找到下一首函数 {method_name}，但无法定位函数体。")

    _, first_body_line = line_info
    lines = text.splitlines()

    insert_index = first_body_line - 1
    body_line = lines[insert_index]
    indent = body_line[: len(body_line) - len(body_line.lstrip())]

    patch_lines = [
        f"{indent}if self.play_next_queued_song():",
        f"{indent}    return",
        "",
    ]

    lines[insert_index:insert_index] = patch_lines

    print(f"已接入播放队列到下一首函数：{method_name}")
    return "\n".join(lines) + "\n"


def patch_context_menu(text: str) -> str:
    if 'menu.addAction("下一首播放")' in text:
        return text

    marker = "play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))"

    if marker not in text:
        raise RuntimeError("没有找到右键菜单里的播放 action。")

    lines = text.splitlines()
    result = []
    inserted = False

    for line in lines:
        result.append(line)

        if marker not in line or inserted:
            continue

        indent = line[: len(line) - len(line.lstrip())]
        result.extend([
            "",
            f'{indent}next_queue_action = menu.addAction("下一首播放")',
            f"{indent}next_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_next(selected_item))",
            "",
            f'{indent}add_queue_action = menu.addAction("加入播放队列")',
            f"{indent}add_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_last(selected_item))",
            "",
            f'{indent}show_queue_action = menu.addAction("查看播放队列")',
            f"{indent}show_queue_action.triggered.connect(self.show_play_queue)",
            "",
            f'{indent}clear_queue_action = menu.addAction("清空播放队列")',
            f"{indent}clear_queue_action.triggered.connect(self.clear_play_queue)",
        ])
        inserted = True

    if not inserted:
        raise RuntimeError("右键菜单插入失败。")

    return "\n".join(result) + "\n"


def main() -> None:
    restore_from_v050_backup()

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.5.1" in text:
        print("恢复后的文件已经是 v0.5.1，不重复处理。")
        return

    text = ensure_version(text)
    text = add_queue_file_path(text)
    text = add_queue_init(text)
    text = insert_queue_methods(text)
    text = patch_next_method(text)
    text = patch_context_menu(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("修复完成：已恢复到 v0.5.0 备份，并重新安全加入 v0.5.1 播放队列。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
