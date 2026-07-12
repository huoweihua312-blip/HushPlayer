import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v053"


PLAYLIST_NAV_METHODS = r'''    def install_playlist_button_hook(self) -> None:
        self.playlist_nav_button = None

        for button in self.findChildren(QPushButton):
            button_text = button.text().strip()

            if not button_text.startswith("播放列表"):
                continue

            if button.property("hushPlaylistHooked"):
                self.playlist_nav_button = button
                continue

            try:
                button.clicked.disconnect()
            except Exception:
                pass

            button.clicked.connect(self.show_play_queue)
            button.setProperty("hushPlaylistHooked", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

            self.playlist_nav_button = button

        self.update_play_queue_nav_badge()

    def update_play_queue_nav_badge(self) -> None:
        button = getattr(self, "playlist_nav_button", None)

        if button is None:
            return

        queue = getattr(self, "play_queue", [])
        count = len(queue) if isinstance(queue, list) else 0

        if count > 0:
            button.setText(f"播放列表 ({count})")
        else:
            button.setText("播放列表")
'''


NEW_SAVE_PLAY_QUEUE = r'''    def save_play_queue(self) -> None:
        try:
            self.play_queue_file.parent.mkdir(parents=True, exist_ok=True)

            with self.play_queue_file.open("w", encoding="utf-8") as file:
                json.dump(self.play_queue, file, ensure_ascii=False, indent=2)

            print("播放队列已保存：", self.play_queue_file)

        except Exception as error:
            print("保存播放队列失败：", error)

        try:
            self.update_play_queue_nav_badge()
        except Exception:
            pass
'''


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


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


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.3 (local music player prototype)",
        "HushPlayer/0.5.2 (local music player prototype)",
        "HushPlayer/0.5.1.1 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.3.1 (local music player prototype)")

    return text


def add_methods(text: str) -> str:
    if "def install_playlist_button_hook" in text:
        return text

    if "def install_settings_button_hook" in text:
        return insert_before_method(text, "install_settings_button_hook", PLAYLIST_NAV_METHODS)

    if "def open_settings_dialog" in text:
        return insert_before_method(text, "open_settings_dialog", PLAYLIST_NAV_METHODS)

    if "def show_play_queue" in text:
        return insert_before_method(text, "show_play_queue", PLAYLIST_NAV_METHODS)

    raise RuntimeError("没有找到适合插入播放列表左侧按钮方法的位置。")


def patch_init_call(text: str) -> str:
    if "self.install_playlist_button_hook" in text:
        return text

    if "QTimer.singleShot(0, self.install_settings_button_hook)" in text:
        return text.replace(
            "        QTimer.singleShot(0, self.install_settings_button_hook)\n",
            "        QTimer.singleShot(0, self.install_settings_button_hook)\n        QTimer.singleShot(0, self.install_playlist_button_hook)\n",
            1,
        )

    # 如果没有设置按钮 hook，就插到 MainWindow.__init__ 的末尾附近。
    pattern = re.compile(
        r"(\n    def __init__\(self.*?\):\n.*?)(\n    def )",
        flags=re.S,
    )
    match = pattern.search(text)

    if not match:
        raise RuntimeError("没有找到 MainWindow.__init__，无法安装左侧播放列表入口。")

    init_text = match.group(1).rstrip() + "\n\n        QTimer.singleShot(0, self.install_playlist_button_hook)\n"
    return text[:match.start(1)] + init_text + text[match.start(2):]


def patch_save_play_queue(text: str) -> str:
    if "def save_play_queue" not in text:
        raise RuntimeError("没有找到 save_play_queue。请先确认播放队列功能已经实现。")

    return replace_method(text, "save_play_queue", NEW_SAVE_PLAY_QUEUE)


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    if "def show_play_queue" not in text:
        raise RuntimeError("没有找到 show_play_queue。请先确认播放队列面板已经实现。")

    text = ensure_version(text)
    text = add_methods(text)
    text = patch_init_call(text)
    text = patch_save_play_queue(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.3.1 左侧播放列表已整合播放队列。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
