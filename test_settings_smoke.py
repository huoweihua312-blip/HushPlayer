# -*- coding: utf-8 -*-
"""Smoke test for settings dialog"""

import sys
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QObject, Signal
from app.ui.settings_dialog import SettingsDialog

class MockMainWindow(QMainWindow):
    """Mock main window for testing"""
    def __init__(self):
        super().__init__()

        # Mock theme manager
        class MockThemeManager(QObject):
            themeChanged = Signal(str)
        self.theme_manager = MockThemeManager()

        # Mock online audio cache
        class MockAudioCache(QObject):
            statisticsChanged = Signal()
            cache_root = "C:\\Users\\Test\\AppData\\Local\\HushPlayer\\AudioCache"

            def statistics(self):
                return {
                    'total_files': 10,
                    'total_size': 1024 * 1024 * 100,
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
            "music_scan_folders": ["C:\\Music"],
            "music_scan_import_mode": "pending",
            "auto_scan_music_folders_on_startup": True,
            "update_check_delay_seconds": 15,
        }

    def check_for_updates(self, manual=False):
        """Mock update check"""
        pass

def run_smoke_test():
    """Run smoke test"""
    app = QApplication.instance() or QApplication(sys.argv)

    print("=" * 70)
    print("Settings Dialog Smoke Test")
    print("=" * 70)
    print()

    # Test 1: Construction
    print("✓ Test 1: Constructing SettingsDialog...")
    main_window = MockMainWindow()
    dialog = SettingsDialog(main_window)
    print("  ✓ SettingsDialog instantiated successfully")

    # Test 2: Navigation count
    print("\n✓ Test 2: Checking navigation items...")
    nav_count = dialog.nav_list.count()
    assert nav_count == 8, f"Expected 8 categories, got {nav_count}"
    print(f"  ✓ Navigation has exactly 8 categories")

    # Test 3: Category names
    print("\n✓ Test 3: Verifying category names...")
    expected_categories = ["常规", "外观", "播放", "歌词", "音乐库", "缓存", "更新", "关于"]
    for i, expected in enumerate(expected_categories):
        item = dialog.nav_list.item(i)
        actual = item.text() if item else None
        assert actual == expected, f"Category {i}: expected '{expected}', got '{actual}'"
        print(f"  ✓ Category {i}: {actual}")

    # Test 4: Pages count
    print("\n✓ Test 4: Checking pages...")
    assert len(dialog.pages) == 8, f"Expected 8 pages, got {len(dialog.pages)}"
    print(f"  ✓ Created exactly 8 pages")

    # Test 5: Playback page exists
    print("\n✓ Test 5: Checking playback page...")
    assert hasattr(dialog, 'page_playback'), "Missing page_playback"
    print("  ✓ Playback page exists")

    # Test 6: All key controls exist
    print("\n✓ Test 6: Checking key controls...")
    key_controls = [
        'restore_checkbox',
        'auto_scan_checkbox',
        'floating_auto_open_checkbox',
        'appearance_mode_combo',
        'immersive_background_mode_combo',
        'auto_hide_checkbox',
        'alpha_slider',
        'floating_color_combo',
        'floating_opacity_slider',
        'floating_font_slider',
        'floating_width_slider',
        'music_scan_folder_list',
        'music_scan_import_mode_combo',
        'audio_cache_summary_label',
        'audio_cache_path_label',
        'auto_update_checkbox',
        'update_delay_combo',
        'check_update_button',
    ]

    missing = []
    for control in key_controls:
        if not hasattr(dialog, control):
            missing.append(control)

    assert not missing, f"Missing controls: {missing}"
    print(f"  ✓ All {len(key_controls)} key controls present")

    # Test 7: Category switching
    print("\n✓ Test 7: Testing category switching...")
    dialog.show()

    # Test switching to each category
    for i in range(8):
        dialog._on_category_changed(i)
        assert dialog.pages[i].isVisible(), f"Page {i} should be visible"

        # Check only one page is visible
        visible_count = sum(1 for p in dialog.pages if p.isVisible())
        assert visible_count == 1, f"Expected 1 visible page, got {visible_count}"

    print("  ✓ All 8 categories can be switched")
    print("  ✓ Only one page visible at a time")

    # Test 8: collect_settings_updates
    print("\n✓ Test 8: Testing collect_settings_updates...")
    updates = dialog.collect_settings_updates()

    required_keys = [
        "appearance_mode",
        "restore_last_playback",
        "auto_scan_music_folders_on_startup",
        "floating_lyrics_auto_open",
        "floating_lyrics_color",
        "floating_lyrics_opacity",
        "floating_lyrics_font_size",
        "floating_lyrics_width",
        "immersive_auto_hide_ui",
        "music_scan_folders",
        "music_scan_import_mode",
        "auto_check_updates_on_startup",
        "update_check_delay_seconds",
    ]

    missing_keys = [k for k in required_keys if k not in updates]
    assert not missing_keys, f"Missing keys: {missing_keys}"
    print(f"  ✓ Returns all {len(required_keys)} required keys")

    # Test 9: Dialog can close
    print("\n✓ Test 9: Testing dialog close...")
    dialog.close()
    print("  ✓ Dialog closes without error")

    # Test 10: Window size
    print("\n✓ Test 10: Checking window constraints...")
    min_width = dialog.minimumWidth()
    min_height = dialog.minimumHeight()
    print(f"  ✓ Minimum size: {min_width}x{min_height}")
    assert min_width >= 900, f"Minimum width should be at least 900, got {min_width}"
    assert min_height >= 600, f"Minimum height should be at least 600, got {min_height}"

    print("\n" + "=" * 70)
    print("✓ ALL SMOKE TESTS PASSED")
    print("=" * 70)

    print("\n8 个分类的控件分布：")
    print("  1. 常规 - 启动时自动扫描、启动时自动打开桌面歌词")
    print("  2. 外观 - 主题设置")
    print("  3. 播放 - 启动时恢复上次播放")
    print("  4. 歌词 - 沉浸歌词、桌面歌词设置")
    print("  5. 音乐库 - 文件夹管理、扫描设置")
    print("  6. 缓存 - 元数据缓存、音频缓存")
    print("  7. 更新 - 应用更新设置")
    print("  8. 关于 - 应用信息")

    return True

if __name__ == '__main__':
    try:
        success = run_smoke_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ SMOKE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
