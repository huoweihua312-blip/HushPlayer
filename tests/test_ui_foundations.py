import os
import unittest
from dataclasses import replace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from app.ui_v2.theme.tokens import LIGHT_THEME, DARK_THEME
from app.ui_v2.theme.responsive import LayoutWidths
from app.ui_v2.widgets.responsive_columns import ResponsiveColumnPolicy
from app.ui_v2.widgets.content_surface import ContentSurface


class FoundationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tokens_preserve_custom_theme_values(self):
        for theme in (LIGHT_THEME, DARK_THEME):
            colors = replace(theme.colors, danger='#123456')
            self.assertEqual(colors.error, '#123456')
            self.assertEqual(colors.background, theme.colors.app_background)
            self.assertEqual(colors.surface_playing, theme.colors.playing_background)
            self.assertEqual(theme.metrics.radius_control, 8)
            self.assertEqual(theme.fonts.label, 15)

    def test_existing_table_boundaries_and_width_sources(self):
        for width, expected in ((949,'narrow'),(950,'standard'),(1219,'standard'),(1220,'wide')):
            self.assertEqual(ResponsiveColumnPolicy.profile_for_width(width).name, expected)
        widths = LayoutWidths(1450, 1230, 1160)
        self.assertEqual((widths.window_width, widths.content_width, widths.viewport_width), (1450,1230,1160))

    def test_surface_preserves_existing_insets(self):
        surface = ContentSurface()
        from PySide6.QtCore import Qt
        self.assertTrue(surface.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        surface.set_insets(8, 120)
        margins = surface.stack.contentsMargins()
        self.assertEqual((margins.left(),margins.top(),margins.right(),margins.bottom()), (8,8,8,128))
        surface.deleteLater()

    def test_search_contract_matches_legacy(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from app.ui_v2.widgets.search_box import SearchBox
        from app.ui_v2.widgets.search_field import SearchField
        outputs = []
        for cls in (SearchBox, SearchField):
            widget = cls()
            events = []
            widget.text_changed.connect(events.append)
            widget.set_text('测试歌曲')
            QTest.keyClick(widget.line_edit, Qt.Key.Key_Return)
            widget.set_text('')
            QTest.qWait(220)
            outputs.append(events)
            widget.deleteLater()
        self.assertEqual(outputs[0], ['测试歌曲', ''])
        self.assertEqual(outputs[0], outputs[1])

    def test_action_bar_preserves_styles_and_single_emission(self):
        from app.ui_v2.widgets.collection_action_row import CollectionActionRow
        from app.ui_v2.widgets.collection_action_bar import CollectionActionBar
        for theme in (LIGHT_THEME, DARK_THEME):
            old, new = CollectionActionRow(theme), CollectionActionBar(theme)
            for name in ('play_button', 'shuffle_button'):
                self.assertEqual(getattr(old,name).styleSheet(), getattr(new,name).styleSheet())
            events = []
            new.play_requested.connect(lambda: events.append('play'))
            new.shuffle_requested.connect(lambda: events.append('shuffle'))
            new.play_button.click()
            new.shuffle_button.click()
            self.assertEqual(events, ['play','shuffle'])
            old.deleteLater()
            new.deleteLater()

    def test_identity_keeps_caller_labels_and_layout(self):
        from PySide6.QtWidgets import QLabel
        from app.ui_v2.widgets.track_identity import TrackIdentity
        title, metadata = QLabel('长歌名' * 30), QLabel('歌手')
        block = TrackIdentity(title, metadata)
        self.assertIs(block.layout().itemAt(0).widget(), title)
        self.assertIs(block.layout().itemAt(1).widget(), metadata)
        self.assertEqual(block.layout().spacing(), 3)
        self.assertEqual(title.text(), '长歌名' * 30)
        block.deleteLater()


if __name__ == '__main__':
    unittest.main()
