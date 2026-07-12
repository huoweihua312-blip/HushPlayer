import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0491"


SESSION_METHODS = r'''    def load_playback_session(self) -> dict:
        if not self.playback_session_file.exists():
            return {}

        try:
            with self.playback_session_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                return data

            return {}

        except Exception as error:
            print("读取上次播放状态失败：", error)
            return {}

    def save_playback_session(self) -> None:
        if not hasattr(self, "media_player"):
            return

        current_path = self.normalize_song_path(getattr(self, "current_song_path", ""))

        if not current_path:
            return

        try:
            position = int(self.media_player.position())
        except Exception:
            position = 0

        session = {
            "path": current_path,
            "position": position,
            "saved_at": int(time.time()),
            "library_view": getattr(self, "current_library_view", "all"),
        }

        self.playback_session_file.parent.mkdir(parents=True, exist_ok=True)

        with self.playback_session_file.open("w", encoding="utf-8") as file:
            json.dump(session, file, ensure_ascii=False, indent=2)

    def find_song_item_by_path(self, song_path: str | None):
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
                return item

        return None

    def restore_playback_session(self) -> None:
        if getattr(self, "restored_playback_session", False):
            return

        self.restored_playback_session = True

        session = getattr(self, "playback_session", {})

        if not isinstance(session, dict):
            return

        song_path = self.normalize_song_path(session.get("path", ""))
        position = int(session.get("position", 0) or 0)

        if not song_path:
            return

        if not Path(song_path).exists():
            print("上次播放的文件已经不存在：", song_path)
            return

        try:
            if hasattr(self, "set_library_view"):
                self.set_library_view("all")
        except Exception as error:
            print("切换到全部歌曲视图失败：", error)

        item = self.find_song_item_by_path(song_path)

        if item is None:
            print("音乐库里没有找到上次播放歌曲：", song_path)
            return

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return

        self.song_list.setCurrentItem(item)
        self.browsing_song_path = song_path
        self.browsing_song_data = song_data

        try:
            self.load_song_for_playback(song_data)
        except Exception as error:
            print("恢复上次播放歌曲失败：", error)
            return

        if position > 0:
            QTimer.singleShot(650, lambda position=position: self.media_player.setPosition(position))

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")

        print(f"已恢复上次播放：{title} - {artist} @ {position // 1000}s")
'''


SHOW_EVENT_METHOD = r'''    def showEvent(self, event) -> None:
        super().showEvent(event)

        if getattr(self, "restored_playback_session", False):
            return

        QTimer.singleShot(500, self.restore_playback_session)
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


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def ensure_imports(text: str) -> str:
    if "import time" not in text:
        text = "import time\n" + text

    if "import json" not in text:
        text = "import json\n" + text

    if "QTimer" not in text:
        match = re.search(r"from PySide6\.QtCore import \((.*?)\)", text, flags=re.S)

        if match:
            imports_block = match.group(1)
            names = [name.strip().rstrip(",") for name in imports_block.splitlines() if name.strip()]
            names.append("QTimer")
            names = sorted(set(names), key=lambda x: x.lower())
            new_block = "from PySide6.QtCore import (\n" + "".join(f"    {name},\n" for name in names) + ")"
            return text[:match.start()] + new_block + text[match.end():]

        line_match = re.search(r"from PySide6\.QtCore import ([^\n]+)", text)

        if line_match:
            names = [name.strip() for name in line_match.group(1).split(",")]
            names.append("QTimer")
            names = sorted(set(names), key=lambda x: x.lower())
            new_line = "from PySide6.QtCore import " + ", ".join(names)
            return text[:line_match.start()] + new_line + text[line_match.end():]

    return text


def ensure_version(text: str) -> str:
    old_versions = (
        "HushPlayer/0.4.9.1 (local music player prototype)",
        "HushPlayer/0.4.9 (local music player prototype)",
        "HushPlayer/0.4.8.4 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.5.0 (local music player prototype)")

    return text


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.5.0" in text:
        print("当前文件看起来已经升级到 v0.5.0 了，不需要重复升级。")
        return

    if "class MainWindow(QMainWindow):" not in text:
        raise RuntimeError("没有找到 MainWindow。")

    if "def load_song_for_playback" not in text:
        raise RuntimeError("没有找到 load_song_for_playback。请先确认已经升级到 v0.4.4.1 之后的版本。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)

    if "self.playback_session_file" not in text:
        if "self.lyrics_bindings_file" in text:
            text = replace_once(
                text,
                '''        self.lyrics_bindings_file = self.project_root / "data" / "lyrics_bindings.json"
