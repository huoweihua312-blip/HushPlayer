from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.online_recovery_dialog import OnlineRecoveryCandidateDialog


def _candidate(index: int = 0, *, long_text: bool = False) -> OnlineTrack:
    title = "一首非常长的歌曲标题，用于验证弹窗不会裁切内容" if long_text else f"夜航 {index}"
    return OnlineTrack(
        id=f"remote:{index}",
        source_id="catalog",
        source_name="开放目录",
        title=title,
        artist="North Window",
        album="Night Signals",
        duration_ms=186_000,
        artwork_key=f"art:{index}",
        quality="标准",
        stable_identity=f"remote:{index}",
        is_favorite=False,
        is_downloaded=False,
        is_cached=False,
        availability="not_resolved",
        explicit=False,
        result_rank=index,
    )


class OnlineRecoveryCandidateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, mode: str = "dark", count: int = 4) -> OnlineRecoveryCandidateDialog:
        dialog = OnlineRecoveryCandidateDialog(
            tuple(_candidate(index, long_text=index == 1) for index in range(count)),
            get_theme(mode),
        )
        dialog.show()
        self.app.processEvents()
        return dialog

    def test_light_and_dark_dialogs_keep_actions_and_rows_readable(self) -> None:
        for mode in ("light", "dark"):
            dialog = self._dialog(mode)
            try:
                self.assertGreaterEqual(dialog.minimumWidth(), 640)
                self.assertEqual(dialog.list_widget.count(), 4)
                self.assertTrue(dialog.list_widget.isEnabled())
                primary = next(
                    button
                    for button in dialog.findChildren(QPushButton)
                    if button.text() == "替换播放来源并播放"
                )
                self.assertTrue(primary.isEnabled())
                self.assertEqual(primary.property("role"), "primary")
                self.assertIn("QDialog QListWidget", dialog.styleSheet())
                self.assertIn(
                    "QDialog QListWidget#onlineRecoveryCandidateList::item:hover",
                    dialog.styleSheet(),
                )
                self.assertIn(get_theme(mode).colors.primary_text, dialog.styleSheet())
                self.assertIn("一首非常长的歌曲标题", dialog.list_widget.item(1).toolTip())
                self.assertGreaterEqual(dialog.list_widget.item(0).sizeHint().height(), 56)
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()

    def test_empty_candidate_list_disables_selection_and_primary_action(self) -> None:
        dialog = OnlineRecoveryCandidateDialog((), get_theme("dark"))
        try:
            primary = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == "替换播放来源并播放"
            )
            self.assertFalse(dialog.list_widget.isEnabled())
            self.assertFalse(primary.isEnabled())
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_accepting_selected_candidate_preserves_full_track_object(self) -> None:
        dialog = self._dialog("dark", 3)
        try:
            dialog.list_widget.setCurrentRow(2)
            dialog._accept_selected()
            self.assertIs(dialog.selected_track, dialog._candidates[2])
            self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
