from __future__ import annotations

import os
import inspect
import json
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("HUSHPLAYER_UI_V2_DATA_MODE", "mock")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout

from app.ui_v2.models.playback_state import RepeatMode
from app.ui_v2.theme.icons import (
    FLUENT_PLAYER_ASSETS,
    _FLUENT_PLAYER_PIXMAP_CACHE,
    _SVG_PIXMAP_CACHE,
    _svg_pixmap,
    clear_svg_icon_cache,
    icon,
    optical_scale_for,
    palette_for,
)
from app.ui_v2.theme.tokens import get_theme
import app.ui_v2.widgets.navigation_item as navigation_item_module
from app.ui_v2.widgets.cover_card import CoverCard, CoverCardPlayButton
from app.ui_v2.widgets.placeholder_cover import placeholder_cover_index
from app.ui_v2.widgets.playback_button import PlayerIconButton
from app.ui_v2.shell.main_window import MainWindow


class ApprovedShellMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_approved_title_bar_and_sidebar_structure(self) -> None:
        title_bar = self.window.title_bar
        self.assertEqual(title_bar.height(), 59)
        self.assertEqual(self.window.windowTitle(), "HushPlayer UI V2")
        self.assertTrue(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(title_bar.search_input.placeholderText(), "搜索")
        self.assertEqual(
            {button.toolTip() for button in (
                title_bar.back_button, title_bar.forward_button, title_bar.settings_button,
                title_bar.theme_button, title_bar.view_options_button, title_bar.minimize_button,
                title_bar.maximize_button, title_bar.close_button,
            )},
            {"返回", "前进", "设置", "切换到浅色模式", "视图选项（暂不可用）", "最小化", "最大化", "关闭"},
        )
        self.assertEqual(title_bar.back_button.iconSize(), QSize(16, 16))
        self.assertEqual(title_bar.forward_button.iconSize(), QSize(16, 16))
        self.assertEqual(title_bar.search_icon.iconSize(), QSize(16, 16))
        for button in (
            title_bar.back_button,
            title_bar.forward_button,
            title_bar.settings_button,
            title_bar.theme_button,
            title_bar.minimize_button,
            title_bar.maximize_button,
            title_bar.close_button,
        ):
            self.assertEqual(button.size(), QSize(32, 32))
        for button in (
            title_bar.settings_button,
            title_bar.theme_button,
            title_bar.view_options_button,
        ):
            self.assertEqual(button.iconSize(), QSize(18, 18))
        self.assertIn("border-radius: 8px", title_bar.styleSheet())
        self.assertFalse(title_bar.notifications_button.isVisible())
        self.assertFalse(title_bar.avatar_button.isVisible())
        self.assertTrue(title_bar.brand.isVisible())
        self.assertEqual(title_bar.brand_label.text(), "HushPlayer")
        sidebar = self.window.sidebar
        self.assertEqual(sidebar.width(), 220)
        self.assertEqual(sidebar.brand_label.text(), "HushPlayer")
        self.assertEqual(
            set(sidebar._items),
            {"library", "browse", "online_search", "liked", "settings"},
        )
        self.assertFalse(sidebar.settings_box.isVisible())

    def test_browse_sections_cover_cards_and_stable_cover_mapping(self) -> None:
        page = self.window.router.browse_page
        self.assertIs(self.window.router.currentWidget(), page)
        self.assertEqual(set(page.sections), {"recent_added", "recommended", "recent_played"})
        self.assertEqual(page.target_card_count, 5)
        for section in page.sections.values():
            visible_cards = [card for card in section.cards if not card.isHidden()]
            self.assertEqual(len(visible_cards), 5)
            self.assertTrue(all(isinstance(card, CoverCard) for card in visible_cards))
            self.assertTrue(all(isinstance(card.play_button, CoverCardPlayButton) for card in visible_cards))
            for card in visible_cards:
                self.assertEqual(
                    placeholder_cover_index(card.track.stable_id),
                    placeholder_cover_index(card.track.stable_id),
                )
                for visible_label in (
                    card.title_label.full_text,
                    card.meta_label.full_text,
                    card.toolTip(),
                ):
                    self.assertFalse(
                        any(marker in visible_label.casefold() for marker in ("mock", "demo", "preview", "fixture")),
                        visible_label,
                    )

    def test_track_selection_uses_surface_and_accent_rail_without_cell_frame(self) -> None:
        source = inspect.getsource(self.window.library_page.track_table.delegate.__class__)
        self.assertIn("RenderHint(QPainter.RenderHint.Antialiasing, True)", source)
        self.assertIn("colors.focus_ring", source)
        self.assertNotIn("State_HasFocus", source)
        self.assertNotIn("drawRoundedRect(rect.adjusted(2, 2, -2, -2)", source)

    def test_sidebar_uses_qt_elision_and_keeps_playlist_tooltip(self) -> None:
        sidebar = self.window.sidebar
        self.window.resize(1200, 800)
        self.app.processEvents()
        full_name = "用于验证侧栏真实省略号的超长自定义歌单名称与夜间收听记录"
        self.assertTrue(sidebar.adapter.rename_playlist("playlist-seed-2", full_name))
        self.app.processEvents()
        item = sidebar._playlist_items["playlist-seed-2"]
        self.assertEqual(item.toolTip(), full_name)
        self.assertEqual(item._full_title, full_name)
        self.assertIn("…", item.text())
        for width, compact in ((900, True), (1200, False)):
            self.window.resize(width, 600 if compact else 800)
            self.app.processEvents()
            self.assertEqual(item.toolTip(), full_name)
            if compact:
                self.assertEqual(item.text(), "")
            else:
                self.assertIn("…", item.text())

    def test_sidebar_uses_formal_icons_and_approved_row_geometry(self) -> None:
        sidebar = self.window.sidebar
        self.window.resize(1200, 800)
        self.app.processEvents()

        self.assertEqual(sidebar.width(), 220)
        self.assertEqual(sidebar.brand.layout().contentsMargins().left(), 28)
        self.assertEqual(sidebar.brand.height(), 84)
        self.assertEqual(sidebar.library_box.layout().contentsMargins().left(), 18)
        self.assertEqual(sidebar.library_box.layout().contentsMargins().top(), 20)
        self.assertEqual(sidebar.library_box.layout().contentsMargins().right(), 14)
        self.assertFalse(sidebar.settings_box.isVisible())
        self.assertFalse(sidebar._items["settings"].isVisible())
        self.assertTrue(sidebar.playlist_section.layout().itemAt(1).widget() is sidebar.scroll_area)
        self.assertEqual(
            {
                "library": sidebar._items["library"].item.icon_name,
                "browse": sidebar._items["browse"].item.icon_name,
                "online_search": sidebar._items["online_search"].item.icon_name,
                "liked": sidebar._items["liked"].item.icon_name,
                "settings": sidebar._items["settings"].item.icon_name,
                "more": sidebar.more_playlists_button.item.icon_name,
            },
            {
                "library": "library",
                "browse": "browse",
                "online_search": "search",
                "liked": "favorite",
                "settings": "settings",
                "more": "playlist_more",
            },
        )
        expected_icon_sizes = {
            "library": QSize(18, 18),
            "browse": QSize(18, 18),
            "online_search": QSize(17, 17),
            "liked": QSize(18, 18),
            "settings": QSize(18, 18),
        }
        for route_id, item in sidebar._items.items():
            self.assertEqual(item.height(), 42)
            self.assertEqual(item.iconSize(), expected_icon_sizes[route_id])
            self.assertFalse(item.icon().isNull())
        self.assertEqual(sidebar.more_playlists_button.iconSize(), QSize(17, 17))
        for item in sidebar._playlist_items.values():
            self.assertEqual(item.height(), 42)
            self.assertEqual(item.iconSize(), QSize(18, 18))
            self.assertFalse(item.icon().isNull())

        selected = sidebar._items["browse"]
        unselected_contents = selected.contentsRect()
        selected.set_selected(True)
        self.assertEqual(selected.contentsRect(), unselected_contents)
        self.assertNotIn("border-left", selected.styleSheet())
        self.assertIn("border: 0", selected.styleSheet())
        source = inspect.getsource(navigation_item_module.NavigationItem)
        self.assertNotIn("def paintEvent", source)
        self.assertNotIn("QPainter", source)

    def test_sidebar_uses_deterministic_local_playlist_cover_icons(self) -> None:
        sidebar = self.window.sidebar
        self.window.resize(1200, 800)
        self.app.processEvents()

        first = sidebar._playlist_cover_icon("playlist-seed-2", "晚间收藏")
        second = sidebar._playlist_cover_icon("playlist-seed-2", "晚间收藏")
        first_image = first.pixmap(QSize(18, 18)).toImage()
        second_image = second.pixmap(QSize(18, 18)).toImage()
        self.assertFalse(first_image.isNull())
        self.assertEqual(first_image, second_image)
        self.assertTrue(all(item._custom_icon is not None for item in sidebar._playlist_items.values()))
        self.assertTrue(all(item.item.icon_name == "playlist" for item in sidebar._playlist_items.values()))
        self.assertEqual(sidebar._items["liked"].item.icon_name, "favorite")

    def test_approved_svg_icon_sources_and_cache_contract(self) -> None:
        icon_dir = PROJECT_ROOT / "app" / "ui_v2" / "assets" / "icons"
        svg_paths = sorted(icon_dir.glob("*.svg"))
        self.assertEqual(len(svg_paths), 25)
        for path in svg_paths:
            source = path.read_text(encoding="utf-8")
            self.assertTrue(source.isascii(), path.name)
            self.assertIn('viewBox="0 0 24 24"', source, path.name)
            self.assertIn('stroke-linecap="round"', source, path.name)
            self.assertIn('stroke-linejoin="round"', source, path.name)
            widened_player_icons = {
                "favorite", "lyrics", "next", "pause", "previous", "queue",
                "repeat-all", "repeat-one", "shuffle", "volume",
            }
            expected_width = "1.9" if path.stem == "brand" or path.stem in widened_player_icons else "1.7"
            self.assertIn(f'stroke-width="{expected_width}"', source, path.name)
            self.assertNotIn("<text", source, path.name)
        repeat_one = (icon_dir / "repeat-one.svg").read_text(encoding="utf-8")
        self.assertIn('M10.1 8.8', repeat_one)
        self.assertIn('fill="currentColor" stroke="none"', repeat_one)

        clear_svg_icon_cache()
        color = QColor(get_theme("dark").colors.accent)
        first = _svg_pixmap("repeat_one", 16, color, 1.0)
        second = _svg_pixmap("repeat_one", 16, color, 1.0)
        self.assertFalse(first.isNull())
        self.assertEqual(first.cacheKey(), second.cacheKey())
        self.assertIn(
            ("repeat_one", 16, color.rgba(), 1.0, optical_scale_for("repeat_one")),
            _SVG_PIXMAP_CACHE,
        )

    def test_optical_scaling_keeps_canvas_safe_and_cache_keys_complete(self) -> None:
        color = QColor(get_theme("dark").colors.icon_default)
        clear_svg_icon_cache()
        scaled = _svg_pixmap("library", 18, color, 1.0)
        unscaled = _svg_pixmap("library", 18, color, 1.0, optical_scale=1.0)
        self.assertEqual(scaled.size(), QSize(18, 18))
        self.assertEqual(unscaled.size(), QSize(18, 18))
        self.assertNotEqual(scaled.cacheKey(), unscaled.cacheKey())
        self.assertIn(
            ("library", 18, color.rgba(), 1.0, optical_scale_for("library")),
            _SVG_PIXMAP_CACHE,
        )
        self.assertIn(("library", 18, color.rgba(), 1.0, 1.0), _SVG_PIXMAP_CACHE)
        for name in ("library", "browse", "repeat", "repeat_one", "queue", "lyrics", "volume"):
            image = _svg_pixmap(name, 20, color, 1.0).toImage()
            alpha_points = [
                (x, y)
                for y in range(image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 0
            ]
            self.assertTrue(alpha_points, name)
            self.assertGreater(min(x for x, _y in alpha_points), 0, name)
            self.assertLess(max(x for x, _y in alpha_points), image.width() - 1, name)
            self.assertGreater(min(y for _x, y in alpha_points), 0, name)
            self.assertLess(max(y for _x, y in alpha_points), image.height() - 1, name)

    def test_icon_canvas_sizes_raise_visibility_without_changing_controls(self) -> None:
        sidebar = self.window.sidebar
        bar = self.window.player_bar
        self.window.playback_adapter.play()
        self.app.processEvents()
        self.assertTrue(all(
            17 <= item.iconSize().width() <= 20
            for item in (*sidebar._items.values(), sidebar.more_playlists_button)
        ))
        self.assertTrue(all(
            16 <= button.iconSize().width() <= 18
            for button in (
                bar.favorite_button, bar.shuffle_button, bar.repeat_button,
                bar.queue_button, bar.lyrics_button, bar.volume_button, bar.more_button,
            )
        ))
        self.assertEqual(bar.previous_button.iconSize(), QSize(20, 20))
        self.assertEqual(bar.next_button.iconSize(), QSize(20, 20))
        self.assertEqual(bar.play_button.iconSize(), QSize(22, 22))
        self.assertEqual(bar.favorite_button.size(), QSize(32, 32))
        self.assertEqual(bar.shuffle_button.size(), QSize(32, 32))
        self.assertEqual(bar.previous_button.size(), QSize(34, 34))
        self.assertEqual(bar.play_button.size(), QSize(52, 52))
        self.assertEqual(bar.next_button.size(), QSize(34, 34))
        self.assertEqual(bar.repeat_button.size(), QSize(32, 32))
        self.assertEqual(bar.queue_button.size(), QSize(32, 32))
        self.assertEqual(bar.more_button.size(), QSize(32, 32))
        palette = palette_for(get_theme("dark"))
        self.assertGreater(palette.normal.lightness(), QColor(get_theme("dark").colors.text_secondary).lightness())
        self.assertLess(palette.normal.lightness(), palette.hover.lightness())

    def test_compact_shell_uses_the_approved_icon_rail_without_hiding_player_actions(self) -> None:
        self.window.resize(900, 600)
        self.app.processEvents()

        sidebar = self.window.sidebar
        title_bar = self.window.title_bar
        bar = self.window.player_bar
        self.assertTrue(sidebar.compact)
        self.assertEqual(sidebar.width(), 76)
        self.assertFalse(sidebar.brand_label.isVisible())
        self.assertFalse(title_bar.brand_label.isVisible())
        self.assertFalse(sidebar.library_caption.isVisible())
        self.assertFalse(sidebar.playlist_caption.isVisible())
        self.assertEqual(title_bar._sidebar_spacer.width(), 76)
        for item in (*sidebar._items.values(), *sidebar._playlist_items.values(), sidebar.more_playlists_button):
            self.assertEqual(item.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.assertFalse(sidebar.scroll_area.horizontalScrollBar().isVisible())
        self.assertTrue(all(button.isVisible() for button in (
            bar.shuffle_button, bar.repeat_button, bar.queue_button, bar.lyrics_button,
        )))
        self.assertFalse(bar.more_button.isVisible())

    def test_playerbar_uses_only_the_fixed_local_fluent_manifest(self) -> None:
        manifest_path = PROJECT_ROOT / "app" / "ui_v2" / "assets" / "icons" / "fluent_player" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_files = {entry["filename"] for entry in manifest["icons"]}
        self.assertEqual(manifest_files, set(FLUENT_PLAYER_ASSETS.values()))
        bar = self.window.player_bar
        expected = {
            bar.favorite_button: "heart_20_regular.svg",
            bar.shuffle_button: "arrow_shuffle_20_regular.svg",
            bar.previous_button: "previous_frame_20_filled.svg",
            bar.play_button: "play_24_filled.svg",
            bar.next_button: "next_frame_20_filled.svg",
            bar.repeat_button: "arrow_repeat_all_20_regular.svg",
            bar.queue_button: "document_queue_24_regular.svg",
            bar.lyrics_button: "subtitles_20_regular.svg",
            bar.volume_button: "speaker_2_20_regular.svg",
            bar.more_button: "more_horizontal_20_regular.svg",
        }
        self.assertTrue(all(button.asset_family == "fluent_player" for button in expected))
        self.assertEqual({button.asset_filename for button in expected}, set(expected.values()))
        self.assertTrue(all(path.read_text(encoding="utf-8").isascii() for path in manifest_path.parent.glob("*.svg")))

    def test_fluent_player_render_cache_includes_file_size_color_dpr_and_play_offset(self) -> None:
        bar = self.window.player_bar
        bar.play_button._refresh_icon()
        bar.favorite_button._refresh_icon()
        self.assertTrue(any(key[0] == "play_24_filled.svg" and key[1] == 22 for key in _FLUENT_PLAYER_PIXMAP_CACHE))
        self.assertTrue(any(key[0] == "heart_20_regular.svg" and key[1] == 18 for key in _FLUENT_PLAYER_PIXMAP_CACHE))

    def test_player_icon_button_uses_one_state_system_without_geometry_jumps(self) -> None:
        bar = self.window.player_bar
        controls = (
            bar.favorite_button,
            bar.shuffle_button,
            bar.previous_button,
            bar.play_button,
            bar.next_button,
            bar.repeat_button,
            bar.queue_button,
            bar.lyrics_button,
            bar.volume_button,
            bar.more_button,
        )
        self.assertTrue(all(isinstance(button, PlayerIconButton) for button in controls))
        self.assertEqual(bar.play_button.button_size, 52)
        self.assertEqual(bar.play_button.icon_canvas_size, 22)
        self.assertTrue(all(button.icon_canvas_size >= 18 for button in controls if button is not bar.play_button))
        geometries = tuple(button.geometry() for button in controls)
        sizes = tuple(button.sizeHint() for button in controls)

        bar.shuffle_button.set_active(True)
        bar.repeat_button.set_active(True)
        self.app.processEvents()
        self.assertIn("background: transparent", bar.shuffle_button.styleSheet())
        self.assertIn("background: transparent", bar.repeat_button.styleSheet())
        self.assertNotIn(get_theme("dark").colors.accent, bar.repeat_button.styleSheet())
        self.assertEqual(tuple(button.geometry() for button in controls), geometries)
        self.assertEqual(tuple(button.sizeHint() for button in controls), sizes)

        bar.shuffle_button.setEnabled(False)
        self.assertIn("background: transparent", bar.shuffle_button.styleSheet())
        self.assertEqual(tuple(button.geometry() for button in controls), geometries)

    def test_player_side_regions_center_natural_width_in_double_stretch_outers(self) -> None:
        bar = self.window.player_bar
        self.window.playback_adapter.play()
        for outer, inner, layout in (
            (bar.track_region, bar.track_inner, bar.track_region_layout),
            (bar.utility_region, bar.utility_inner, bar.utility_region_layout),
        ):
            self.assertIsInstance(layout, QHBoxLayout)
            self.assertEqual(layout.count(), 3)
            self.assertEqual(layout.stretch(0), 1)
            self.assertIs(layout.itemAt(1).widget(), inner)
            self.assertEqual(layout.stretch(2), 1)
            self.assertEqual(inner.sizePolicy().horizontalPolicy(), inner.sizePolicy().Policy.Maximum)
            alignment = layout.itemAt(1).alignment()
            self.assertTrue(alignment & Qt.AlignmentFlag.AlignHCenter)
            self.assertFalse(alignment & Qt.AlignmentFlag.AlignLeft)
            self.assertFalse(alignment & Qt.AlignmentFlag.AlignRight)

        instances = (bar, self.window.sidebar)
        for width, height in ((900, 600), (1200, 800), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            for outer, inner in ((bar.track_region, bar.track_inner), (bar.utility_region, bar.utility_inner)):
                outer_center = outer.mapTo(bar, outer.rect().center()).x()
                inner_center = inner.mapTo(bar, inner.rect().center()).x()
                self.assertLessEqual(abs(inner_center - outer_center), 2)
            self.assertLessEqual(
                abs(bar.play_button.mapTo(bar, bar.play_button.rect().center()).x() - bar.rect().center().x()),
                2,
            )
        self.assertIs(self.window.player_bar, instances[0])
        self.assertIs(self.window.sidebar, instances[1])

    def test_formal_shuffle_and_repeat_icons_keep_button_geometry_stable(self) -> None:
        bar = self.window.player_bar
        self.window.playback_adapter.play()
        self.app.processEvents()
        self.assertEqual(bar.shuffle_button.icon_name, "shuffle")
        self.assertEqual(bar.shuffle_button.toolTip(), "随机播放")
        self.assertEqual(bar.repeat_button.icon_name, "repeat")
        self.assertEqual(bar.repeat_button.toolTip(), "列表循环")
        button_rects = (bar.shuffle_button.geometry(), bar.repeat_button.geometry())

        self.window.playback_adapter.toggle_shuffle()
        self.window.playback_adapter.cycle_repeat_mode()
        self.app.processEvents()
        self.assertTrue(bar.shuffle_button.active)
        self.assertTrue(bar.repeat_button.active)
        self.assertEqual(self.window.playback_adapter.state.repeat_mode, RepeatMode.ONE)
        self.assertEqual(bar.repeat_button.icon_name, "repeat_one")
        self.assertEqual(bar.repeat_button.toolTip(), "单曲循环")
        self.assertEqual((bar.shuffle_button.geometry(), bar.repeat_button.geometry()), button_rects)

        self.window.playback_adapter.cycle_repeat_mode()
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.repeat_mode, RepeatMode.OFF)
        self.assertEqual(bar.repeat_button.icon_name, "repeat")
        self.assertEqual(bar.repeat_button.toolTip(), "关闭循环")
        self.assertFalse(bar.repeat_button.active)
        self.assertIn("background: transparent", bar.repeat_button.styleSheet())
        self.assertEqual((bar.shuffle_button.geometry(), bar.repeat_button.geometry()), button_rects)

        repeat_image = icon("repeat", get_theme("dark")).pixmap(QSize(24, 24)).toImage()
        repeat_one_image = icon("repeat_one", get_theme("dark")).pixmap(QSize(24, 24)).toImage()
        self.assertNotEqual(repeat_image, repeat_one_image)

    def test_player_bar_uses_approved_three_region_hierarchy(self) -> None:
        bar = self.window.player_bar
        self.assertEqual(bar.height(), 102)
        self.assertIs(bar.track_region.parentWidget(), bar)
        self.assertIs(bar.center_region.parentWidget(), bar)
        self.assertIs(bar.utility_region.parentWidget(), bar)
        self.assertIs(bar.transport_row.parentWidget(), bar.center_region)
        self.assertIs(bar.progress_row.parentWidget(), bar.center_region)
        self.assertNotEqual(bar.track_region.parentWidget(), bar.transport_row)
        self.assertNotEqual(bar.utility_region.parentWidget(), bar.transport_row)
        self.assertEqual(bar.track_region.height(), bar.contentsRect().height())
        self.assertEqual(bar.utility_region.height(), bar.contentsRect().height())
        self.assertLessEqual(abs(bar.play_button.mapTo(bar, bar.play_button.rect().center()).x() - bar.rect().center().x()), 4)

    def test_player_metadata_is_one_compact_two_line_group_in_all_widths(self) -> None:
        bar = self.window.player_bar
        metadata_layout = bar.metadata.layout()
        self.assertIsInstance(metadata_layout, QVBoxLayout)
        self.assertEqual(metadata_layout.count(), 2)
        self.assertEqual(metadata_layout.stretch(0), 0)
        self.assertEqual(metadata_layout.stretch(1), 0)
        self.assertEqual(bar.metadata.height(), 36)
        self.assertIs(bar.title_label.parentWidget(), bar.metadata)
        self.assertIs(bar.artist_label.parentWidget(), bar.metadata)
        self.window.playback_adapter.play()
        for width, height in ((900, 600), (1200, 800), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            metadata_center = bar.metadata.mapTo(bar, bar.metadata.rect().center()).y()
            track_center = bar.track_region.mapTo(bar, bar.track_region.rect().center()).y()
            title_bottom = bar.title_label.mapTo(bar, bar.title_label.rect().bottomLeft()).y()
            artist_top = bar.artist_label.mapTo(bar, bar.artist_label.rect().topLeft()).y()
            self.assertLessEqual(abs(metadata_center - track_center), 2)
            self.assertGreaterEqual(artist_top - title_bottom, 1)
            self.assertLessEqual(artist_top - title_bottom, 4)
            self.assertEqual(bar.metadata.height(), 36)

    def test_player_empty_artwork_and_repeat_states_are_explicit(self) -> None:
        bar = self.window.player_bar
        self.window.playback_adapter.clear()
        self.window.playback_adapter.cycle_repeat_mode()
        self.window.playback_adapter.cycle_repeat_mode()
        self.app.processEvents()
        empty_artwork = bar.artwork.pixmap()
        self.assertIsNotNone(empty_artwork)
        self.assertFalse(empty_artwork.isNull())
        self.assertEqual(bar.title_label.full_text, "未选择歌曲")
        self.assertEqual(bar.artist_label.full_text, "选择一首歌曲开始播放")
        self.assertFalse(bar.repeat_button.active)
        self.assertFalse(bool(bar.repeat_button.property("selected")))
        self.assertIn("background: transparent", bar.repeat_button.styleSheet())

        self.window.playback_adapter.play()
        self.window.playback_adapter.cycle_repeat_mode()
        self.app.processEvents()
        self.assertTrue(bar.repeat_button.active)
        self.assertTrue(bool(bar.repeat_button.property("selected")))
        self.assertIn("background: transparent", bar.repeat_button.styleSheet())
        self.assertNotIn(get_theme("dark").colors.accent, bar.repeat_button.styleSheet())
        self.assertFalse(bar.repeat_button.isHidden())
        self.assertFalse(any(
            marker in value.casefold()
            for value in (bar.title_label.full_text, bar.artist_label.full_text, bar.artwork.toolTip())
            for marker in ("mock", "demo", "preview", "fixture")
        ))

    def test_resize_keeps_adapters_models_and_player_bar_instances(self) -> None:
        page = self.window.router.browse_page
        player_bar = self.window.player_bar
        adapter = self.window.playback_adapter
        model = self.window.library_page.track_table.model
        for width, expected_cards, compact in ((900, 3, True), (1200, 5, False), (1600, 7, False)):
            self.window.resize(width, 600 if width == 900 else 800)
            self.app.processEvents()
            self.assertEqual(page.target_card_count, expected_cards)
            self.assertEqual(self.window.sidebar.compact, compact)
            self.assertEqual(player_bar.compact, compact)
            self.assertIs(self.window.playback_adapter, adapter)
            self.assertIs(self.window.library_page.track_table.model, model)
            self.assertIs(self.window.player_bar, player_bar)
        self.assertEqual(self.window.sidebar.brand_label.text(), "HushPlayer")
        self.assertTrue(player_bar.more_button.isHidden())

    def test_content_safe_area_is_owned_by_the_shared_router_contract(self) -> None:
        expected = get_theme("dark").metrics.player_bar_height + get_theme("dark").metrics.content_safe_bottom
        self.assertEqual(self.window.router.content_safe_bottom, expected)
        self.assertEqual(self.window.router.browse_page.content_safe_bottom, expected)


if __name__ == "__main__":
    unittest.main()
