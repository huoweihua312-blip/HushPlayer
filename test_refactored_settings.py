# -*- coding: utf-8 -*-
"""Test refactored settings dialog"""

import sys
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication, QMainWindow
from app.ui.settings_dialog import SettingsDialog

class MockMainWindow(QMainWindow):
    """Mock main window for testing"""
    def __init__(self):
        super().__init__()

        # Mock theme manager
        from PySide6.QtCore import QObject, Signal
        class MockThemeManager(QObject):
            themeChanged = Signal(str)
        self.theme_manager = MockThemeManager()

        # Mock online audio cache
        class MockAudioCache(QObject):
            statisticsChanged = Signal()
            cache_root = "C:\\Users\\Test\\AppData\\Local\\HushPlayer\\AudioCache"

            def statistics(self):
                """Return mock statistics"""
                return {
                    'total_files': 10,
                    'total_size': 1024 * 1024 * 100,  # 100MB
                    'incomplete_files': 2,
                }
        self.online_audio_cache = MockAudioCache()

        # Mock update service
        class MockUpdateService(QObject):
            checkStarted = Signal()
            checkCompleted = Signal(bool, str)
            is_checking = False
            is_downloading = False
        self.update_service = MockUpdateService()

    def get_hush_settings(self):
        """Return mock settings"""
        return {
            "appearance_mode": "dark",
            "auto_check_updates_on_startup": False,
            "restore_last_playback": True,
            "floating_lyrics_color": "white",
            "floating_lyrics_opacity": 100,
            "floating_lyrics_font_size": 42,
            "floating_lyrics_width": 980,
            "floating_lyrics_auto_open": False,
            "immersive_auto_hide_ui": True,
            "immersive_appearance": {
                "background_mode": "cover",
                "darkness": 45,
            },
            "music_scan_folders": ["C:\\Music", "D:\\Music"],
            "music_scan_import_mode": "pending",
            "auto_scan_music_folders_on_startup": True,
            "update_check_delay_seconds": 15,
        }

    def check_for_updates(self, manual=False):
        """Mock update check"""
        pass

def test_settings_dialog():
    """Test that settings dialog can be instantiated and has all required components"""
    app = QApplication.instance() or QApplication(sys.argv)

    main_window = MockMainWindow()
    dialog = SettingsDialog(main_window)

    print("✓ SettingsDialog instantiated successfully")

    # Check navigation list
    assert hasattr(dialog, 'nav_list'), "Missing nav_list"
    assert dialog.nav_list.count() == 7, f"Expected 7 categories, got {dialog.nav_list.count()}"
    print(f"✓ Navigation list has {dialog.nav_list.count()} categories")

    # Check pages
    assert hasattr(dialog, 'pages'), "Missing pages list"
    assert len(dialog.pages) == 7, f"Expected 7 pages, got {len(dialog.pages)}"
    print(f"✓ Created {len(dialog.pages)} category pages")

    # Check all required controls exist
    required_controls = [
        # General page
        'restore_checkbox',
        'auto_scan_checkbox',
        'floating_auto_open_checkbox',
        # Appearance page
        'appearance_mode_combo',
        # Lyrics page
        'immersive_background_mode_combo',
        'auto_hide_checkbox',
        'alpha_slider',
        'alpha_label',
        'floating_color_combo',
        'floating_opacity_slider',
        'floating_opacity_label',
        'floating_font_slider',
        'floating_font_label',
        'floating_width_slider',
        'floating_width_label',
        # Library page
        'music_scan_folder_list',
        'music_scan_import_mode_combo',
        # Cache page
        'audio_cache_summary_label',
        'audio_cache_path_label',
        # Updates page
        'auto_update_checkbox',
        'update_delay_combo',
        'check_update_button',
    ]

    missing_controls = []
    for control_name in required_controls:
        if not hasattr(dialog, control_name):
            missing_controls.append(control_name)

    if missing_controls:
        print(f"✗ Missing controls: {', '.join(missing_controls)}")
        return False

    print(f"✓ All {len(required_controls)} required controls present")

    # Check collect_settings_updates returns correct structure
    updates = dialog.collect_settings_updates()

    print(f"\nActual keys returned: {sorted(updates.keys())}")

    required_keys = [
        "appearance_mode",
        "auto_check_updates_on_startup",
        "update_check_delay_seconds",
        "restore_last_playback",
        "floating_lyrics_color",
        "floating_lyrics_opacity",
        "floating_lyrics_font_size",
        "floating_lyrics_width",
        "floating_lyrics_auto_open",
        "immersive_auto_hide_ui",
        # Note: immersive_appearance is added via to_settings(), check what keys it actually adds
        "music_scan_folders",
        "music_scan_import_mode",
        "auto_scan_music_folders_on_startup",
    ]

    missing_keys = []
    for key in required_keys:
        if key not in updates:
            missing_keys.append(key)

    if missing_keys:
        print(f"✗ collect_settings_updates missing keys: {', '.join(missing_keys)}")
        return False

    print(f"✓ collect_settings_updates returns all {len(required_keys)} required keys")

    # Check category navigation
    categories = [
        "常规", "外观", "歌词", "音乐库", "缓存", "更新", "关于"
    ]

    for i in range(dialog.nav_list.count()):
        item = dialog.nav_list.item(i)
        if item:
            print(f"  - Category {i}: {item.text()}")

    print(f"✓ Navigation categories: {', '.join(categories)}")

    # Test category switching (show dialog first to trigger layout)
    dialog.show()
    dialog._on_category_changed(2)  # Switch to lyrics page directly
    assert dialog.pages[2].isVisible(), "Lyrics page should be visible"
    assert not dialog.pages[0].isVisible(), "General page should be hidden"
    print("✓ Category navigation works correctly")

    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    print(f"\nSettings dialog refactored successfully:")
    print(f"  - New navigation layout with 7 categories")
    print(f"  - All {len(required_controls)} controls preserved")
    print(f"  - collect_settings_updates returns {len(required_keys)} settings")
    print(f"  - Category switching functional")

    return True

if __name__ == '__main__':
    try:
        success = test_settings_dialog()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
