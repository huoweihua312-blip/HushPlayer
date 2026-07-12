import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v052"


PLAY_QUEUE_DIALOG_CLASS = r'''class PlayQueueDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("播放队列")
        self.setObjectName("playQueueDialog")
        self.setMinimumSize(620, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("播放队列")
        title.setObjectName("playQueueDialogTitle")

        subtitle = QLabel("这里显示接下来会优先播放的歌曲。队列里的歌会先于列表循环 / 随机播放。")
        subtitle.setObjectName("playQueueDialogSubtitle")
        subtitle.setWordWrap(True)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("playQueueList")
        self.queue_list.itemDoubleClicked.connect(self.play_selected_song)

        main_buttons = QHBoxLayout()
        main_buttons.setContentsMargins(0, 0, 0, 0)
        main_buttons.setSpacing(10)

        self.play_btn = QPushButton("立即播放")
        self.play_btn.setObjectName("queuePrimaryButton")
        self.play_btn.clicked.connect(self.play_selected_song)

        self.remove_btn = QPushButton("移除")
        self.remove_btn.setObjectName("queueSecondaryButton")
        self.remove_btn.clicked.connect(self.remove_selected_song)

        self.move_up_btn = QPushButton("上移")
        self.move_up_btn.setObjectName("queueSecondaryButton")
        self.move_up_btn.clicked.connect(self.move_selected_song_up)

        self.move_down_btn = QPushButton("下移")
        self.move_down_btn.setObjectName("queueSecondaryButton")
        self.move_down_btn.clicked.connect(self.move_selected_song_down)

        self.clear_btn = QPushButton("清空队列")
        self.clear_btn.setObjectName("queueDangerButton")
        self.clear_btn.clicked.connect(self.clear_queue)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("queueSecondaryButton")
        self.close_btn.clicked.connect(self.accept)

        main_buttons.addWidget(self.play_btn)
        main_buttons.addWidget(self.remove_btn)
        main_buttons.addWidget(self.move_up_btn)
        main_buttons.addWidget(self.move_down_btn)
        main_buttons.addStretch(1)
        main_buttons.addWidget(self.clear_btn)
        main_buttons.addWidget(self.close_btn)

        self.hint_label = QLabel("双击队列里的歌曲可以立即播放。")
        self.hint_label.setObjectName("playQueueHint")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.queue_list, 1)
        layout.addLayout(main_buttons)
        layout.addWidget(self.hint_label)

        self.apply_style()
        self.refresh_queue_list()

    def apply_style(self) -> None:
        self.setStyleSheet(
            "QDialog#playQueueDialog { background: #101217; color: #e8ecf5; font-family: 'Microsoft YaHei UI'; }"
            "QLabel#playQueueDialogTitle { color: #ffffff; font-size: 26px; font-weight: 900; }"
            "QLabel#playQueueDialogSubtitle { color: #9ca5b5; font-size: 13px; }"
            "QLabel#playQueueHint { color: #8f98a8; font-size: 12px; }"
            "QListWidget#playQueueList { background: #171a22; color: #e8ecf5; border: 1px solid #252a35; border-radius: 16px; padding: 8px; outline: none; }"
            "QListWidget#playQueueList::item { padding: 12px 10px; border-radius: 10px; }"
            "QListWidget#playQueueList::item:hover { background: #232936; }"
            "QListWidget#playQueueList::item:selected { background: #2f68d8; color: #ffffff; }"
            "QPushButton#queuePrimaryButton { background: #2f68d8; color: #ffffff; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; font-weight: 700; }"
            "QPushButton#queuePrimaryButton:hover { background: #3d7af0; }"
            "QPushButton#queueSecondaryButton { background: #232833; color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#queueSecondaryButton:hover { background: #303747; }"
            "QPushButton#queueDangerButton { background: #3a2024; color: #ffd7dd; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#queueDangerButton:hover { background: #71303a; color: #ffffff; }"
        )

    def refresh_queue_list(self) -> None:
        if not hasattr(self.main_window, "play_queue"):
            self.main_window.play_queue = []

        valid_queue = []

        for song_path in self.main_window.play_queue:
            normalized_path = self.main_window.normalize_song_path(song_path)

            if normalized_path and Path(normalized_path).exists():
                valid_queue.append(normalized_path)

        if valid_queue != self.main_window.play_queue:
            self.main_window.play_queue = valid_queue
            self.main_window.save_play_queue()

        self.queue_list.clear()

        for index, song_path in enumerate(self.main_window.play_queue, start=1):
            song_title = self.main_window.get_song_title_for_queue(song_path)
            item = QListWidgetItem(f"{index}. {song_title}")
            item.setData(Qt.ItemDataRole.UserRole, song_path)
            self.queue_list.addItem(item)

        if self.queue_list.count() > 0 and self.queue_list.currentRow() < 0:
            self.queue_list.setCurrentRow(0)

        self.update_hint()

    def update_hint(self) -> None:
        count = self.queue_list.count()

        if count == 0:
            self.hint_label.setText("播放队列是空的。可以在音乐库里右键歌曲，选择“下一首播放”或“加入播放队列”。")
        else:
            self.hint_label.setText(f"队列里有 {count} 首歌。双击歌曲可以立即播放。")

    def get_selected_index(self) -> int:
        row = self.queue_list.currentRow()

        if row < 0 or row >= len(self.main_window.play_queue):
            QMessageBox.information(self, "播放队列", "请先选择队列里的一首歌。")
            return -1

        return row

    def play_selected_song(self) -> None:
        row = self.get_selected_index()

        if row < 0:
            return

        song_path = self.main_window.play_queue.pop(row)
        self.main_window.save_play_queue()

        if self.main_window.play_song_from_queue_path(song_path):
            self.refresh_queue_list()
            self.accept()
        else:
            QMessageBox.information(self, "播放队列", "这首歌无法播放，可能文件已经不存在。")
            self.refresh_queue_list()

    def remove_selected_song(self) -> None:
        row = self.get_selected_index()

        if row < 0:
            return

        self.main_window.play_queue.pop(row)
        self.main_window.save_play_queue()
        self.refresh_queue_list()

        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(min(row, self.queue_list.count() - 1))

    def move_selected_song_up(self) -> None:
        row = self.get_selected_index()

        if row <= 0:
            return

        queue = self.main_window.play_queue
        queue[row - 1], queue[row] = queue[row], queue[row - 1]
        self.main_window.save_play_queue()
        self.refresh_queue_list()
        self.queue_list.setCurrentRow(row - 1)

    def move_selected_song_down(self) -> None:
        row = self.get_selected_index()

        if row < 0 or row >= len(self.main_window.play_queue) - 1:
            return

        queue = self.main_window.play_queue
        queue[row + 1], queue[row] = queue[row], queue[row + 1]
        self.main_window.save_play_queue()
        self.refresh_queue_list()
        self.queue_list.setCurrentRow(row + 1)

    def clear_queue(self) -> None:
        if not self.main_window.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列已经是空的。")
            return

        reply = QMessageBox.question(
            self,
            "清空播放队列",
            "确定要清空当前播放队列吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.main_window.play_queue.clear()
        self.main_window.save_play_queue()
        self.refresh_queue_list()
'''


