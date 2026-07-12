import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0531"


QUEUE_PAGE_METHODS = r'''    def get_main_stack_widget(self):
        possible_names = [
            "content_stack",
            "main_stack",
            "page_stack",
            "stacked_widget",
            "stack",
            "center_stack",
        ]

        for name in possible_names:
            stack = getattr(self, name, None)

            if isinstance(stack, QStackedWidget):
                return stack

        stacks = self.findChildren(QStackedWidget)

        if not stacks:
            return None

        stacks.sort(key=lambda item: item.count(), reverse=True)
        return stacks[0]

    def ensure_play_queue_page(self) -> None:
        if hasattr(self, "play_queue_page") and self.play_queue_page is not None:
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            QMessageBox.information(self, "播放列表", "没有找到主页面容器，暂时无法切换到播放列表页面。")
            return

        self.play_queue_page = QFrame()
        self.play_queue_page.setObjectName("playQueuePage")

        layout = QVBoxLayout(self.play_queue_page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(6)

        title = QLabel("播放列表")
        title.setObjectName("playQueuePageTitle")

        subtitle = QLabel("这里显示接下来会优先播放的歌曲。右键音乐库里的歌曲，可以选择“下一首播放”或“加入播放队列”。")
        subtitle.setObjectName("playQueuePageSubtitle")
        subtitle.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.play_queue_back_btn = QPushButton("返回音乐库")
        self.play_queue_back_btn.setObjectName("playQueuePageSecondaryButton")
        self.play_queue_back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_queue_back_btn.clicked.connect(self.return_from_play_queue_page)

        header.addLayout(title_box, 1)
        header.addWidget(self.play_queue_back_btn)

        self.play_queue_page_list = QListWidget()
        self.play_queue_page_list.setObjectName("playQueuePageList")
        self.play_queue_page_list.itemDoubleClicked.connect(self.play_selected_queue_page_song)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)

        self.queue_page_play_btn = QPushButton("立即播放")
        self.queue_page_play_btn.setObjectName("playQueuePagePrimaryButton")
        self.queue_page_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_play_btn.clicked.connect(self.play_selected_queue_page_song)

        self.queue_page_remove_btn = QPushButton("移除")
        self.queue_page_remove_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_remove_btn.clicked.connect(self.remove_selected_queue_page_song)

        self.queue_page_up_btn = QPushButton("上移")
        self.queue_page_up_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_up_btn.clicked.connect(self.move_selected_queue_page_song_up)

        self.queue_page_down_btn = QPushButton("下移")
        self.queue_page_down_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_down_btn.clicked.connect(self.move_selected_queue_page_song_down)

        self.queue_page_clear_btn = QPushButton("清空队列")
        self.queue_page_clear_btn.setObjectName("playQueuePageDangerButton")
        self.queue_page_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_clear_btn.clicked.connect(self.clear_queue_from_page)

        button_row.addWidget(self.queue_page_play_btn)
        button_row.addWidget(self.queue_page_remove_btn)
        button_row.addWidget(self.queue_page_up_btn)
        button_row.addWidget(self.queue_page_down_btn)
        button_row.addStretch(1)
        button_row.addWidget(self.queue_page_clear_btn)

        self.play_queue_page_hint = QLabel("播放队列为空。")
        self.play_queue_page_hint.setObjectName("playQueuePageHint")
        self.play_queue_page_hint.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self.play_queue_page_list, 1)
        layout.addLayout(button_row)
        layout.addWidget(self.play_queue_page_hint)

        self.play_queue_page.setStyleSheet(
            "QFrame#playQueuePage { background: transparent; color: #e8ecf5; }"
            "QLabel#playQueuePageTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#playQueuePageSubtitle { color: #9ca5b5; font-size: 13px; }"
            "QLabel#playQueuePageHint { color: #8f98a8; font-size: 12px; }"
            "QListWidget#playQueuePageList { background: #171a22; color: #e8ecf5; border: 1px solid #252a35; border-radius: 16px; padding: 8px; outline: none; }"
            "QListWidget#playQueuePageList::item { padding: 13px 12px; border-radius: 10px; }"
            "QListWidget#playQueuePageList::item:hover { background: #232936; }"
            "QListWidget#playQueuePageList::item:selected { background: #2f68d8; color: #ffffff; }"
            "QPushButton#playQueuePagePrimaryButton { background: #2f68d8; color: #ffffff; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; font-weight: 700; }"
            "QPushButton#playQueuePagePrimaryButton:hover { background: #3d7af0; }"
            "QPushButton#playQueuePageSecondaryButton { background: #232833; color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#playQueuePageSecondaryButton:hover { background: #303747; }"
            "QPushButton#playQueuePageDangerButton { background: #3a2024; color: #ffd7dd; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#playQueuePageDangerButton:hover { background: #71303a; color: #ffffff; }"
        )

        stack.addWidget(self.play_queue_page)

    def show_play_queue_page(self) -> None:
        self.ensure_play_queue_page()

        if not hasattr(self, "play_queue_page") or self.play_queue_page is None:
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            return

        self.play_queue_previous_stack_index = stack.currentIndex()

        if hasattr(self, "set_right_panel_mode"):
            self.set_right_panel_mode("normal")

        self.refresh_play_queue_page()
        stack.setCurrentWidget(self.play_queue_page)

    def return_from_play_queue_page(self) -> None:
        if hasattr(self, "show_library_page"):
            self.show_library_page()
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            return

        previous_index = getattr(self, "play_queue_previous_stack_index", 0)

        if previous_index < 0 or previous_index >= stack.count():
            previous_index = 0

        stack.setCurrentIndex(previous_index)

    def refresh_play_queue_page(self) -> None:
        if not hasattr(self, "play_queue_page_list"):
            return

        if not hasattr(self, "play_queue"):
            self.play_queue = []

        valid_queue = []

        for song_path in self.play_queue:
            normalized_path = self.normalize_song_path(song_path)

            if normalized_path and Path(normalized_path).exists():
                valid_queue.append(normalized_path)

        if valid_queue != self.play_queue:
            self.play_queue = valid_queue
            self.save_play_queue()

        self.play_queue_page_list.clear()

        for index, song_path in enumerate(self.play_queue, start=1):
            song_title = self.get_song_title_for_queue(song_path)
            item = QListWidgetItem(f"{index}. {song_title}")
            item.setData(Qt.ItemDataRole.UserRole, song_path)
            self.play_queue_page_list.addItem(item)

        if self.play_queue_page_list.count() > 0 and self.play_queue_page_list.currentRow() < 0:
            self.play_queue_page_list.setCurrentRow(0)

        count = self.play_queue_page_list.count()

        if count == 0:
            self.play_queue_page_hint.setText("播放队列是空的。可以在音乐库里右键歌曲，选择“下一首播放”或“加入播放队列”。")
        else:
            self.play_queue_page_hint.setText(f"队列里有 {count} 首歌。双击歌曲可以立即播放。")

        try:
            self.update_play_queue_nav_badge()
        except Exception:
            pass

    def get_selected_queue_page_index(self) -> int:
        if not hasattr(self, "play_queue_page_list"):
            return -1

        row = self.play_queue_page_list.currentRow()

        if row < 0 or row >= len(self.play_queue):
            QMessageBox.information(self, "播放列表", "请先选择播放列表里的一首歌。")
            return -1

        return row

    def play_selected_queue_page_song(self) -> None:
        row = self.get_selected_queue_page_index()

        if row < 0:
            return

        song_path = self.play_queue.pop(row)
        self.save_play_queue()

        if self.play_song_from_queue_path(song_path):
            self.refresh_play_queue_page()
        else:
            QMessageBox.information(self, "播放列表", "这首歌无法播放，可能文件已经不存在。")
            self.refresh_play_queue_page()

    def remove_selected_queue_page_song(self) -> None:
        row = self.get_selected_queue_page_index()

        if row < 0:
            return

        self.play_queue.pop(row)
        self.save_play_queue()
        self.refresh_play_queue_page()

        if self.play_queue_page_list.count() > 0:
            self.play_queue_page_list.setCurrentRow(min(row, self.play_queue_page_list.count() - 1))

    def move_selected_queue_page_song_up(self) -> None:
        row = self.get_selected_queue_page_index()

        if row <= 0:
            return

        self.play_queue[row - 1], self.play_queue[row] = self.play_queue[row], self.play_queue[row - 1]
        self.save_play_queue()
        self.refresh_play_queue_page()
        self.play_queue_page_list.setCurrentRow(row - 1)

    def move_selected_queue_page_song_down(self) -> None:
        row = self.get_selected_queue_page_index()

        if row < 0 or row >= len(self.play_queue) - 1:
            return

        self.play_queue[row + 1], self.play_queue[row] = self.play_queue[row], self.play_queue[row + 1]
        self.save_play_queue()
        self.refresh_play_queue_page()
        self.play_queue_page_list.setCurrentRow(row + 1)

    def clear_queue_from_page(self) -> None:
        if not self.play_queue:
            QMessageBox.information(self, "播放列表", "播放列表已经是空的。")
            return

        reply = QMessageBox.question(
            self,
            "清空播放列表",
            "确定要清空当前播放列表吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.play_queue.clear()
        self.save_play_queue()
        self.refresh_play_queue_page()
'''


