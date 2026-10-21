"""GUI 冒烟：真实主窗口构造、路由切换、主题切换、沉浸模式与桌面歌词。

这些用例跑在 offscreen 平台上，只验证「能构造、能切换、不抛异常」，
视觉验收由 tools/shot_app.py 生成的真实截图负责。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from hushplayer.core import paths

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def app_bundle(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from hushplayer.ui.context import AppContext, ctx, set_context
    from hushplayer.services.library import LibraryService
    from hushplayer.store.db import Database

    data = tmp_path_factory.mktemp("gui-data")
    paths.set_data_dir(data)
    application = QApplication.instance() or QApplication([])

    database = Database(paths.database_file())
    database.initialize()
    library = LibraryService(database)

    # 只构造 UI 需要的服务，避免真机扫描与网络请求
    from hushplayer.audio.controller import PlayerController
    from hushplayer.library.artwork import ArtworkStore
    from hushplayer.online.client import OnlineSourceClient
    from hushplayer.online.proxy import AudioProxy
    from hushplayer.core.settings import Settings
    from hushplayer.services.cache import CacheService
    from hushplayer.services.state import PlaybackKeeper
    from hushplayer.lyrics.service import LyricsService

    settings = Settings(paths.settings_file())
    settings.load()
    settings.set("library.auto_scan_on_start", False, save=False)
    settings.set("general.check_updates_on_start", False, save=False)

    proxy = AudioProxy(cache_dir=paths.audio_cache_dir())
    client = OnlineSourceClient()
    player = PlayerController(client=client, proxy=proxy)
    lyrics = LyricsService(library.tracks, library.bindings, library.meta, client)
    keeper = PlaybackKeeper(player, library.tracks)
    artwork = ArtworkStore(paths.artwork_cache_dir())
    cache = CacheService(proxy, artwork)

    set_context(
        AppContext(
            library=library,
            player=player,
            lyrics=lyrics,
            cache=cache,
            covers=library.covers,
            client=client,
            proxy=proxy,
            keeper=keeper,
            settings=settings,
            window=None,
            desktop_lyrics=None,
            immersive=None,
        )
    )
    assert ctx() is not None

    from hushplayer.core.theme import apply_theme_to_app

    apply_theme_to_app(application, preference="dark")

    from hushplayer.ui.main_window import MainWindow

    window = MainWindow()
    ctx().window = window
    window.show()
    application.processEvents()

    yield application, window, library, player

    window.close()
    player.shutdown()
    client.stop()
    proxy.shutdown()
    library.close()
    database.close_current_thread()


def pump(application, seconds: float = 0.15) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)


def test_navigate_every_route(app_bundle) -> None:
    application, window, library, player = app_bundle
    routes = ["home", "songs", "albums", "artists", "favorites", "recent", "search", "settings", "lyrics"]
    for route in routes:
        window.navigate(route)
        pump(application)
        assert window.stack.currentWidget() is not None, route
    window.navigate("songs")
    pump(application)


def test_playlist_and_detail_routes(app_bundle) -> None:
    application, window, library, player = app_bundle
    playlist_id = library.create_playlist("冒烟歌单")
    window.navigate(f"playlist:{playlist_id}")
    pump(application)
    albums = library.albums()
    artists = library.artists()
    if albums:
        window.navigate("album", albums[0].id)
        pump(application)
    if artists:
        window.navigate("artist", artists[0].id)
        pump(application)
    assert window.stack.currentWidget() is not None


def test_history_back_forward(app_bundle) -> None:
    application, window, library, player = app_bundle
    window.navigate("songs")
    pump(application)
    window.navigate("albums")
    pump(application)
    window.go_back()
    pump(application)
    assert window.current_route == "songs"
    window.go_forward()
    pump(application)
    assert window.current_route == "albums"


def test_theme_switch_keeps_pages_alive(app_bundle) -> None:
    application, window, library, player = app_bundle
    window.navigate("songs")
    pump(application)
    for mode in ("light", "dark"):
        window.apply_theme(mode)
        pump(application, 0.2)
        assert window.stack.currentWidget() is not None


def test_immersive_open_and_close(app_bundle) -> None:
    application, window, library, player = app_bundle
    window.open_immersive()
    pump(application, 0.3)
    immersive = getattr(window, "immersive", None) or __import__("hushplayer.ui.context", fromlist=["ctx"]).ctx().immersive
    assert immersive is not None
    assert immersive.isVisible()
    immersive.set_mode("lyrics", animate=False)
    pump(application, 0.2)
    assert immersive.mode == "lyrics"
    immersive.set_mode("cover", animate=False)
    pump(application, 0.2)
    assert immersive.mode == "cover"
    immersive.close_immersive()
    pump(application, 0.2)


def test_desktop_lyrics_window(app_bundle) -> None:
    application, window, library, player = app_bundle
    from hushplayer.ui.desktop_lyrics import ensure_desktop_lyrics

    desktop = ensure_desktop_lyrics()
    assert desktop is not None
    desktop.show_lyrics()
    pump(application, 0.2)
    assert desktop.isVisible()
    desktop.hide_lyrics()
    pump(application, 0.1)
    assert not desktop.isVisible()


def test_playerbar_controls_reach_controller(app_bundle) -> None:
    application, window, library, player = app_bundle
    window.navigate("songs")
    pump(application)
    bar = window.playerbar
    bar.volume.set_value(0.25)
    bar.volume.value_changed.emit(0.25)
    pump(application)
    assert abs(player.volume - 0.25) < 0.02
    before_shuffle = player.shuffle
    bar.shuffle.click()
    pump(application)
    assert player.shuffle is not before_shuffle
    before_repeat = player.repeat
    bar.repeat.click()
    pump(application)
    assert player.repeat != before_repeat


FIXTURE_AUDIO = Path(__file__).parent / "fixtures" / "audio"


def _import_fixtures(library) -> None:
    files = [
        str(path)
        for path in FIXTURE_AUDIO.rglob("*")
        if path.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac"}
    ]
    library.import_files(files)


def test_favorite_heart_does_not_break_favorites_page(app_bundle) -> None:
    """R6: clicking the heart on 我喜欢 raised AttributeError in _sync_current.

    ``TrackListWidget`` is a thin composite around ``TrackTable`` and had lost
    the ``ensure_current_visible`` passthrough, so reloading the page while a
    track is playing crashed in a Qt slot (silently, via the excepthook).
    """
    application, window, library, player = app_bundle
    _import_fixtures(library)
    window.navigate("favorites")
    pump(application)


    page = window._pages["favorites"]
    tracks = library.search_local("夜航", limit=1) or library.recent(1)
    assert tracks, "fixtures should provide at least one track"
    track = tracks[0]

    captured: list = []
    previous = sys.excepthook
    sys.excepthook = lambda *args: captured.append(args)
    try:
        library.toggle_favorite(track)
        pump(application, 0.3)
        page._sync_current()
        page.list.ensure_current_visible()
    finally:
        sys.excepthook = previous

    assert not captured, captured
    assert library.is_favorite(track)
    assert page.list.tracks(), "favorites page should list the toggled track"

    # undo so later tests in this module see the same state
    library.toggle_favorite(track)
    pump(application, 0.2)


def test_no_tray_falls_back_to_taskbar(app_bundle) -> None:
    """没有托盘图标时最小化到任务栏，窗口不会消失到找不到。"""
    _application, window, _library, _player = app_bundle
    window.show()
    window._tray_ok = False
    window._background_without_tray()
    assert window.isMinimized()
    assert window.isVisible()
    window.showNormal()


def test_window_state_changes_survive_tray_state(app_bundle) -> None:
    """Maximise / minimise must not depend on tray attributes existing.

    Regression: ``changeEvent`` referenced ``_tray_available`` after the method
    was removed during a tray rewrite, so every maximise crashed with
    ``AttributeError`` (the window then stayed half-toggled).
    """
    from PySide6.QtCore import QEvent, Qt

    application, window, _library, _player = app_bundle
    assert hasattr(window, "_tray_available")
    window.show()
    window.toggle_maximize()
    window.showNormal()
    # A stray WindowStateChange event must be harmless as well.
    window.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    window.setWindowState(window.windowState() | window.windowState().WindowMaximized)
    window.setWindowState(window.windowState() & ~Qt.WindowMaximized)
    application.processEvents()
    assert not window.isMinimized()


@pytest.mark.integration
def test_tray_failure_keeps_window_reachable(app_bundle, monkeypatch):
    """A refused Shell_NotifyIcon must never leave a hidden, unreachable window."""
    application, window, _library, _player = app_bundle
    window.show()
    monkeypatch.setattr(window, "_tray_ok", False, raising=False)
    assert window._tray_available() is False

    window._hide_to_tray()
    application.processEvents()
    # Falls back to the taskbar instead of hiding with no icon to click.
    assert window.isVisible()
    assert window.isMinimized()

def test_settings_page_fits_small_window(app_bundle) -> None:
    """880×580 时设置页不应出现横向滚动，导航文字也不该被截断。"""
    from PySide6.QtWidgets import QApplication, QScrollArea

    from hushplayer.ui.pages.settings import SettingsPage

    application = QApplication.instance() or QApplication([])
    page = SettingsPage()
    page.resize(880, 580)
    page.show()
    application.processEvents()
    page.resize(880, 580)
    application.processEvents()

    assert page._nav.width() >= page._nav.preferred_width()
    assert page.header.height() > 0

    overflows = [
        area
        for area in page.findChildren(QScrollArea)
        if area.horizontalScrollBar().maximum() > 0
    ]
    assert overflows == [], "设置页出现横向滚动"

    page.close()


def test_setting_row_stacks_control_when_narrow() -> None:
    """窄宽度下控件换行到标题下方，宽宽度下回到同一行右侧。"""
    from PySide6.QtWidgets import QApplication, QLabel

    from hushplayer.ui.widgets.settings_widgets import SettingRow

    application = QApplication.instance() or QApplication([])
    control = QLabel("control")
    row = SettingRow("恢复上次浏览的页面", "重新打开应用时回到上次离开的位置", control=control)

    row.resize(760, 120)
    row.show()
    application.processEvents()
    wide_y = control.geometry().y()
    wide_x = control.geometry().x()
    assert wide_x > row.title_label.geometry().x()

    row.resize(320, 160)
    application.processEvents()
    narrow_y = control.geometry().y()
    assert narrow_y > wide_y
    assert control.geometry().x() > row.title_label.geometry().x()
    row.close()

def test_source_badge_hides_raw_import_ids():
    from hushplayer.model.track import Track
    from hushplayer.ui.widgets.hover_tip import display_source, tip_text

    track = Track(
        id="online:x:1", title="Colt.45", artist="弹壳Danko", album="黄金追踪者",
        source_id="x", source_name="user_source_540939a8398b", kind="online",
    )
    assert display_source(track) == "自建音源"
    assert "user_source_" not in tip_text(track)
    assert "自建音源" in tip_text(track)

    known = Track(
        id="online:y:1", title="家书", artist="加木", source_id="y",
        source_name="酷我", kind="online",
    )
    assert display_source(known) == "酷我"

    long_name = Track(id="online:z:1", title="t", source_id="z",
                      source_name="一个非常非常长的音源名字", kind="online")
    assert len(display_source(long_name)) <= 18

def test_queue_duration_column_fits_its_text(app_bundle):
    """The duration column must hold "4:02" at the current type scale."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QAbstractItemView
    from hushplayer.core.theme import theme
    from hushplayer.model.track import Track
    from hushplayer.ui.widgets.tracklist import COLUMN_DURATION, DEFAULT_COLUMNS, TrackTable

    table = TrackTable()
    table.setVerticalScrollBarPolicy(table.verticalScrollBarPolicy())
    table.resize(340, 420)
    table.set_tracks([Track(id="kw:1", title="家书", artist="加木", duration_ms=242000,
                           kind="online", source_id="x", source_name="酷我")])
    table._apply_columns()
    index = DEFAULT_COLUMNS.index(next(c for c in DEFAULT_COLUMNS if c.key == COLUMN_DURATION))
    needed = QFontMetrics(theme().font(8.4, 400)).horizontalAdvance("4:02") + 12
    assert table.columnWidth(index) >= needed
    table.deleteLater()


def test_immersive_queue_keeps_app_palette(app_bundle):
    """The stage queue paints dark locally and must not hijack the app theme."""
    from hushplayer.core.theme import DARK, theme
    from hushplayer.ui.widgets.queue_panel import QueuePanel

    panel = QueuePanel(immersive=True)
    before = theme().palette
    panel.activate_palette()
    assert theme().palette is before
    assert panel.list.table.palette_override is DARK
    panel.release_palette()
    assert panel.list.table.palette_override is None
    assert theme().palette is before

def test_popup_menus_and_combos_use_rounded_theme(app_bundle):
    """Menus and combo popups must use the themed popup, not native chrome."""
    from PySide6.QtCore import Qt

    from hushplayer.ui.widgets.menu import themed_menu
    from hushplayer.ui.widgets.settings_widgets import SettingCombo, _RoundedRowDelegate

    menu = themed_menu()
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    combo = SettingCombo([("过渡动画（从标题栏按钮扩散）", "reveal"), ("关闭", "off")])
    assert isinstance(combo.view().itemDelegate(), _RoundedRowDelegate)
    assert combo.view().window().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