NEW_SHOW_PLAY_QUEUE = r'''    def show_play_queue(self) -> None:
        dialog = PlayQueueDialog(self)
        dialog.exec()
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
    return ensure_import_names(
        text,
        "PySide6.QtWidgets",
        [
            "QDialog",
            "QListWidget",
            "QListWidgetItem",
        ],
    )


def ensure_version(text: str) -> str:
    versions = (
        "HushPlayer/0.5.2 (local music player prototype)",
        "HushPlayer/0.5.1.1 (local music player prototype)",
        "HushPlayer/0.5.1 (local music player prototype)",
    )

    for version in versions:
        text = text.replace(version, "HushPlayer/0.5.3 (local music player prototype)")

    return text


def insert_play_queue_dialog_class(text: str) -> str:
    if "class PlayQueueDialog(QDialog):" in text:
        return text

    marker = "\nclass SettingsDialog(QDialog):"

    if marker in text:
        return text.replace(marker, "\n" + PLAY_QUEUE_DIALOG_CLASS.strip() + "\n\nclass SettingsDialog(QDialog):", 1)

    marker = "\nclass ImmersiveLyricsWindow(QWidget):"

    if marker in text:
        return text.replace(marker, "\n" + PLAY_QUEUE_DIALOG_CLASS.strip() + "\n\nclass ImmersiveLyricsWindow(QWidget):", 1)

    marker = "\nclass MainWindow(QMainWindow):"

    if marker in text:
        return text.replace(marker, "\n" + PLAY_QUEUE_DIALOG_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):", 1)

    raise RuntimeError("没有找到插入 PlayQueueDialog 的位置。")


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def main() -> None:
    text = read_text()
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    if "def show_play_queue" not in text:
        raise RuntimeError("没有找到 show_play_queue。请先确认播放队列功能已经实现。")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = insert_play_queue_dialog_class(text)
    text = replace_method(text, "show_play_queue", NEW_SHOW_PLAY_QUEUE)

    write_text(text)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print("升级完成：v0.5.3 播放队列面板已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