NEW_SHOW_PLAY_QUEUE = r'''    def show_play_queue(self) -> None:
        self.show_play_queue_page()
'''


def read_text() -> str:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    return MAIN_WINDOW_FILE.read_text(encoding="utf-8")


def write_text(text: str) -> None:
    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")


def ensure_import_names(text: str, module: str, names_to_add: list[str]) -> str:
    pattern = re.compile(rf"from {re.escape(module)} import \((.*?)\)", flags=re.S)
    match = pattern.search(text)

    if match:
        raw = match.group(1)
        names = [line.strip().rstrip(",") for line in raw.splitlines() if line.strip()]

        for name in names_to_add:
            if name not in names:
                names.append(name)

        names = sorted(set(names), key=lambda item: item.lower())
        new_import = f"from {module} import (\n" + "".join(f"    {name},\n" for name in names) + ")"
        return text[:match.start()] + new_import + text[match.end():]

    pattern = re.compile(rf"from {re.escape(module)} import ([^\n]+)")
    match = pattern.search(text)

    if match:
        names = [name.strip() for name in match.group(1).split(",")]

        for name in names_to_add:
            if name not in names:
                names.append(name)

        new_import = f"from {module} import " + ", ".join(sorted(set(names), key=lambda item: item.lower()))
        return text[:match.start()] + new_import + text[match.end():]

    raise RuntimeError(f"没有找到导入：{module}")


