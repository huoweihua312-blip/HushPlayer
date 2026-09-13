"""B2 system presentation keeps native actions and guarded lifecycle intact."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.widgets.playlist_dialogs import PlaylistNameDialog, PlaylistConfirmDialog
from app.ui_v2.widgets.track_action_dialogs import PlaylistSelectionDialog
from app.ui_v2.widgets.quiet_context_menu import QuietContextMenu, apply_menu_theme
from app.ui_v2.shell.close_behavior_controller import CloseBehaviorController
from app.ui_v2.dialogs.update_dialog import UpdateDialog
from app.services.app_update_service import AppUpdateService, UpdateManifest


class B2SystemSurfacesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app.setProperty('hushUiFlavor', 'ui-v2')
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            widget.hide()
            widget.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def test_name_validation_enter_escape_and_theme_geometry(self):
        sizes = []
        for mode in ('dark', 'light'):
            theme = get_theme(mode)
            self.app.setStyleSheet(build_stylesheet(theme))
            d = self.keep(PlaylistNameDialog(theme, '新建歌单'))
            d.show(); self.app.processEvents()
            sizes.append(d.size())
            QTest.mouseClick(d.confirm_button, Qt.MouseButton.LeftButton)
            self.assertTrue(d.error_label.isVisible())
            self.assertEqual(d.result(), QDialog.DialogCode.Rejected)
            d.name_input.setText('  夜航手记  ')
            QTest.keyClick(d.name_input, Qt.Key.Key_Return)
            self.assertEqual(d.name, '夜航手记')
            self.assertEqual(d.result(), QDialog.DialogCode.Accepted)
            d.show(); QTest.keyClick(d, Qt.Key.Key_Escape)
            self.assertEqual(d.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(*sizes)

    def test_destructive_cancel_and_explicit_confirm(self):
        d = self.keep(PlaylistConfirmDialog(get_theme('dark'), '删除歌单', '歌曲文件会保留。'))
        d.show(); self.app.processEvents()
        QTest.mouseClick(d.cancel_button, Qt.MouseButton.LeftButton)
        self.assertEqual(d.result(), QDialog.DialogCode.Rejected)
        d.show(); QTest.mouseClick(d.confirm_button, Qt.MouseButton.LeftButton)
        self.assertEqual(d.result(), QDialog.DialogCode.Accepted)

    def test_picker_preserves_ids_excludes_favorites_and_disables_empty(self):
        d = self.keep(PlaylistSelectionDialog(get_theme('light'), [SimpleNamespace(id='liked',name='我喜欢'),SimpleNamespace(id='p',name='夜航')]))
        self.assertEqual(d.list_widget.count(), 1)
        self.assertEqual(d.selected_playlist_id, 'p')
        empty = self.keep(PlaylistSelectionDialog(get_theme('dark'), []))
        self.assertFalse(empty.confirm_button.isEnabled())

    def test_native_menu_order_shortcut_checked_disabled_and_keyboard(self):
        menu = self.keep(QuietContextMenu(get_theme('dark')))
        first = menu.addAction('播放'); first.setShortcut('Ctrl+P')
        checked = menu.addAction('显示来源'); checked.setCheckable(True); checked.setChecked(True)
        disabled = menu.addAction('不可用'); disabled.setEnabled(False)
        sub = menu.addMenu('更多'); sub.addAction('歌曲信息')
        danger = menu.addAction('删除歌单')
        original = list(menu.actions())
        apply_menu_theme(menu, get_theme('light'))
        menu.popup(QPoint(10,10)); self.app.processEvents()
        self.assertEqual(menu.actions(), original)
        self.assertFalse(danger.icon().isNull())
        self.assertEqual(first.shortcut().toString(), 'Ctrl+P')
        self.assertFalse(disabled.isEnabled())
        menu.setActiveAction(first); QTest.keyClick(menu, Qt.Key.Key_Down)
        self.assertIs(menu.activeAction(), checked)
        QTest.keyClick(menu, Qt.Key.Key_Return)
        self.assertFalse(checked.isChecked())
        menu.popup(QPoint(10,10)); menu.setActiveAction(sub.menuAction())
        QTest.keyClick(menu, Qt.Key.Key_Right); self.app.processEvents()
        self.assertTrue(sub.isVisible())
        QTest.keyClick(sub, Qt.Key.Key_Escape); menu.hide()

    def test_close_prompt_maps_native_roles_without_persisting_on_cancel(self):
        parent = self.keep(QWidget()); parent.show()
        controller = CloseBehaviorController(self.app, Path(self.temp.name)/'settings.json', tray_available=True)
        for caption, expected in [('取消', None), ('最小化到托盘', ('tray',True)), ('直接退出', ('exit',True))]:
            def choose():
                d = self.app.activeModalWidget()
                d.checkBox().setChecked(True)
                next(b for b in d.buttons() if b.text() == caption).click()
            QTimer.singleShot(30, choose)
            self.assertEqual(controller._ask_for_decision(parent), expected)
        self.assertFalse((Path(self.temp.name)/'settings.json').exists())
        controller.tray_icon.hide()

    def test_update_states_and_layout_preserve_verification_gate(self):
        for mode in ('dark', 'light'):
            self.app.setProperty('hushUiV2ThemeMode', mode)
            service = AppUpdateService(updates_dir=Path(self.temp.name)/'updates')
            manifest = UpdateManifest(1,'stable','0.9.0',(0,9,0,0),'0.9.0.0','x64',False,'https://example.invalid/setup.exe',4096,'0'*64,('日志',),(), 'https://example.invalid/package.zip',4096,'0'*64,'package.zip')
            d = self.keep(UpdateDialog(service, manifest)); d.show(); self.app.processEvents()
            self.assertFalse(d.install_button.isEnabled())
            self.assertTrue(d.download_button.isEnabled())
            d.on_download_started(self.temp.name); d.on_download_progress(2048,4096)
            self.assertEqual(d.progress_bar.value(),50)
            self.assertTrue(d.cancel_button.isEnabled())
            self.assertFalse(d.install_button.isEnabled())
            self.assertEqual(d.progress_bar.height(),3)
            with patch.object(QMessageBox,'warning'):
                d.on_download_failed('网络中断')
            self.assertTrue(d.download_button.isEnabled())
            self.assertFalse(d.install_button.isEnabled())
            # A signal alone must not bypass the verified-file gate.
            d.on_download_verified(manifest,'absent.zip')
            self.assertFalse(d.install_button.isEnabled())
            for button in (d.download_button,d.cancel_button,d.install_button,d.fallback_install_button):
                self.assertTrue(d.rect().contains(button.geometry()))
            d.hide(); service.shutdown()


if __name__ == '__main__':
    unittest.main()
