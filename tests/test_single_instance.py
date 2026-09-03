from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication

from app.core.single_instance import SingleInstanceCoordinator


class SingleInstanceCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.name = f"HushPlayer.Tests.{uuid.uuid4().hex}"
        self.lock_directory = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.lock_directory.name) / "single-instance.lock"
        self.coordinators: list[SingleInstanceCoordinator] = []

    def tearDown(self) -> None:
        for coordinator in reversed(self.coordinators):
            coordinator.close()
        self.app.processEvents()
        self.lock_directory.cleanup()

    def test_second_process_notifies_primary_and_does_not_claim_server(self) -> None:
        primary = SingleInstanceCoordinator(name=self.name, lock_path=self.lock_path)
        self.coordinators.append(primary)
        notifications: list[bool] = []
        primary.activation_requested.connect(lambda: notifications.append(True))

        secondary = SingleInstanceCoordinator(name=self.name, lock_path=self.lock_path)
        self.coordinators.append(secondary)

        self.assertTrue(primary.is_primary)
        self.assertFalse(secondary.is_primary)
        deadline = time.monotonic() + 1.0
        while not notifications and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(notifications, [True])

        secondary.close()
        self.assertTrue(primary.is_primary)

    def test_server_can_be_claimed_after_primary_closes(self) -> None:
        primary = SingleInstanceCoordinator(name=self.name, lock_path=self.lock_path)
        self.coordinators.append(primary)
        self.assertTrue(primary.is_primary)

        primary.close()
        replacement = SingleInstanceCoordinator(
            name=self.name,
            lock_path=self.lock_path,
        )
        self.coordinators.append(replacement)
        self.assertTrue(replacement.is_primary)


if __name__ == "__main__":
    unittest.main()
