"""B2 collection/discovery presentation and preserved navigation contracts."""
import os
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.models.track_table_model import TrackColumn


class B2DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.window = MainWindow(data_mode='mock', settings_path=self.tmp.name+'/settings.json')
        self.window.resize(1450, 900)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_related_rail_uses_window_width_on_route_creation_and_resize(self):
        w = self.window
        route = 'playlist:' + w.navigation_adapter.playlists()[0].id
        w.navigation_adapter.set_route(route)
        page = w.router.currentWidget()
        for width, visible in ((1450, True), (1510, True), (1600, True), (1449, False), (1080, False), (1450, True)):
            w.resize(width, 900)
            self.app.processEvents()
            for reference in (900, page.width(), 1800):
                page.set_responsive_reference_width(reference)
                self.assertEqual(not page.related_playlists.isHidden(), visible)
            self.app.processEvents()
            table = page.track_table
            more = int(TrackColumn.MORE)
            self.assertFalse(table.isColumnHidden(more))
            self.assertLessEqual(table.columnViewportPosition(more) + table.columnWidth(more), table.viewport().width())
        requested = []
        page.playlist_requested.connect(requested.append)
        row = next(r for r in page.related_playlists._rows if r.playlist_id != page.playlist_id)
        QTest.mouseClick(row, Qt.MouseButton.LeftButton)
        self.assertEqual(requested, [row.playlist_id])

    def test_grid_list_reuses_cards_and_keeps_navigation(self):
        for route in ('artists', 'albums'):
            self.window.navigation_adapter.set_route(route)
            page = self.window.router.currentWidget()
            self.app.processEvents()
            cards = dict(page._cards)
            requested = []
            page.entity_requested.connect(requested.append)
            for mode, extent in (('list', 64), ('grid', 176), ('list', 64)):
                page.view_toggle.set_mode(mode)
                self.app.processEvents()
                self.assertEqual(cards, page._cards)
                self.assertTrue(all(c.cover_label.width() == extent for c in cards.values()))
            key, card = next(iter(cards.items()))
            QTest.mouseClick(card, Qt.MouseButton.LeftButton)
            self.assertEqual(requested[-1], key)

    def test_search_empty_and_restore_keep_aggregate_data(self):
        for route in ('artists', 'albums'):
            self.window.navigation_adapter.set_route(route)
            page = self.window.router.currentWidget()
            count = len(page._entities)
            page.search_box.set_text('NoMatchingEntityForThisTest')
            QTest.qWait(350)
            self.assertFalse(page._entities)
            self.assertFalse(page.empty_state.isHidden())
            page.search_box.set_text('')
            QTest.qWait(350)
            self.assertEqual(len(page._entities), count)

    def test_detail_tables_reuse_p2_visuals_without_replacing_models(self):
        w = self.window
        routes = ['playlist:'+w.navigation_adapter.playlists()[0].id,
                  'album_detail:'+w.router._albums_adapter.albums()[0].id,
                  'artist_detail:'+w.router._artists_adapter.artists()[0].id]
        for route in routes:
            w.navigation_adapter.set_route(route)
            page = w.router.currentWidget()
            model = page.track_table.model
            for mode in ('light', 'dark'):
                page.set_theme(get_theme(mode))
                self.assertIs(page.track_table.model, model)
                self.assertTrue(page.track_table.delegate._b2)
                self.assertIs(page.track_table.delegate._theme, get_theme(mode, profile='b2'))
