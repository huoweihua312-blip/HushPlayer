"""Capture isolated formal-startup UI fixtures; never use the user's library."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='hush-ui-baseline-') as temporary:
        settings = str(Path(temporary) / 'settings.json')
        os.environ.update(HUSHPLAYER_APP_DATA_DIR=temporary, HUSHPLAYER_CACHE_DIR=temporary,
                          HUSHPLAYER_UI_V2_SETTINGS_PATH=settings, HUSHPLAYER_UI_V2_DATA_MODE='mock')
        from app.startup import create_application_context
        context = create_application_context(['ui-baseline'], settings_path=settings)
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from app.ui_v2.shell.main_window import MainWindow
        from app.ui_v2.models.track_table_model import TrackColumn
        app = QApplication.instance()
        window = MainWindow(data_mode='mock', settings_path=settings)
        window.playback_adapter._timer_enabled = False
        window.show()
        records = []

        def capture(name):
            app.processEvents()
            QTest.qWait(120)
            path = args.output / (name + '.png')
            if not window.grab().save(str(path)):
                raise RuntimeError(f'Cannot save {path}')
            records.append({'file': path.name, 'width': window.width(), 'height': window.height(),
                            'dpr': window.devicePixelRatioF(), 'route': window.navigation_adapter.route})

        collection = window.library_page.adapter.collection
        original = collection.tracks()
        sample = next(t for t in original if not t.is_missing)
        long_track = replace(sample, id='baseline-long', title='这是一首用于验证长歌名省略和布局稳定性的歌曲·现场特别版本' * 3,
                             artist='很长的歌手名称与合作音乐人', stable_identity='baseline-long')
        collection.set_tracks([long_track, *original])
        tracks = collection.tracks()
        geometry = []
        for mode in ('light', 'dark'):
            window.set_theme(mode)
            for width in (900, 1080, 1450):
                window.navigation_adapter.set_route('library')
                window.resize(width, 800)
                app.processEvents()
                table = window.library_page.track_table
                row = next(i for i,t in enumerate(table.model.tracks()) if t.id == long_track.id)
                table.doubleClicked.emit(table.model.index(row, int(TrackColumn.TITLE)))
                table.selectRow((row + 1) % table.model.rowCount())
                capture(f'{mode}-{width}-library-playing-selected-long')
                margins = window.library_page.view_stack.contentsMargins()
                geometry.append({'theme': mode, 'window_width': width,
                                 'content_width': window.router.width(), 'viewport_width': table.viewport().width(),
                                 'body_bottom': window.body.geometry().bottom(),
                                 'player_top': window.player_bar_container.geometry().top(),
                                 'surface_bottom_margin': margins.bottom(),
                                 'surface_height': window.library_page.view_host.height(),
                                 'table_bottom_in_surface': table.geometry().bottom(),
                                 'visible_bottom_gap': window.library_page.view_host.height() - table.geometry().bottom() - 1})
                window.open_settings_overlay('general')
                capture(f'{mode}-{width}-settings')
                window.settings_overlay.hide()
                window.navigation_adapter.set_route('lyrics')
                window.lyrics_adapter.load_mock_scenario('chinese_synced')
                window.lyrics_adapter.complete_loading_for_test()
                capture(f'{mode}-{width}-lyrics')
                window.navigation_adapter.set_route('immersive_lyrics')
                capture(f'{mode}-{width}-immersive')
                window.navigation_adapter.set_route('library')
                collection.set_tracks([])
                capture(f'{mode}-{width}-empty')
                collection.set_tracks(tracks)

            window.navigation_adapter.set_route('artists')
            capture(f'{mode}-1450-artists-search-field')

        window.set_theme('light')
        window.resize(1450, 800)
        window.navigation_adapter.set_route('artists')
        artist_id = window.router._artists_adapter.artists()[0].id
        window.navigation_adapter.set_route('artist_detail:' + artist_id)
        page = window.router.currentWidget()
        window.router.setCurrentWidget(page)
        app.processEvents()
        page._set_info_rail('UI baseline：歌手介绍区域，验证宽度来源。')
        before = not page.info_rail.isHidden()
        capture('light-1450-artist-own-width')
        page._update_info_rail_visibility(window.width())
        capture('light-1450-artist-window-width')
        artist = {'window_width': window.width(), 'page_width': page.width(),
                  'own_width_visible': before, 'reference_width_visible': not page.info_rail.isHidden(),
                  'artist_resolved': page._artist is not None}
        manifest = {'platform': os.environ.get('QT_QPA_PLATFORM'), 'python': sys.version,
                    'fixtures': records, 'safe_bottom': geometry, 'artist_rail': artist}
        (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        window.close()
        print(json.dumps({'captures': len(records), 'artist': artist, 'safe_bottom': geometry}, ensure_ascii=False))


if __name__ == '__main__':
    main()
