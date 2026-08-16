"""Background music-folder scanning shared by the formal UI runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from mutagen import File as MutagenFile
from PySide6.QtCore import QObject, QThread, Qt, Signal


AUDIO_EXTENSIONS = frozenset({
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
})


class MusicFolderScanWorker(QObject):
    """Scan files and read metadata without touching UI or persistence."""

    progress = Signal(int, object)
    finished = Signal(int, object)

    def __init__(
        self,
        task_id: int,
        entries: list[str],
        existing_paths: list[str] = (),
        pending_paths: list[str] | None = None,
        ignored_paths: list[str] | None = None,
        *,
        folders_only: bool = False,
        casefold_paths: bool = True,
        include_duration: bool = True,
        sort_folder_paths: bool = False,
    ) -> None:
        super().__init__()
        self.task_id = int(task_id)
        self.entries = list(entries)
        self.existing_paths = set(existing_paths)
        self.pending_paths = set(pending_paths or ())
        self.ignored_paths = set(ignored_paths or ())
        self.folders_only = bool(folders_only)
        self.casefold_paths = bool(casefold_paths)
        self.include_duration = bool(include_duration)
        self.sort_folder_paths = bool(sort_folder_paths)
        self.cancel_requested = False
        self.last_progress_at = 0.0

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def is_cancelled(self) -> bool:
        if self.cancel_requested:
            return True
        thread = QThread.currentThread()
        return bool(thread and thread.isInterruptionRequested())

    def path_key(self, path_text: str) -> str:
        return path_text.lower() if self.casefold_paths else path_text

    def emit_progress(
        self,
        phase: str,
        processed: int,
        total: int,
        *,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        if not force and processed % 25 != 0 and now - self.last_progress_at < 0.12:
            return
        self.last_progress_at = now
        self.progress.emit(
            self.task_id,
            {
                "phase": str(phase),
                "processed": max(0, int(processed)),
                "total": max(0, int(total)),
            },
        )

    def run(self) -> None:
        result = {
            "ok": True,
            "cancelled": False,
            "scan_ms": 0.0,
            "metadata_ms": 0.0,
            "scanned": 0,
            "new_songs": [],
            "duplicates": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "metadata_errors": [],
        }
        try:
            self.scan_entries(result)
        except Exception as error:  # report worker failures through the result
            result["ok"] = False
            result["errors"].append(str(error))
        result["cancelled"] = self.is_cancelled()
        self.finished.emit(self.task_id, result)

    @staticmethod
    def is_link_or_junction(path: Path) -> bool:
        try:
            if path.is_symlink():
                return True
            is_junction = getattr(path, "is_junction", None)
            return bool(callable(is_junction) and is_junction())
        except OSError:
            return True

    def scan_entries(self, result: dict) -> None:
        scan_started_at = time.perf_counter()
        seen_paths = {
            self.path_key(path)
            for path in (
                set(self.existing_paths)
                | set(self.pending_paths)
                | set(self.ignored_paths)
            )
        }
        candidates: list[tuple[Path, str]] = []
        self.emit_progress("scanning", 0, 0, force=True)

        for entry_text in self.entries:
            if self.is_cancelled():
                return
            entry_text = str(entry_text).strip()
            if not entry_text:
                continue
            raw_path = Path(entry_text).expanduser()
            try:
                if raw_path.is_symlink():
                    raise OSError("已跳过符号链接或目录联接")
                path = raw_path.resolve()
            except Exception as error:
                result["failed"] += 1
                result["errors"].append(f"{entry_text}: {error}")
                continue

            try:
                is_directory = path.is_dir()
                is_file = path.is_file()
            except OSError as error:
                result["failed"] += 1
                result["errors"].append(f"{entry_text}: {error}")
                continue

            if is_directory and self.is_link_or_junction(raw_path):
                result["failed"] += 1
                result["errors"].append(f"已跳过符号链接或目录联接：{entry_text}")
                continue
            if is_file and not self.folders_only:
                if path.suffix.lower() in AUDIO_EXTENSIONS:
                    candidates.append((path, str(path.parent)))
                else:
                    result["skipped"] += 1
                continue
            if not is_directory:
                result["failed"] += 1
                result["errors"].append(f"路径不可用：{entry_text}")
                continue

            def on_walk_error(error) -> None:
                result["failed"] += 1
                result["errors"].append(str(error))

            source_folder = str(path)
            visited_directories: set[str] = set()
            folder_candidate_start = len(candidates)
            for root, directory_names, file_names in os.walk(
                path,
                topdown=True,
                onerror=on_walk_error,
                followlinks=False,
            ):
                if self.is_cancelled():
                    return
                root_path = Path(root)
                try:
                    root_key = str(root_path.resolve()).lower()
                except Exception as error:
                    result["failed"] += 1
                    result["errors"].append(f"{root_path}: {error}")
                    directory_names[:] = []
                    continue
                if root_key in visited_directories:
                    directory_names[:] = []
                    continue
                visited_directories.add(root_key)
                directory_iterator = (
                    sorted(directory_names, key=str.lower)
                    if self.sort_folder_paths
                    else list(directory_names)
                )
                safe_directories = [
                    name
                    for name in directory_iterator
                    if not self.is_link_or_junction(root_path / name)
                ]
                directory_names[:] = safe_directories
                if self.sort_folder_paths:
                    file_names.sort(key=str.lower)
                for file_name in file_names:
                    candidate = root_path / file_name
                    if candidate.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue
                    try:
                        if candidate.is_symlink():
                            continue
                    except OSError:
                        continue
                    candidates.append((candidate, source_folder))
                self.emit_progress("scanning", len(candidates), 0)
            if self.sort_folder_paths:
                candidates[folder_candidate_start:] = sorted(
                    candidates[folder_candidate_start:],
                    key=lambda item: str(item[0]).lower(),
                )

        total = len(candidates)
        result["scan_ms"] = (time.perf_counter() - scan_started_at) * 1000
        metadata_started_at = time.perf_counter()
        self.emit_progress("metadata", 0, total, force=True)
        for index, (path, source_folder) in enumerate(candidates, start=1):
            if self.is_cancelled():
                return
            result["scanned"] += 1
            try:
                normalized_path = str(path.resolve())
            except Exception as error:
                result["failed"] += 1
                result["errors"].append(f"{path}: {error}")
                self.emit_progress("metadata", index, total)
                continue
            normalized_key = self.path_key(normalized_path)
            if normalized_key in seen_paths:
                result["duplicates"] += 1
                self.emit_progress("metadata", index, total)
                continue
            try:
                if not path.is_file():
                    result["failed"] += 1
                    self.emit_progress("metadata", index, total)
                    continue
            except OSError as error:
                result["failed"] += 1
                result["errors"].append(f"{path}: {error}")
                self.emit_progress("metadata", index, total)
                continue
            title, artist, album, metadata_error = self.read_audio_metadata(path)
            if metadata_error:
                result["metadata_errors"].append(metadata_error)
            try:
                if not path.is_file():
                    result["failed"] += 1
                    self.emit_progress("metadata", index, total)
                    continue
            except OSError as error:
                result["failed"] += 1
                result["errors"].append(f"{path}: {error}")
                self.emit_progress("metadata", index, total)
                continue
            song_data = {
                "title": title,
                "artist": artist,
                "album": album,
                "path": normalized_path,
                "added_at": int(time.time()) + len(result["new_songs"]),
                "demo": False,
            }
            if self.include_duration:
                song_data.update(
                    {
                        "duration": self.read_audio_duration(path),
                        "format": path.suffix.lower().lstrip("."),
                        "source_folder": source_folder,
                        "found_at": int(time.time()),
                    }
                )
            result["new_songs"].append(song_data)
            seen_paths.add(normalized_key)
            self.emit_progress("metadata", index, total)
        self.emit_progress("metadata", total, total, force=True)
        result["metadata_ms"] = (time.perf_counter() - metadata_started_at) * 1000

    @staticmethod
    def read_audio_metadata(path: Path) -> tuple[str, str, str, str]:
        title = path.stem
        artist = "未知艺术家"
        album = "未知专辑"
        error_message = ""
        try:
            audio = MutagenFile(path, easy=True)
            if audio is None or audio.tags is None:
                return title, artist, album, error_message
            title = audio.tags.get("title", [title])[0]
            artist = audio.tags.get("artist", [artist])[0]
            album = audio.tags.get("album", [album])[0]
        except Exception as error:
            error_message = f"{path}: {error}"
        return (
            str(title or path.stem),
            str(artist or "未知艺术家"),
            str(album or "未知专辑"),
            error_message,
        )

    @staticmethod
    def read_audio_duration(path: Path) -> int:
        try:
            audio = MutagenFile(path)
            info = getattr(audio, "info", None)
            return int(round(float(getattr(info, "length", 0) or 0)))
        except Exception:
            return 0


def _read_json_document(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    return value


def _write_json_document(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


class MusicFolderImportService(QObject):
    """Own scan-thread lifecycle and legacy-compatible import persistence."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        library_path: Path,
        pending_imports_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.library_path = Path(library_path)
        self.pending_imports_path = Path(pending_imports_path)
        self.ignored_imports_path = self.library_path.parent / "ignored_imports.json"
        self._task_id = 0
        self._worker: MusicFolderScanWorker | None = None
        self._thread: QThread | None = None
        self._direct_import = False
        self._import_mode = "pending"
        self._closed = False

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(
        self,
        entries: list[str],
        *,
        import_mode: str = "pending",
        direct_import: bool = False,
    ) -> bool:
        if self._closed or self.busy:
            return False
        cleaned_entries = [str(entry).strip() for entry in entries if str(entry).strip()]
        if not cleaned_entries:
            return False

        library = _read_json_document(self.library_path, [])
        pending = _read_json_document(self.pending_imports_path, [])
        library = library if isinstance(library, list) else []
        pending = pending if isinstance(pending, list) else []
        existing_paths = [
            str(item.get("path"))
            for item in library
            if isinstance(item, dict) and item.get("path")
        ]
        pending_paths = [
            str(item.get("path"))
            for item in pending
            if isinstance(item, dict) and item.get("path")
        ]
        ignored = _read_json_document(self.ignored_imports_path, [])
        ignored_paths = [str(item) for item in ignored] if isinstance(ignored, list) else []
        self._task_id += 1
        self._direct_import = bool(direct_import)
        self._import_mode = "direct" if direct_import else str(import_mode or "pending")
        if self._import_mode not in {"pending", "auto", "direct"}:
            self._import_mode = "pending"

        worker = MusicFolderScanWorker(
            self._task_id,
            cleaned_entries,
            existing_paths,
            pending_paths,
            ignored_paths,
            folders_only=not direct_import,
            casefold_paths=not direct_import,
            include_duration=not direct_import,
            sort_folder_paths=bool(direct_import),
        )
        thread = QThread(self)
        thread.setObjectName(f"music-import-{self._task_id}")
        worker.moveToThread(thread)
        worker.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(self._on_thread_finished, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        self._worker = worker
        self._thread = thread
        self.busy_changed.emit(True)
        thread.start()
        return True

    def cancel(self) -> None:
        worker = self._worker
        thread = self._thread
        if worker is not None:
            worker.request_cancel()
        if thread is not None and thread.isRunning():
            thread.requestInterruption()

    def shutdown(self, timeout_ms: int = 2_000) -> None:
        self._closed = True
        self.cancel()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(max(1, int(timeout_ms)))
        self._worker = None
        self._thread = None

    def _on_progress(self, task_id: int, payload: object) -> None:
        if int(task_id) != self._task_id or not isinstance(payload, dict):
            return
        self.progress.emit(dict(payload))

    def _on_worker_finished(self, task_id: int, result: object) -> None:
        if int(task_id) != self._task_id:
            return
        if not isinstance(result, dict):
            self.failed.emit("音乐扫描返回了无效结果。")
            return
        try:
            if not result.get("cancelled"):
                result = self._apply_result(dict(result))
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self.busy_changed.emit(False)

    def _apply_result(self, result: dict) -> dict:
        songs = [item for item in result.get("new_songs", ()) if isinstance(item, dict)]
        if not songs:
            result.update({"added_count": 0, "pending_count": 0})
            return result
        library = _read_json_document(self.library_path, [])
        pending = _read_json_document(self.pending_imports_path, [])
        library = library if isinstance(library, list) else []
        pending = pending if isinstance(pending, list) else []
        mode = self._import_mode
        final_records = library if mode in {"auto", "direct"} else pending
        final_keys = {
            str(item.get("path")).casefold() if not self._direct_import else str(item.get("path"))
            for item in final_records
            if isinstance(item, dict) and item.get("path")
        }
        added_count = 0
        pending_count = 0
        now = int(time.time())
        for raw_song in songs:
            song = dict(raw_song)
            path = str(song.get("path") or "")
            key = path if self._direct_import else path.casefold()
            if not path or key in final_keys:
                result["duplicates"] = int(result.get("duplicates", 0) or 0) + 1
                continue
            final_keys.add(key)
            if mode == "pending":
                song.setdefault("duration", 0)
                song.setdefault("format", Path(path).suffix.lower().lstrip("."))
                song.setdefault("source_folder", str(Path(path).parent))
                song.setdefault("found_at", now)
                song.pop("demo", None)
                pending.append(song)
                pending_count += 1
            else:
                if self._direct_import:
                    for field in ("duration", "format", "source_folder", "found_at"):
                        song.pop(field, None)
                library.append(song)
                added_count += 1
        if added_count:
            _write_json_document(self.library_path, library)
        if pending_count:
            _write_json_document(self.pending_imports_path, pending)
        result.update({"added_count": added_count, "pending_count": pending_count})
        return result
