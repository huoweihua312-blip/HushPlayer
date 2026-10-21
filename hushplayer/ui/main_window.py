"""Main application window: title bar, sidebar, pages and docked player bar."""

from __future__ import annotations

import os
import time
import sys

from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..core.logging_setup import get_logger, log_exception
from ..core.paths import data_dir
from ..core.theme import apply_theme_to_app, theme
from ..core import brand, icons
from .context import ctx
from .menus import playlist_menu
from .widgets.common import TextButton
from .widgets.frameless import FramelessWindow, center_on_screen, ensure_on_screen
from .widgets.playerbar import PlayerBar
from .widgets.queue_panel import QueuePanel
from .widgets.sidebar import Sidebar
from .widgets.titlebar import TitleBar
from .widgets.toast import ToastHost

log = get_logger(__name__)


ROUTE_TITLES = {
    "home": "首页",
    "songs": "歌曲",
    "albums": "专辑",
    "album": "专辑",
    "artists": "歌手",
    "artist": "歌手",
    "favorites": "我喜欢",
    "recent": "最近播放",
    "playlist": "歌单",
    "search": "搜索",
    "settings": "设置",
    "lyrics": "歌词",
    "downloads": "下载",
}


class MainWindow(FramelessWindow):
    route_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HushPlayer")
        self.setMinimumSize(820, 540)
        self.resize(1240, 800)
        self.setWindowIcon(brand.app_icon())

        self._pages: dict[str, QWidget] = {}
        self._history: list[tuple[str, object]] = []
        self._history_index = -1
        self._current_route = ""
        self._toasts: ToastHost | None = None
        self._tray: QSystemTrayIcon | None = None

        self.titlebar = TitleBar(self)
        self.set_titlebar(self.titlebar)
        self.titlebar.sidebar_toggled.connect(self._toggle_sidebar)
        self.titlebar.back_requested.connect(self.go_back)
        self.titlebar.forward_requested.connect(self.go_forward)
        self.titlebar.minimize_requested.connect(self.showMinimized)
        self.titlebar.maximize_requested.connect(self.toggle_maximize)
        self.titlebar.close_requested.connect(self.close_window)
        self.titlebar.theme_toggle_requested.connect(self.toggle_theme_mode)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.navigate)
        self.sidebar.collapsed_changed.connect(self._on_collapsed)
        self.sidebar.playlist_context_menu.connect(self._playlist_menu)
        self.sidebar.create_playlist_requested.connect(self._create_playlist)
        body_layout.addWidget(self.sidebar)

        self.content = QWidget()
        self.content.setObjectName("HushContent")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        background = QWidget()
        background.setObjectName("HushPageBackground")
        # Square corner on purpose: the window itself is translucent so its
        # rounded frame shows the wallpaper, and a rounded page corner would
        # punch a visible notch through to the desktop (bug report: 缺口).
        background.setStyleSheet(
            f"#HushPageBackground {{ background: {theme().palette.window}; }}"
        )
        bg_layout = QVBoxLayout(background)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        bg_layout.addWidget(self.stack)
        content_layout.addWidget(background, 1)
        body_layout.addWidget(self.content, 1)
        self._page_background = background

        self.playerbar = PlayerBar()
        self.playerbar.lyrics_clicked.connect(lambda: self.navigate("lyrics"))
        self.playerbar.queue_clicked.connect(self.toggle_queue)
        self.playerbar.immersive_clicked.connect(self.open_immersive)
        self.playerbar.track_info_clicked.connect(self._go_to_current_album)
        content_layout.addWidget(self.playerbar)

        self.queue_panel = QueuePanel(self.content)
        self.queue_panel.close_requested.connect(self.queue_panel.close_panel)

        self.body_layout().addWidget(body, 1)
        self._toasts = ToastHost(self.container)
        self._toasts.set_bottom_offset(96)

        self._wire_player()
        self._wire_downloads()
        self._wire_library()
        self._install_shortcuts()
        self._build_tray()
        self._restore_geometry()

        self.navigate("home", push=True)
        self.sidebar.set_collapsed(
            not bool(ctx().settings.get("appearance.sidebar_visible", True)), animate=False
        )

    # ------------------------------------------------------------------ pages
    def _page(self, route: str) -> QWidget:
        page = self._pages.get(route)
        if page is not None:
            return page
        page = self._create_page(route)
        self._pages[route] = page
        self.stack.addWidget(page)
        return page

    def _create_page(self, route: str) -> QWidget:
        from .pages.albums import AlbumPage, AlbumsPage
        from .pages.artists import ArtistPage, ArtistsPage
        from .pages.collection import FavoritesPage, PlaylistPage, RecentPage
        from .pages.home import HomePage
        from .pages.downloads import DownloadsPage
        from .pages.search import SearchPage
        from .pages.songs import SongsPage

        factories: dict[str, Callable[[], QWidget]] = {
            "home": HomePage,
            "songs": SongsPage,
            "albums": AlbumsPage,
            "album": AlbumPage,
            "artists": ArtistsPage,
            "artist": ArtistPage,
            "favorites": FavoritesPage,
            "recent": RecentPage,
            "playlist": PlaylistPage,
            "search": SearchPage,
            "downloads": DownloadsPage,
        }
        if route == "lyrics":
            from .pages.lyrics import LyricsPage

            return LyricsPage()
        if route == "settings":
            from .pages.settings import SettingsPage

            return SettingsPage()
        factory = factories.get(route)
        if factory is None:
            return QWidget()
        return factory()

    def navigate(self, route: str, payload: object = None, *, push: bool = True) -> None:
        if ":" in route:
            head, _, tail = route.partition(":")
            route, payload = head, tail
        if route == "playlist" and isinstance(payload, str) and payload.isdigit():
            payload = int(payload)
        try:
            page = self._page(route)
        except Exception as exc:  # noqa: BLE001
            log_exception(f"无法打开页面 {route}", exc)
            self.toast("页面加载失败，请查看日志", "error")
            return
        self.stack.setCurrentWidget(page)
        self._current_route = route
        if payload is not None and hasattr(page, "set_payload"):
            try:
                page.set_payload(payload)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                log_exception("设置页面参数失败", exc)
        if hasattr(page, "on_show"):
            try:
                page.on_show(payload)
            except Exception as exc:  # noqa: BLE001
                log_exception("页面初始化失败", exc)
        self.sidebar.set_route(route if route != "playlist" else f"playlist:{payload}")
        title = getattr(page, "title", "") or ROUTE_TITLES.get(route, route)
        if route == "playlist":
            playlist = ctx().library.playlist(payload) if isinstance(payload, int) else None
            title = playlist.name if playlist is not None else "歌单"
        self.titlebar.set_title(title)
        self.route_changed.emit(route)
        if push:
            self._push_history(route, payload)
        if self.queue_panel.isVisible():
            self.queue_panel.open_panel()

    @property
    def current_route(self) -> str:
        """当前页面路由（供测试与外部诊断使用）。"""
        return self._current_route

    def _push_history(self, route: str, payload: object) -> None:
        if self._history_index >= 0 and self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]
        entry = (route, payload)
        if self._history and self._history[-1] == entry:
            return
        self._history.append(entry)
        if len(self._history) > 60:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self._sync_history_buttons()

    def _sync_history_buttons(self) -> None:
        self.titlebar.set_history(self._history_index > 0, self._history_index < len(self._history) - 1)

    def go_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        route, payload = self._history[self._history_index]
        self.navigate(route, payload, push=False)
        self._sync_history_buttons()

    def go_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        route, payload = self._history[self._history_index]
        self.navigate(route, payload, push=False)
        self._sync_history_buttons()

    # ----------------------------------------------------------------- player
    def _wire_downloads(self) -> None:
        """下载完成 / 失败在主窗口用 toast 反馈（进度过多，不逐条提示）。"""
        self._download_failures: set[str] = set()
        downloads = getattr(ctx(), "downloads", None)
        if downloads is None:
            return
        downloads.job_finished.connect(self._on_download_finished)
        downloads.job_updated.connect(self._on_download_updated)

    def _on_download_finished(self, job) -> None:
        self.toast(f"已下载：{job.title}")

    def _on_download_updated(self, job) -> None:
        if getattr(job, "state", "") != "failed":
            return
        if job.id in self._download_failures:
            return
        self._download_failures.add(job.id)
        self.toast(f"下载失败：{job.title}（{job.error or '未知原因'}）", "error")

    def _wire_player(self) -> None:
        player = ctx().player
        player.status_message.connect(lambda text: self.toast(text, "info"))
        player.error_message.connect(lambda text: self.toast(text, "error"))
        player.track_changed.connect(self._on_track_changed)
        player.state_changed.connect(lambda _s: self._refresh_tray_tooltip())
        player.sources_changed.connect(lambda _s: self._refresh_sidebar())

    def _on_track_changed(self, track) -> None:
        if track is None:
            self.titlebar.set_title(self.titlebar_title)
            return
        self.titlebar.set_title(f"{track.title} — {track.artist}" if track.artist else track.title)
        for page in self._pages.values():
            if hasattr(page, "current_track_changed"):
                try:
                    page.current_track_changed(track)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    continue
        self._refresh_tray_tooltip()

    @property
    def titlebar_title(self) -> str:
        page = self.stack.currentWidget()
        return getattr(page, "title", "HushPlayer") or "HushPlayer"

    def _go_to_current_album(self) -> None:
        track = ctx().player.current_track
        if track is None:
            return
        if track.album_id:
            self.navigate("album", track.album_id)
        else:
            self.navigate("lyrics")

    def toggle_queue(self) -> None:
        self.queue_panel.toggle()

    def open_immersive(self) -> None:
        try:
            from .immersive import ImmersiveWindow

            window = getattr(self, "_immersive", None)
            if window is None:
                window = ImmersiveWindow()
                window.closed.connect(self._on_immersive_closed)
                self._immersive = window
            ctx().immersive = window
            window.open_immersive()
        except Exception as exc:  # noqa: BLE001
            log_exception("打开沉浸式播放器失败", exc)
            self.toast("沉浸式播放器暂时不可用", "error")

    def _on_immersive_closed(self) -> None:
        ctx().immersive = None

    # ---------------------------------------------------------------- library
    def _wire_library(self) -> None:
        library = ctx().library
        library.playlists_changed.connect(self._refresh_sidebar)
        library.favorites_changed.connect(self._refresh_sidebar)
        library.library_changed.connect(self._refresh_sidebar)
        self._refresh_sidebar()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._refresh_sidebar)
        self._timer.start()

    def _refresh_sidebar(self, *_args) -> None:
        library = ctx().library
        try:
            self.sidebar.set_playlists(library.playlists_all())
            stats = library.stats
            self.sidebar.set_counts(
                {
                    "songs": str(stats.track_count) if stats.track_count else "",
                    "albums": str(stats.album_count) if stats.album_count else "",
                    "favorites": str(stats.favorite_count) if stats.favorite_count else "",
                }
            )
            downloads = ctx().downloads
            if downloads is not None:
                active = len(downloads.active())
                self.sidebar.set_count("downloads", str(active) if active else "")
        except Exception as exc:  # noqa: BLE001
            log_exception("刷新侧边栏失败", exc)

    def _toggle_sidebar(self) -> None:
        collapsed = not self.sidebar.collapsed
        self.sidebar.set_collapsed(collapsed)
        ctx().settings.set("appearance.sidebar_visible", not collapsed)

    def _on_collapsed(self, collapsed: bool) -> None:
        ctx().settings.set("appearance.sidebar_visible", not collapsed)

    def _playlist_menu(self, playlist_id: int, position: QPoint) -> None:
        playlist = ctx().library.playlist(playlist_id)
        if playlist is None:
            return
        menu = playlist_menu(self, playlist_id, playlist.name, position)
        menu.exec(position)
        self._refresh_sidebar()

    def _create_playlist(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "新建歌单", "歌单名称", text="新建歌单")
        if not ok or not name.strip():
            return
        playlist_id = ctx().library.create_playlist(name.strip())
        self._refresh_sidebar()
        self.navigate(f"playlist:{playlist_id}")

    # --------------------------------------------------------------- shortcuts
    def _install_shortcuts(self) -> None:
        def add(sequence: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(handler)

        add("Space", self._toggle_play)
        add("Ctrl+F", self._focus_search)
        add("Ctrl+Left", lambda: ctx().player.skip_by(-5))
        add("Ctrl+Right", lambda: ctx().player.skip_by(5))
        add("Ctrl+Up", lambda: self._bump_volume(0.05))
        add("Ctrl+Down", lambda: self._bump_volume(-0.05))
        add("Ctrl+M", lambda: ctx().player.toggle_mute())
        add("Ctrl+L", lambda: self.navigate("lyrics"))
        add("Ctrl+Shift+L", self.toggle_desktop_lyrics)
        add("F11", self.open_immersive)
        add("Ctrl+Q", self.close_window)
        add("Alt+1", lambda: self.navigate("home"))
        add("Alt+2", lambda: self.navigate("songs"))
        add("Esc", self._escape)
        for key in (Qt.Key_MediaPlay, Qt.Key_MediaPause, Qt.Key_MediaTogglePlayPause):
            add(QKeySequence(key).toString(), self._toggle_play)
        add(QKeySequence(Qt.Key_MediaNext).toString(), lambda: ctx().player.next())
        add(QKeySequence(Qt.Key_MediaPrevious).toString(), lambda: ctx().player.previous())
        add(QKeySequence(Qt.Key_MediaStop).toString(), lambda: ctx().player.stop())

    def _toggle_play(self) -> None:
        widget = QApplication.focusWidget()
        if isinstance(widget, QLineEdit):
            return
        ctx().player.toggle()

    def _bump_volume(self, delta: float) -> None:
        player = ctx().player
        player.set_volume(max(0.0, min(1.0, player.volume + delta)))

    def _focus_search(self) -> None:
        self.navigate("search")
        page = self._pages.get("search")
        if page is not None and hasattr(page, "field"):
            page.field.focus()  # type: ignore[attr-defined]

    def _minimize_to_taskbar(self, *, reason: str | None = None) -> None:
        """Keep the app reachable when the tray cannot be used."""
        self.showMinimized()
        if reason:
            self.toast(reason, "warning")

    def _background_without_tray(self) -> None:
        """No usable tray icon: minimise to the taskbar instead of vanishing."""
        self._minimize_to_taskbar(
            reason="系统未接受托盘图标，已最小化到任务栏（并未退出）"
        )

    def show_from_background(self) -> None:
        """Bring the player back after it was hidden to tray."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _escape(self) -> None:
        if self.queue_panel.isVisible():
            self.queue_panel.close_panel()

    # ------------------------------------------------------------------- tray
    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("系统托盘不可用，关闭/最小化将保持窗口可见")
            return
        self._tray = QSystemTrayIcon(self)
        icon = brand.tray_icon()
        if icon.isNull():
            from ..core import icons

            icon = icons.icon("headphones", "#C95770")
        icon = QIcon(icon.pixmap(32)) if icon.isNull() else icon
        self._tray.setIcon(icon)
        self._tray_null_icon = icon.isNull()
        self._tray.setToolTip("HushPlayer")
        menu = QMenu()
        show_action = QAction("显示 HushPlayer", self)
        show_action.triggered.connect(self._restore_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        play_action = QAction("播放 / 暂停", self)
        play_action.triggered.connect(self._toggle_play)
        menu.addAction(play_action)
        next_action = QAction("下一首", self)
        next_action.triggered.connect(lambda: ctx().player.next())
        menu.addAction(next_action)
        prev_action = QAction("上一首", self)
        prev_action.triggered.connect(lambda: ctx().player.previous())
        menu.addAction(prev_action)
        menu.addSeparator()
        lyrics_action = QAction("桌面歌词", self)
        lyrics_action.triggered.connect(self.toggle_desktop_lyrics)
        menu.addAction(lyrics_action)
        immersive_action = QAction("沉浸模式", self)
        immersive_action.triggered.connect(self.open_immersive)
        menu.addAction(immersive_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        log.info(
            "托盘图标：null=%s visible=%s available=%s sizes=%s",
            getattr(self, "_tray_null_icon", True),
            self._tray.isVisible(),
            QSystemTrayIcon.isSystemTrayAvailable(),
            [s.width() for s in icon.availableSizes()],
        )
        # Explorer occasionally ignores the first registration; re-assert once,
        # then verify that the shell really owns an icon for us.
        # Pessimistic until proven: a failed Shell_NotifyIcon leaves no icon at
        # all, and hiding the window then makes the app look crashed/lost.
        self._tray_ok = False
        QTimer.singleShot(1200, self._reassert_tray_icon)
        QTimer.singleShot(2600, self._verify_tray_registration)

    def toggle_desktop_lyrics(self) -> None:
        from .desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            self.toast("桌面歌词暂时不可用", "warning")
            return
        window.toggle()
        if window.isVisible():
            self.toast("桌面歌词已开启", "success")

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _tray_available(self) -> bool:
        """Whether hiding to the tray keeps the app reachable.

        Uses the real registration result (see ``tray_probe``); before the probe
        has run we optimistically assume the tray works so early minimise
        requests behave like the user expects.
        """
        if getattr(self, "_tray", None) is None:
            return False
        return bool(getattr(self, "_tray_ok", True))

    def _verify_tray_registration(self) -> None:
        tray = getattr(self, "_tray", None)
        if tray is None:
            return
        from ..services.tray_probe import describe, probe_registration

        try:
            hwnd = int(self.winId())
        except Exception:
            hwnd = 0
        ok, error = probe_registration(hwnd, brand.tray_icon_path())
        self._tray_ok = bool(ok and QSystemTrayIcon.isSystemTrayAvailable())
        if not ok:
            message = describe(error)
            log.warning("托盘图标注册失败：%s", message)
            if error == 5:
                # Do not claim success (and do not lie to the user): tell them how
                # to fix it, then keep the window reachable through the taskbar.
                self._tray_ok = False
                try:
                    self.toast("托盘图标不可用：请把程序移到桌面等普通目录运行", "warning")
                except Exception:
                    pass
        elif not self._tray_ok:
            log.warning("系统托盘不可用；关闭/最小化将改为最小化到任务栏")
        else:
            log.info("托盘图标注册成功（系统已接受）")
        self._restyle_tray_menu()

    def _restyle_tray_menu(self) -> None:
        return

    def _reassert_tray_icon(self) -> None:
        tray = getattr(self, "_tray", None)
        if tray is None or not getattr(self, "_tray_ok", True):
            return
        tray.setIcon(brand.tray_icon())
        tray.show()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _refresh_tray_tooltip(self) -> None:
        if self._tray is None:
            return
        track = ctx().player.current_track
        if track is None:
            self._tray.setToolTip("HushPlayer")
        else:
            self._tray.setToolTip(f"HushPlayer\n{track.title} — {track.artist}")

    def _quit(self) -> None:
        self.closing.emit()
        QApplication.instance().quit()

    # ------------------------------------------------------------------ misc
    def toast(self, text: str, kind: str = "info") -> None:
        if self._toasts is not None:
            self._toasts.show_message(text, kind)

    def refresh_theme(self) -> None:
        palette = theme().palette
        self._page_background.setStyleSheet(
            f"#HushPageBackground {{ background: {palette.window}; }}"
        )
        self.sidebar.refresh_theme()
        self.playerbar.refresh_theme()
        self.queue_panel.refresh_theme()
        for page in self._pages.values():
            if hasattr(page, "refresh_theme"):
                try:
                    page.refresh_theme()  # type: ignore[attr-defined]
                except Exception as exc:  # noqa: BLE001
                    log_exception("刷新页面主题失败", exc)
        self.titlebar.update()
        self.titlebar.set_theme_mode(theme().mode)
        self.update()

    def toggle_theme_mode(self) -> None:
        """Switch between light and dark from the title bar (sun / moon)."""
        target = "light" if theme().mode == "dark" else "dark"
        settings = ctx().settings
        settings.set("appearance.theme", target)
        toast = getattr(self, "_toasts", None)
        # Burst-clicking the toggle should not stack a pile of identical toasts.
        now = time.monotonic()
        if toast is not None and now >= getattr(self, "_theme_toast_at", 0.0) + 1.2:
            self._theme_toast_at = now
            self.toast("已切换到浅色模式" if target == "light" else "已切换到深色模式")

    def apply_theme(self, mode: str = "system") -> None:
        actual = apply_theme_to_app(QApplication.instance(), preference=mode)
        log.info("主题已切换为 %s（实际 %s）", mode, actual)
        self.refresh_theme()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.queue_panel.isVisible():
            self.queue_panel.setGeometry(
                self.content.width() - self.queue_panel.width(),
                0,
                self.queue_panel.width(),
                max(120, self.content.height() - self.playerbar.height()),
            )
        self._toasts.setGeometry(0, 0, self.container.width(), self.container.height())

    def _ask_close_action(self) -> str:
        """Ask whether closing quits or hides to the tray. Returns quit/tray/cancel."""
        from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("关闭 HushPlayer")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)
        title = QLabel("要退出 HushPlayer，还是最小化到系统托盘继续播放？")
        title.setWordWrap(True)
        title.setFont(theme().font(10.4, 600))
        layout.addWidget(title)
        remember = QCheckBox("记住我的选择（可在 设置 → 常规 中修改）")
        layout.addWidget(remember)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = TextButton("取消", size=30)
        tray_ok = self._tray_available()
        hide = TextButton("最小化到托盘" if tray_ok else "最小化到任务栏", size=30)
        quit_button = TextButton("直接退出", size=30, accent=True)
        buttons.addWidget(cancel)
        buttons.addWidget(hide)
        buttons.addWidget(quit_button)
        layout.addLayout(buttons)

        choice = {"value": "cancel"}
        quit_button.clicked.connect(lambda: (choice.update(value="quit"), dialog.accept()))
        hide_target = "tray" if tray_ok else "minimize"
        hide.clicked.connect(
            lambda: (choice.update(value=hide_target), dialog.accept())
        )
        cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.Accepted:
            return "cancel"
        if remember.isChecked() and choice["value"] in ("quit", "tray", "minimize"):
            ctx().settings.set("general.close_action", choice["value"])
        return choice["value"]

    def closeEvent(self, event) -> None:  # noqa: N802
        if getattr(self, "_force_quit", False):
            super().closeEvent(event)
            return
        self._save_geometry()
        action = str(ctx().settings.get("general.close_action", "ask"))
        if os.environ.get("HUSHPLAYER_NO_CLOSE_PROMPT") == "1" or "pytest" in sys.modules:
            # Automated tests and scripted runs must never block on a modal.
            action = "quit"
        if getattr(self, "_close_prompt_open", False):
            event.ignore()
            return
        if time.monotonic() < getattr(self, "_close_suppress_until", 0.0):
            # Windows delivers a second WM_CLOSE when the dialog itself closes;
            # asking twice looks like a bug.
            event.ignore()
            return
        if action == "ask":
            self._close_prompt_open = True
            try:
                action = self._ask_close_action()
            finally:
                self._close_prompt_open = False
                self._close_suppress_until = time.monotonic() + 1.2
            if action == "cancel":
                event.ignore()
                return
        if action == "minimize" or (action == "tray" and not self._tray_available()):
            event.ignore()
            self._background_without_tray()
            return
        prefer_tray = action == "tray" and self._tray_available()
        if prefer_tray:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "HushPlayer",
                "已最小化到系统托盘，双击图标可恢复。",
                QSystemTrayIcon.MessageIcon.Information,
                2600,
            )
            return
        self._force_quit = True
        self.closing.emit()
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)
        QApplication.instance().quit()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange:
            try:
                minimize_to_tray = bool(
                    ctx().settings.get("general.minimize_to_tray", False)
                )
                tray_ready = self._tray_available()
                if minimize_to_tray and self.isMinimized() and tray_ready:
                    QTimer.singleShot(0, self._hide_to_tray)
            except Exception:  # noqa: BLE001
                log.debug("处理窗口状态变化失败", exc_info=True)
        super().changeEvent(event)

    def _hide_to_tray(self) -> None:
        # Re-check at the moment of hiding: Explorer can revoke an icon later
        # (shell restart, security tooling), and a probe is a few milliseconds.
        if self._tray is not None and QSystemTrayIcon.isSystemTrayAvailable():
            from ..services.tray_probe import probe_registration

            try:
                ok, _error = probe_registration(int(self.winId()), brand.tray_icon_path())
            except Exception:  # noqa: BLE001
                ok = False
            self._tray_ok = bool(ok)
        if not self._tray_available():
            self._background_without_tray()
            return
        if not bool(ctx().settings.get("general.tray_hint_shown", False)):
            # First time: explain where the icon went, otherwise the window can
            # look like it vanished (Windows 11 keeps new icons in the overflow).
            QMessageBox.information(
                self,
                "已最小化到系统托盘",
                "HushPlayer 仍在后台播放。\n\n"
                "Windows 11 默认把新图标放进任务栏的隐藏区：点击任务栏右下角的"
                "「^」（或按 Win+B 后右方向键）即可看到 HushPlayer。\n"
                "你可以把它拖到常显区域，或用「设置 → 常规 → 关闭窗口时」改成直接退出。",
            )
            ctx().settings.set("general.tray_hint_shown", True)
            ctx().settings.save()
        self.hide()
        if self._tray is not None:
            self._tray.showMessage(
                "HushPlayer",
                "仍在后台播放，双击托盘图标可恢复窗口。",
                QSystemTrayIcon.MessageIcon.Information,
                2200,
            )

    # ------------------------------------------------------------- geometry
    def _restore_geometry(self) -> None:
        settings = ctx().settings
        stored = settings.get("general.window", {}) or {}
        width = int(stored.get("w", 0) or 0)
        height = int(stored.get("h", 0) or 0)
        x = int(stored.get("x", -1) or -1)
        y = int(stored.get("y", -1) or -1)
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 820)
        too_big = width >= available.width() - 2 and height >= available.height() - 2
        if width >= 940 and height >= 620 and not too_big:
            rect = ensure_on_screen(self, QRect(x, y, width, height))
            self.setGeometry(rect)
        else:
            center_on_screen(self, screen_ratio=0.78)
        self._normal_geometry = QRect(self.geometry())
        if stored.get("maximized"):
            QTimer.singleShot(0, self._start_maximized)

    def _start_maximized(self) -> None:
        self.showMaximized()
        self._maximized = True
        self._sync_maximized_ui()

    def _save_geometry(self) -> None:
        settings = ctx().settings
        maximized = bool(self.isMaximized())
        geometry = self.normal_geometry() if maximized else QRect(self.geometry())
        if geometry.width() < 480 or geometry.height() < 360:
            geometry = QRect(self._normal_geometry)
        settings.set(
            "general.window",
            {
                "x": geometry.x(),
                "y": geometry.y(),
                "w": geometry.width(),
                "h": geometry.height(),
                "maximized": maximized,
            },
        )
        settings.flush()

