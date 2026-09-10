"""B2 Shell visual boundaries and the existing navigation/input contracts."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QToolButton, QWidget
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.custom_title_bar import CustomTitleBar
from app.ui_v2.widgets.playlist_dialogs import PlaylistNameDialog, PlaylistConfirmDialog


class B2ShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory(prefix='hush-b2-shell-')
        cls.window = MainWindow(data_mode='mock', settings_path=cls.tmp.name+'/settings.json')
        cls.window.playback_adapter._timer_enabled = False

    @classmethod
    def tearDownClass(cls):
        cls.window.hide()
        cls.window.deleteLater()
        cls.app.processEvents()
        cls.tmp.cleanup()

    def test_theme_boundary_compact_and_focus_geometry(self):
        w = self.window
        for width, rail in ((1450, 220), (1080, 76)):
            for mode in ('dark', 'light'):
                w.navigation_adapter.set_route("library")
                w.resize(width, 900); w.set_theme(mode); w.show(); w.activateWindow()
                self.app.processEvents()
                self.assertEqual(w.sidebar.width(), rail)
                self.assertEqual(w.title_bar.height(), 59)
                self.assertIs(w.theme, get_theme(mode))
                self.assertIs(w.library_page.theme, get_theme(mode))
                self.assertEqual(w.sidebar.palette().color(QPalette.ColorRole.Window),
                                 QColor(get_theme(mode, profile='b2').colors.sidebar_background))
                self.assertEqual(w.title_bar.search_box.height(), 36)
                self.assertLessEqual(w.title_bar.search_input.height(), 36)
                for button in (w.title_bar.back_button, w.title_bar.forward_button,
                               w.title_bar.settings_button, w.title_bar.theme_button,
                               w.title_bar.minimize_button, w.title_bar.maximize_button,
                               w.title_bar.close_button):
                    self.assertEqual((button.width(), button.height()), (32, 32))
                self.assertEqual((w.sidebar.playlist_add_button.width(), w.sidebar.playlist_add_button.height()), (26, 26))
                controls = [w.sidebar._items['library'], w.sidebar.more_navigation_button,
                            w.sidebar.playlist_add_button, w.title_bar.settings_button,
                            w.title_bar.theme_button, w.title_bar.minimize_button,
                            w.title_bar.maximize_button, w.title_bar.close_button,
                            w.title_bar.search_input]
                for control in controls:
                    before = control.geometry()
                    control.clearFocus()
                    self.app.processEvents()
                    w._keyboard_focus_navigation = True
                    control.setFocus(Qt.FocusReason.TabFocusReason)
                    self.app.processEvents()
                    QTest.qWait(30)
                    self.assertTrue(control.hasFocus())
                    self.assertEqual(control.geometry(), before)
                    image = control.grab().toImage()
                    accent = QColor(get_theme(mode, profile='b2').colors.focus_ring)
                    # Focus is visibly painted near the edge, not merely present in QSS.
                    self.assertTrue(any(image.pixelColor(x, y) == accent
                                        for y in range(image.height())
                                        for x in (1, 2, image.width()-2)), (mode, width, control.objectName(), control.toolTip()))
                    control.clearFocus()

    def test_more_menu_mapping_and_actions(self):
        w = self.window
        def choose(menu, *_args):
            actions = menu.actions()
            self.assertEqual([a.text() for a in actions], ['最近播放', '歌手', '专辑', '歌词'])
            for action, route in zip(actions, ['recent', 'artists', 'albums', 'lyrics']):
                action.trigger(); self.app.processEvents()
                self.assertEqual(w.navigation_adapter.route, route)
            return None
        class ChoosingMenu(QMenu):
            def exec(self, *args):
                return choose(self, *args)
        with patch('app.ui_v2.shell.navigation_sidebar.QMenu', ChoosingMenu):
            w.sidebar._show_more_navigation_menu()

    def test_playlist_create_context_rename_and_delete_use_mock_only(self):
        sidebar = self.window.sidebar
        def accept_name(dialog):
            dialog.name_input.setText('中文长歌单 ' * 12)
            return QDialog.DialogCode.Accepted
        with patch.object(PlaylistNameDialog, 'exec', accept_name):
            playlist_id = sidebar._open_create_playlist_dialog()
        self.assertTrue(playlist_id)
        item = sidebar._playlist_items[playlist_id]
        self.assertIn('中文长歌单', item.toolTip())
        item.click(); self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, 'playlist:'+playlist_id)
        def rename_name(dialog):
            dialog.name_input.setText('已重命名')
            return QDialog.DialogCode.Accepted
        def menu_choice(menu, *_args):
            self.assertEqual([a.text() for a in menu.actions()], ['重命名歌单', '删除歌单'])
            return menu.actions()[0]
        class RenameMenu(QMenu):
            def exec(self, *args):
                return menu_choice(self, *args)
        with patch('app.ui_v2.shell.navigation_sidebar.QMenu', RenameMenu), patch.object(PlaylistNameDialog, 'exec', rename_name):
            sidebar._show_playlist_menu(playlist_id, QPoint())
        self.assertEqual(sidebar._playlist_items[playlist_id].toolTip(), '已重命名')
        class DeleteMenu(QMenu):
            def exec(self, *args):
                return self.actions()[1]
        with patch('app.ui_v2.shell.navigation_sidebar.QMenu', DeleteMenu), patch.object(PlaylistConfirmDialog, 'exec', return_value=QDialog.DialogCode.Accepted):
            sidebar._show_playlist_menu(playlist_id, QPoint())
        self.assertNotIn(playlist_id, sidebar._playlist_items)

    def test_long_playlist_list_scrolls_without_horizontal_overflow(self):
        w = self.window
        created = []
        try:
            for i in range(18):
                created.append(w.sidebar.create_mock_playlist(f"滚动检查 {i} · 中文长名称"))
            w.resize(1080, 900); w.show(); self.app.processEvents()
            scroll = w.sidebar.scroll_area
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            self.app.processEvents()
            item = w.sidebar._playlist_items[created[-1]]
            self.assertEqual(item.toolTip(), "滚动检查 17 · 中文长名称")
            item.click()
            self.assertEqual(w.navigation_adapter.route, "playlist:"+created[-1])
        finally:
            for playlist_id in created:
                w.sidebar.delete_mock_playlist(playlist_id)

    def test_titlebar_window_actions_and_drag(self):
        host = QWidget(); host.resize(1000, 600)
        bar = CustomTitleBar(get_theme('dark'), host); bar.resize(1000, 59)
        host.show(); self.app.processEvents()
        original = host.pos()
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(400, 5))
        QTest.mouseMove(bar, QPoint(420, 15))
        QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(420, 15))
        self.assertNotEqual(host.pos(), original)
        QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(400, 5))
        self.assertTrue(host.isMaximized())
        bar.maximize_button.click(); self.assertFalse(host.isMaximized())
        bar.minimize_button.click(); self.assertTrue(host.isMinimized())
        host.showNormal()
        closed = []; host.request_user_close = lambda: closed.append(True)
        bar.close_button.click(); self.assertEqual(closed, [True])
        host.close(); host.deleteLater()

    def test_search_visual_keeps_context_submit_clear_and_debounce(self):
        host = QWidget(); host.resize(1450, 900)
        bar = CustomTitleBar(get_theme('light'), host); bar.resize(1450, 59)
        host.show(); self.app.processEvents()
        submitted = []; ready = []
        bar.search_submitted.connect(submitted.append)
        bar.search_text_changed.connect(ready.append)
        for route, placeholder in [('library', '在音乐库中搜索'), ('playlist:id', '在当前歌单中搜索'),
                                   ('artists', '搜索歌手'), ('albums', '搜索专辑'),
                                   ('online_search', '搜索在线歌曲')]:
            bar.set_search_context(route)
            self.assertEqual(bar.search_input.placeholderText(), placeholder)
        bar.search_input.setText('中文长搜索词' * 20)
        QTest.keyClick(bar.search_input, Qt.Key.Key_Return)
        self.assertEqual(submitted[-1], '中文长搜索词' * 20)
        QTest.qWait(220)
        self.assertEqual(ready[-1], submitted[-1])
        clear = next(b for b in bar.search_input.findChildren(QToolButton) if b.isVisible())
        clear.click(); QTest.qWait(220)
        self.assertEqual(bar.search_input.text(), '')
        self.assertEqual(ready[-1], '')
        host.close(); host.deleteLater()


if __name__ == '__main__':
    unittest.main()
