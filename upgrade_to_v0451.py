import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v045"


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def insert_after(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, marker + content, 1)


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.5.1" in text:
        print("当前文件看起来已经升级到 v0.4.5.1 了，不需要重复升级。")
        return

    if "class CoverSearchWorker(QObject):" not in text or "def start_cover_worker" not in text:
        raise RuntimeError("没有找到 v0.4.5 的后台搜索代码。请先确认已经升级到 v0.4.5。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.5 (local music player prototype)",
        "HushPlayer/0.4.5.1 (local music player prototype)",
    )

    if "self.cover_workers: list[QObject] = []" not in text:
        text = replace_once(
            text,
            '''        self.cover_threads: list[QThread] = []
        self.lyrics_threads: list[QThread] = []
        self.displayed_lyrics_song_path: str | None = None
''',
            '''        self.cover_threads: list[QThread] = []
        self.lyrics_threads: list[QThread] = []
        self.cover_workers: list[QObject] = []
        self.lyrics_workers: list[QObject] = []
        self.displayed_lyrics_song_path: str | None = None
''',
            "添加 worker 引用列表",
        )

    if "def cleanup_worker_reference" not in text:
        text = insert_after(
            text,
            '''    def cleanup_thread_reference(self, thread: QThread, kind: str) -> None:
        try:
            if kind == "cover" and thread in self.cover_threads:
                self.cover_threads.remove(thread)
            elif kind == "lyrics" and thread in self.lyrics_threads:
                self.lyrics_threads.remove(thread)
        except Exception:
            pass

''',
            '''    def cleanup_worker_reference(self, worker: QObject, kind: str) -> None:
        try:
            if kind == "cover" and worker in self.cover_workers:
                self.cover_workers.remove(worker)
            elif kind == "lyrics" and worker in self.lyrics_workers:
                self.lyrics_workers.remove(worker)
        except Exception:
            pass

''',
            "添加 worker 清理函数",
        )

    if "self.cover_workers.append(worker)" not in text:
        text = replace_once(
            text,
            '''        thread = QThread(self)
        worker.moveToThread(thread)
''',
            '''        self.cover_workers.append(worker)

        thread = QThread(self)
        worker.moveToThread(thread)
''',
            "保存封面 worker 引用",
        )

    if "self.lyrics_workers.append(worker)" not in text:
        text = replace_once(
            text,
            '''        thread = QThread(self)
        worker.moveToThread(thread)
''',
            '''        self.lyrics_workers.append(worker)

        thread = QThread(self)
        worker.moveToThread(thread)
''',
            "保存歌词 worker 引用",
        )

    if 'cleanup_worker_reference(worker, "cover")' not in text:
        text = replace_once(
            text,
            '''        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
''',
            '''        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda request_id, result, worker=worker: self.cleanup_worker_reference(worker, "cover"))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
''',
            "封面 worker 结束后清理引用",
        )

    if 'cleanup_worker_reference(worker, "lyrics")' not in text:
        text = replace_once(
            text,
            '''        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
''',
            '''        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda request_id, result, worker=worker: self.cleanup_worker_reference(worker, "lyrics"))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
''',
            "歌词 worker 结束后清理引用",
        )

    old_cover_status = '''    def on_cover_worker_status(self, request_id: str, message: str) -> None:
        if request_id != self.active_cover_request_id:
            return

        print("封面状态：", message)

        if not self.cover_label.pixmap() or self.cover_label.pixmap().isNull():
            self.cover_label.setText(message)
'''

    new_cover_status = '''    def on_cover_worker_status(self, request_id: str, message: str) -> None:
        if request_id != self.active_cover_request_id:
            return

        print("封面状态：", message)
        self.cover_label.setText(message)
'''

    if old_cover_status in text:
        text = text.replace(old_cover_status, new_cover_status, 1)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.5.1 已修复后台 worker 被回收导致一直卡在“正在查找”的问题。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
