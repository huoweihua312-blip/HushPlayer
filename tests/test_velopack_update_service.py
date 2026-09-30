from __future__ import annotations

import unittest

from app.services.velopack_update_service import _progress_values


class VelopackUpdateServiceTests(unittest.TestCase):
    def test_progress_accepts_numeric_callback_arguments(self) -> None:
        self.assertEqual(_progress_values((12, 100)), (12, 100))

    def test_progress_accepts_object_callback_arguments(self) -> None:
        class Progress:
            downloaded_bytes = 24
            total_bytes = 200

        self.assertEqual(_progress_values((Progress(),)), (24, 200))

    def test_unknown_progress_shape_is_safe(self) -> None:
        self.assertEqual(_progress_values((object(),)), (0, 0))