''',
                '''        self.lyrics_bindings_file = self.project_root / "data" / "lyrics_bindings.json"
        self.playback_session_file = self.project_root / "data" / "playback_session.json"
''',
                "添加播放状态文件路径",
            )
        elif "self.settings_file" in text:
            text = replace_once(
                text,
                '''        self.settings_file = self.project_root / "data" / "settings.json"
''',
                '''        self.settings_file = self.project_root / "data" / "settings.json"
        self.playback_session_file = self.project_root / "data" / "playback_session.json"
''',
                "添加播放状态文件路径",
            )
        else:
            raise RuntimeError("没有找到 data 文件路径区域，无法加入 playback_session_file。")

    if "self.playback_session = self.load_playback_session()" not in text:
        if "self.lyrics_bindings = self.load_lyrics_bindings()" in text:
            text = replace_once(
                text,
                '''        self.lyrics_bindings = self.load_lyrics_bindings()
''',
                '''        self.lyrics_bindings = self.load_lyrics_bindings()
        self.playback_session = self.load_playback_session()
        self.restored_playback_session = False
''',
                "初始化播放状态数据",
            )
        elif "self.song_stats = self.load_song_stats()" in text:
            text = replace_once(
                text,
                '''        self.song_stats = self.load_song_stats()
''',
                '''        self.song_stats = self.load_song_stats()
        self.playback_session = self.load_playback_session()
        self.restored_playback_session = False
''',
                "初始化播放状态数据",
            )
        else:
            raise RuntimeError("没有找到数据初始化区域，无法加入 playback_session。")

    if "self.session_save_timer" not in text:
        if "self.immersive_lyrics_window" in text:
            text = replace_once(
                text,
                '''        self.immersive_lyrics_window: ImmersiveLyricsWindow | None = None
''',
                '''        self.immersive_lyrics_window: ImmersiveLyricsWindow | None = None

        self.session_save_timer = QTimer(self)
        self.session_save_timer.timeout.connect(self.save_playback_session)
        self.session_save_timer.start(5000)
''',
                "添加播放状态定时保存",
            )
        elif "self.displayed_lyrics_song_path" in text:
            text = replace_once(
                text,
                '''        self.displayed_lyrics_song_path: str | None = None
''',
                '''        self.displayed_lyrics_song_path: str | None = None

        self.session_save_timer = QTimer(self)
        self.session_save_timer.timeout.connect(self.save_playback_session)
        self.session_save_timer.start(5000)
''',
                "添加播放状态定时保存",
            )
        else:
            raise RuntimeError("没有找到适合添加 session_save_timer 的位置。")

    if "def load_playback_session" not in text:
        text = insert_before_method(text, "load_settings", SESSION_METHODS)

    if "def showEvent" not in text:
        if "def closeEvent" in text:
            text = insert_before_method(text, "closeEvent", SHOW_EVENT_METHOD)
        else:
            text = insert_before_method(text, "dragEnterEvent", SHOW_EVENT_METHOD)

    if "self.save_playback_session()" not in text:
        if "self.save_song_stats()" in text:
            text = replace_once(
                text,
                '''        self.save_song_stats()
''',
                '''        self.save_song_stats()
        self.save_playback_session()
''',
                "关闭时保存播放状态",
            )
        else:
            raise RuntimeError("没有找到 closeEvent 里的 save_song_stats，无法加入关闭保存。")

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
    print("升级完成：v0.5.0 恢复上次播放已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
