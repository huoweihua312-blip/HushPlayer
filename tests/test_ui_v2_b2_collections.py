"""Run the established list interaction contract against the B2 opt-in page."""
import unittest
import test_ui_v2_library_page as legacy
from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.all_songs_page import AllSongsPage
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.track_delegate import RowVisualState, TrackDelegate


class B2CollectionTests(unittest.TestCase):
    setUpClass = classmethod(legacy.UiV2LibraryPageTests.setUpClass.__func__)
    tearDown = legacy.UiV2LibraryPageTests.tearDown
    _available_index = legacy.UiV2LibraryPageTests._available_index
    test_double_click_requests_play_and_right_click_menu_constructs = legacy.UiV2LibraryPageTests.test_double_click_requests_play_and_right_click_menu_constructs
    test_single_click_browses_after_delay_but_double_click_only_plays = legacy.UiV2LibraryPageTests.test_single_click_browses_after_delay_but_double_click_only_plays
    test_missing_favorite_can_be_removed_but_not_added = legacy.UiV2LibraryPageTests.test_missing_favorite_can_be_removed_but_not_added
    test_missing_track_exposes_online_recovery_action = legacy.UiV2LibraryPageTests.test_missing_track_exposes_online_recovery_action
    test_unplayable_online_track_exposes_online_recovery_action = legacy.UiV2LibraryPageTests.test_unplayable_online_track_exposes_online_recovery_action
    test_empty_loading_error_and_content_states = legacy.UiV2LibraryPageTests.test_empty_loading_error_and_content_states

    def setUp(self):
        self.adapter = LibraryAdapter(create_mock_tracks(80))
        self.page = AllSongsPage(self.adapter, get_theme('dark'))
        self.page.resize(1080, 700)
        self.page.show()
        self.app.processEvents()

    def test_theme_reapplication_preserves_model_and_header_layout(self):
        table = self.page.track_table
        model = table.model
        count = self.page.header.identity.layout().count()
        for mode in ('light', 'dark', 'light', 'dark'):
            self.page.set_theme(get_theme(mode))
            self.assertIs(table.model, model)
            self.assertEqual(self.page.header.identity.layout().count(), count)
            self.assertTrue(table.delegate._b2)
            self.assertTrue(table.header._b2)
            self.assertEqual(table.delegate._theme, get_theme(mode, profile='b2'))

    def test_current_and_selection_have_distinct_opaque_backgrounds(self):
        for mode in ('dark', 'light'):
            self.page.set_theme(get_theme(mode))
            delegate = self.page.track_table.delegate
            playing = delegate.background_color(RowVisualState.PLAYING)
            selected = delegate.background_color(RowVisualState.SELECTED)
            self.assertNotEqual(playing, selected)
            self.assertEqual(playing.alpha(), 255)
            self.assertEqual(delegate.background_color(RowVisualState.SELECTED_PLAYING), selected)

    def test_legacy_delegate_does_not_opt_in_implicitly(self):
        self.assertFalse(TrackDelegate(get_theme('dark'))._b2)