def ensure_imports(text: str) -> str:
    text = ensure_import_names(
        text,
        "PySide6.QtWidgets",
        [
            "QFrame",
            "QListWidget",
            "QListWidgetItem",
            "QStackedWidget",
        ],
    )

    return text


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.3.1 (local music player prototype)",
        "HushPlayer/0.5.3 (local music player prototype)",
        "HushPlayer/0.5.2 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.3.2 (local music player prototype)")

    return text


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def insert_queue_page_methods(text: str) -> str:
    if "def show_play_queue_page" in text:
        return text

    if "\n    def show_play_queue(" in text:
        return text.replace("\n    def show_play_queue(", "\n" + QUEUE_PAGE_METHODS.rstrip() + "\n\n    def show_play_queue(", 1)

    if "\n    def install_playlist_button_hook(" in text:
        return text.replace("\n    def install_playlist_button_hook(", "\n" + QUEUE_PAGE_METHODS.rstrip() + "\n\n    def install_playlist_button_hook(", 1)

    raise RuntimeError("没有找到插入播放列表页面方法的位置。")


def patch_refresh_on_save(text: str) -> str:
    if "self.refresh_play_queue_page()" in text and "def save_play_queue" in text:
        return text

    pattern = re.compile(r"\n    def save_play_queue\(self\).*?\n(?=    def |\Z)", flags=re.S)
    match = pattern.search(text)

    if not match:
        return text

    method_text = match.group(0)

    marker = '''        try:
            self.update_play_queue_nav_badge()
        except Exception:
            pass
'''

    if marker in method_text:
        new_marker = marker + '''        try:
            self.refresh_play_queue_page()
        except Exception:
            pass
'''
        method_text = method_text.replace(marker, new_marker, 1)
    else:
        method_text = method_text.rstrip() + '''

        try:
            self.update_play_queue_nav_badge()
        except Exception:
            pass

        try:
            self.refresh_play_queue_page()
        except Exception:
            pass
'''

    return text[:match.start()] + method_text + "\n" + text[match.end():]


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    if "def show_play_queue" not in text:
        raise RuntimeError("没有找到 show_play_queue。请先确认播放队列功能已经实现。")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = insert_queue_page_methods(text)
    text = replace_method(text, "show_play_queue", NEW_SHOW_PLAY_QUEUE)
    text = patch_refresh_on_save(text)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.3.2 播放列表已改为主界面页面。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
