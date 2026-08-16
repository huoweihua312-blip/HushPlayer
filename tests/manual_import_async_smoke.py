"""Smoke coverage for the UI-independent music-folder scan worker."""

from __future__ import annotations

import os
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.services.music_folder_scan import MusicFolderImportService, MusicFolderScanWorker


def _touch(path: Path, payload: bytes = b"fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class _RecordingWorker(MusicFolderScanWorker):
    worker_thread_id = 0

    def run(self) -> None:
        type(self).worker_thread_id = threading.get_ident()
        super().run()


def _run_worker(app: QApplication, worker: MusicFolderScanWorker) -> dict:
    results: list[tuple[int, dict]] = []
    thread = QThread()
    worker.moveToThread(thread)
    worker.finished.connect(lambda task_id, result: results.append((task_id, result)))
    worker.finished.connect(thread.quit)
    thread.started.connect(worker.run)
    thread.start()
    while thread.isRunning():
        app.processEvents()
        QThread.msleep(2)
    thread.wait(2_000)
    app.processEvents()
    assert results, "the scan worker did not emit a result"
    assert results[0][0] == worker.task_id
    worker.deleteLater()
    thread.deleteLater()
    return results[0][1]


class MusicFolderScanSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.gui_thread_id = threading.get_ident()

    def test_recursive_manual_import_scan_stays_out_of_ui_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer_scan_service_") as temp_dir:
            root = Path(temp_dir)
            first = _touch(root / "music" / "01-first.mp3")
            second = _touch(root / "music" / "nested" / "02-second.flac")
            third = _touch(root / "music" / "nested" / "03-third.wav")
            _touch(root / "music" / "notes.txt")
            existing = str(first.resolve()).lower()
            worker = _RecordingWorker(
                7,
                [str(root / "music"), str(second)],
                existing_paths=[existing],
                pending_paths=[],
                ignored_paths=[],
                folders_only=False,
                casefold_paths=True,
                include_duration=True,
                sort_folder_paths=True,
            )
            result = _run_worker(self.app, worker)

            self.assertTrue(result["ok"])
            self.assertFalse(result["cancelled"])
            self.assertEqual(result["scanned"], 4)
            self.assertEqual(result["duplicates"], 2)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(
                [Path(item["path"]).name for item in result["new_songs"]],
                ["02-second.flac", "03-third.wav"],
            )
            self.assertEqual(
                {item["title"] for item in result["new_songs"]},
                {"02-second", "03-third"},
            )
            self.assertNotEqual(_RecordingWorker.worker_thread_id, self.gui_thread_id)
            self.assertTrue(result["metadata_errors"])

    def test_file_import_skips_unsupported_and_reports_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer_scan_edges_") as temp_dir:
            root = Path(temp_dir)
            audio = _touch(root / "single.mp3")
            note = _touch(root / "single.txt")
            missing = root / "missing.mp3"
            worker = MusicFolderScanWorker(
                8,
                [str(audio), str(note), str(missing)],
                folders_only=False,
                casefold_paths=False,
                include_duration=False,
                sort_folder_paths=True,
            )
            result = _run_worker(self.app, worker)
            self.assertTrue(result["ok"])
            self.assertEqual(result["scanned"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(
                [Path(item["path"]) for item in result["new_songs"]],
                [audio.resolve()],
            )
            self.assertNotIn("duration", result["new_songs"][0])

    def test_cancelled_worker_does_not_publish_partial_imports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer_scan_cancel_") as temp_dir:
            root = Path(temp_dir)
            _touch(root / "cancelled.mp3")
            worker = MusicFolderScanWorker(9, [str(root)])
            worker.request_cancel()
            result = _run_worker(self.app, worker)
            self.assertTrue(result["cancelled"])
            self.assertEqual(result["new_songs"], [])

    def test_import_service_persists_auto_and_pending_results_without_main_window(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer_import_service_") as temp_dir:
            root = Path(temp_dir)
            library_path = root / "data" / "library.json"
            pending_path = root / "data" / "pending_imports.json"
            library_path.parent.mkdir(parents=True)
            library_path.write_text("[]", encoding="utf-8")
            pending_path.write_text("[]", encoding="utf-8")
            auto_file = _touch(root / "auto" / "auto.mp3")
            pending_file = _touch(root / "pending" / "pending.mp3")
            service = MusicFolderImportService(library_path, pending_path)
            completed: list[dict] = []
            failures: list[str] = []
            service.completed.connect(completed.append)
            service.failed.connect(failures.append)
            try:
                self.assertTrue(service.start([str(auto_file)], import_mode="auto", direct_import=True))
                deadline = time.monotonic() + 5
                while not completed and time.monotonic() < deadline:
                    self.app.processEvents()
                    QThread.msleep(2)
                self.assertFalse(service.busy)
                self.assertFalse(failures)
                self.assertEqual(completed[-1]["added_count"], 1)
                self.assertEqual(json.loads(library_path.read_text(encoding="utf-8"))[0]["path"], str(auto_file.resolve()))

                completed.clear()
                self.assertTrue(service.start([str(pending_file.parent)], import_mode="pending"))
                deadline = time.monotonic() + 5
                while not completed and time.monotonic() < deadline:
                    self.app.processEvents()
                    QThread.msleep(2)
                self.assertFalse(service.busy)
                self.assertEqual(completed[-1]["pending_count"], 1)
                self.assertEqual(json.loads(pending_path.read_text(encoding="utf-8"))[0]["path"], str(pending_file.resolve()))
            finally:
                service.shutdown()


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MusicFolderScanSmoke)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("music folder scan service smoke: OK")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
