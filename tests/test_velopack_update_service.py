from __future__ import annotations

import unittest
import threading
import time
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from app.services.velopack_update_service import _progress_values, _VelopackWorker, VelopackUpdateService


class VelopackUpdateServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def test_failed_helper_launch_does_not_request_app_exit(self) -> None:
        class Manager:
            def wait_exit_then_apply_updates(self, *args, **kwargs):
                raise OSError("helper launch failed")

        worker = _VelopackWorker("test")
        worker.manager = Manager()
        exits = []
        errors = []
        worker.applying.connect(lambda: exits.append(True))
        worker.failed.connect(errors.append)
        worker.apply(object())
        self.assertEqual(exits, [])
        self.assertEqual(errors, ["helper launch failed"])

    def test_successful_apply_schedules_helper_before_exit_signal(self) -> None:
        events = []

        class Manager:
            def wait_exit_then_apply_updates(self, update, **kwargs):
                events.append(("helper", kwargs))

        worker = _VelopackWorker("test")
        worker.manager = Manager()
        worker.applying.connect(lambda: events.append("exit"))
        worker.apply(object())
        self.assertEqual(events, [("helper", {"silent": True, "restart": True}), "exit"])

    def test_close_during_check_defers_until_worker_finishes_and_suppresses_result(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        service = None

        class Manager:
            def check_for_updates(self):
                entered.set()
                release.wait(5)
                return object()

        try:
            with patch("app.services.velopack_update_service.create_update_manager", return_value=Manager()):
                service = VelopackUpdateService("test")
                results = []
                service.updateAvailable.connect(results.append)
                service.check_for_updates()
                self.assertTrue(entered.wait(1))
                start = time.monotonic()
                self.assertFalse(service.shutdown())
                self.assertLess(time.monotonic() - start, 0.5)
                self.assertFalse(service.check_for_updates())
                release.set()
                self.assertTrue(service._thread.wait(1_000))
                self.application.processEvents()
                self.assertEqual(results, [])
                self.assertTrue(service.shutdown())
        finally:
            release.set()
            if service is not None:
                service._thread.quit()
                service._thread.wait(2_000)

    def test_progress_accepts_numeric_callback_arguments(self) -> None:
        self.assertEqual(_progress_values((12, 100)), (12, 100))

    def test_progress_accepts_object_callback_arguments(self) -> None:
        class Progress:
            downloaded_bytes = 24
            total_bytes = 200

        self.assertEqual(_progress_values((Progress(),)), (24, 200))

    def test_unknown_progress_shape_is_safe(self) -> None:
        self.assertEqual(_progress_values((object(),)), (0, 0))
