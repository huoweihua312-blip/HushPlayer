"""Application entry point: wires services together and shows the main window."""

from __future__ import annotations

import os
import sys
import time
import traceback

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .core import icons
from .core.logging_setup import get_logger, log_exception, recent_log_text, setup_logging
from .core import brand
from .core.paths import data_dir, ensure_dirs, is_frozen
from .core.settings import settings
from .core.theme import apply_theme_to_app, theme
from .version import APP_NAME, APP_ID, VERSION
from .ui.context import AppContext, ctx, set_context

log = get_logger(__name__)


class HushApp(QObject):
    """Owns every long-lived service and reacts to settings changes."""

    ready = Signal()

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.window = None
        self._resolved_mode: str | None = None
        self._build_services()
        self._connect_settings()
        self._watch_client()

    # ---------------------------------------------------------------- services
    def _build_services(self) -> None:
        from .audio.clock import PlaybackClock
        from .audio.controller import PlayerController
        from .audio.engine import PlaybackEngine
        from .library.artwork import ArtworkStore
        from .library.scanner import Scanner  # noqa: F401  (import check)
        from .lyrics.service import LyricsService
        from .online.client import OnlineSourceClient, runtime_available
        from .online.proxy import AudioProxy
        from .services.cache import CacheService
        from .services.downloads import DownloadService
        from .services.library import LibraryService
        from .services.state import PlaybackKeeper
        from .store.db import Database

        self.settings = settings()
        self.settings.load()
        self.db = Database()
        self.library = LibraryService(self.db)
        self.artwork = ArtworkStore()

        self.proxy = AudioProxy()
        self.client = OnlineSourceClient(self)
        self.player = PlayerController(self, client=self.client, proxy=self.proxy)
        self.lyrics = LyricsService(
            self.library.tracks, self.library.bindings, self.library.meta, self.client, self
        )
        self.cache = CacheService(self.proxy, self.library.covers.store, self)
        self.clock = PlaybackClock(self)
        self.player.position_changed.connect(self.clock.set_position)
        self.player.duration_changed.connect(self.clock.set_duration)
        self.player.state_changed.connect(
            lambda state: self.clock.set_playing(state == "playing")
        )
        self.keeper = PlaybackKeeper(self.player, self.library.tracks, self)
        self.downloads = DownloadService(self.client, self)
        from .services.updater import UpdateService

        self.updater = UpdateService(self)

        self.runtime_ok = runtime_available()
        log.info("在线音源运行时可用=%s", self.runtime_ok)

        context = AppContext(
            library=self.library,
            player=self.player,
            lyrics=self.lyrics,
            cache=self.cache,
            covers=self.library.covers,
            client=self.client,
            proxy=self.proxy,
            keeper=self.keeper,
            clock=self.clock,
            downloads=self.downloads,
            updater=self.updater,
            settings=self.settings,
            window=None,
            desktop_lyrics=None,
            immersive=None,
        )
        set_context(context)

    # ---------------------------------------------------------------- settings
    def _connect_settings(self) -> None:
        self.settings.changed.connect(self._on_setting_changed)

    def _arm_sleep_timer(self, minutes: int) -> None:
        """Pause playback after N minutes; 0 disables the timer."""
        timer = getattr(self, "_sleep_timer", None)
        if timer is None:
            from PySide6.QtCore import QTimer

            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_sleep_timer)
            self._sleep_timer = timer
        timer.stop()
        if minutes <= 0:
            return
        timer.start(int(minutes * 60_000))
        log.info("睡眠定时：%d 分钟后暂停播放", minutes)
        if getattr(self, "window", None) is not None:
            self.window.toast(f"睡眠定时已设为 {minutes} 分钟")

    def _on_sleep_timer(self) -> None:
        try:
            self.player.pause()
        except Exception:  # noqa: BLE001
            log.exception("睡眠定时暂停失败")
        self.settings.set("playback.sleep_timer_minutes", 0)
        if getattr(self, "window", None) is not None:
            self.window.toast("睡眠定时已到，已暂停播放")

    def _on_setting_changed(self, key: str, value: object) -> None:
        log.info("设置变更 %s = %r", key, value)
        if key.startswith("appearance."):
            self.apply_theme()
        elif key == "playback.volume":
            try:
                self.player.set_volume(float(value))
            except (TypeError, ValueError):
                pass
        elif key == "playback.sleep_timer_minutes":
            self._arm_sleep_timer(int(value or 0))
        elif key == "playback.shuffle":
            self.player.set_shuffle(bool(value))
        elif key == "playback.repeat":
            self.player.set_repeat(str(value))
        elif key == "playback.quality":
            self.player.configure(quality=str(value))
        elif key == "playback.replaygain":
            self.player.configure(replaygain=str(value))
        elif key.startswith("general."):
            if key == "general.launch_at_startup":
                from .services.startup import set_enabled

                ok, detail = set_enabled(bool(value))
                if not ok and self.window is not None:
                    self.window.toast(f"设置开机自启失败：{detail}", "error")
        elif key.startswith("cache."):
            if key == "cache.max_mb":
                self.cache.prune(int(value or 0))
        window = self.window
        if window is not None and hasattr(window, "on_setting_changed"):
            try:
                window.on_setting_changed(key, value)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                log_exception("窗口响应设置失败", exc)

    def _ui_type_scale(self) -> float:
        import os

        from .core import display

        override = os.environ.get("HUSHPLAYER_TYPE_SCALE")
        if override:
            try:
                return max(1.0, float(override))
            except ValueError:
                pass
        # An explicit 界面缩放 replaces the automatic type scale (it is applied
        # here rather than via QT_SCALE_FACTOR so glyphs stay on whole pixels).
        try:
            from .core.display import scale_preference, resolve_scale
            if scale_preference() != "auto":
                return max(0.8, min(2.0, resolve_scale()))
        except Exception:  # noqa: BLE001
            pass
        try:
            width, height = display.physical_screen_size()
        except Exception:  # noqa: BLE001
            return 1.0
        dpr = 1.0
        try:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                dpr = float(screen.devicePixelRatio() or 1.0)
                if height <= 0:
                    height = int(round(screen.size().height() * dpr))
                if width <= 0:
                    width = int(round(screen.size().width() * dpr))
        except Exception:  # noqa: BLE001
            pass
        return display.recommended_type_scale(width, height, dpr)

    def _end_theme_transition(self) -> None:
        """Retire any running reveal so a new one starts from a clean frame."""
        overlay = getattr(self, "_theme_reveal", None)
        self._theme_reveal = None
        if overlay is None:
            return
        try:
            overlay.finish()
        except Exception:  # noqa: BLE001
            pass
        if self.window is not None:
            self.app.processEvents()

    def apply_theme(self, *, animate: bool = True) -> None:
        preference = str(self.settings.get("appearance.theme", "system"))
        accent = str(self.settings.get("appearance.accent", "#C95770"))
        reduce_motion = bool(self.settings.get("appearance.reduce_motion", False))
        font_scale = float(self.settings.get("appearance.font_scale", 1.0) or 1.0)
        density = str(self.settings.get("appearance.density", "comfortable"))
        signature = (preference, accent, reduce_motion, font_scale, density)
        if signature == getattr(self, "_theme_signature", None):
            return
        window = self.window
        animation_mode = str(self.settings.get("appearance.theme_animation_mode", "reveal"))
        animate_theme = animation_mode in ("reveal", "sunrise")
        # Rapid toggling: retire the running wipe first, and skip animating the
        # follow-up switches so overlays can never pile up (a frozen leftover
        # also ends up baked into the next snapshot, which looked "stuck").
        self._end_theme_transition()
        now = time.monotonic()
        if now < getattr(self, "_theme_cooldown_until", 0.0):
            animate = False
        overlay = None
        snapshot = None
        previous_mode = self._resolved_mode
        if (
            animate
            and animate_theme
            and not reduce_motion
            and window is not None
            and window.isVisible()
            and not window.isMinimized()
        ):
            try:
                snapshot = window.grab()
            except Exception:  # noqa: BLE001
                snapshot = None
            if snapshot is not None and not snapshot.isNull():
                from .ui.widgets.transition import SunMoonReveal, ThemeReveal

                host = getattr(window, "container", None) or window
                origin = self._theme_origin(window, host)
                to_dark = previous_mode == "light"
                if animation_mode == "sunrise":
                    overlay = SunMoonReveal(
                        host,
                        snapshot,
                        snapshot,
                        origin,
                        to_dark=to_dark,
                        pop_ms=float(self.settings.get("appearance.theme_anim_pop_ms", 420.0) or 420.0),
                        hold_ms=float(self.settings.get("appearance.theme_anim_hold_ms", 260.0) or 0.0),
                        icon_scale=float(self.settings.get("appearance.theme_anim_icon_scale", 1.0) or 1.0),
                    )
                else:
                    overlay = ThemeReveal(
                        host,
                        snapshot,
                        snapshot,
                        origin,
                        to_dark=to_dark,
                    )
                # Freeze the old frame *before* the palette changes; otherwise a
                # frame of the new theme can be presented under the overlay.
                overlay.freeze()
                self._theme_reveal = overlay
                overlay.destroyed.connect(lambda *_: setattr(self, "_theme_reveal", None))
                self._theme_cooldown_until = now + overlay.animation_ms() / 1000.0 + 0.15
                self.app.processEvents()

        self._theme_signature = signature
        actual = apply_theme_to_app(
            self.app,
            preference=preference,
            accent=accent,
            reduce_motion=reduce_motion,
            font_scale=font_scale,
            density=density,
            ui_scale=self._ui_type_scale(),
        )
        log.info("应用主题：%s → %s（字号缩放 ×%.2f）", preference, actual, theme().type_scale)
        self.app.setStyleSheet(theme().qss())
        if window is not None:
            window.refresh_theme()
        if overlay is not None:
            if previous_mode is not None and previous_mode != actual:
                overlay.hide()
                try:
                    latest = window.grab()
                except Exception:  # noqa: BLE001
                    latest = None
                overlay.resume_with(latest if latest is not None else snapshot)
            else:
                from .ui.widgets.transition import FadeOverlay

                overlay.close()
                if snapshot is not None:
                    host = getattr(window, "container", None) or window
                    FadeOverlay(host, snapshot).start()
        self._resolved_mode = actual

    def _theme_origin(self, window, host):
        from PySide6.QtCore import QPointF

        button = getattr(getattr(window, "titlebar", None), "theme_button", None)
        if button is not None:
            return QPointF(button.mapTo(host, button.rect().center()))
        return QPointF(host.width() / 2.0, 0.0)

    # ------------------------------------------------------------------- start
    def start(self) -> None:
        from .ui.main_window import MainWindow

        self.apply_theme()
        self._resolved_mode = theme().mode
        # Older builds persisted "quit" as the default without ever asking, so
        # owners of such profiles never saw the close dialog. Surface it once.
        if not bool(self.settings.get("general.close_prompt_migrated", False)):
            if str(self.settings.get("general.close_action", "ask")) == "quit":
                self.settings.set("general.close_action", "ask")
            self.settings.set("general.close_prompt_migrated", True)
        self.window = MainWindow()
        context = ctx()
        if context is not None:
            context.window = self.window
        # Windows shell integration needs the real HWND, so it is created here
        # rather than in _build_services().
        from .services.integration import MediaIntegration

        self.integration = MediaIntegration(self.player, self.settings, self)
        self.integration.attach_window(self.window)
        if context is not None:
            context.integration = self.integration
        self._configure_player()
        self._restore_session()

        self.app.setWindowIcon(brand.app_icon())
        self.window.show()
        self._maybe_rescan()
        self._maybe_check_updates()
        self.ready.emit()
        log.info("%s %s 已启动，数据目录 %s", APP_NAME, VERSION, data_dir())

    def _maybe_check_updates(self) -> None:
        """启动后延迟检查更新：只提示，不下载、不安装。"""
        from .services.updater import check_on_start_enabled

        if not check_on_start_enabled():
            return
        QTimer.singleShot(6000, self._run_update_check)

    def _run_update_check(self) -> None:
        updater = getattr(self, "updater", None)
        if updater is None:
            return

        def on_checked(info) -> None:
            if info.available and self.window is not None:
                self.window.toast(f"发现新版本 {info.version}，可在设置中查看", "info")

        updater.checked.connect(on_checked)
        updater.check_async()

    def bring_to_front(self) -> None:
        """第二个实例启动时，把已有窗口恢复并置前。"""
        window = self.window
        if window is None:
            return
        try:
            if window.isMinimized():
                window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
            window.show()
            window.raise_()
            window.activateWindow()
            window.toast("HushPlayer 已在运行，已切换到当前窗口", "info")
        except Exception as exc:  # noqa: BLE001
            log_exception("激活窗口失败", exc)

    def _configure_player(self) -> None:
        playback = {
            "volume": float(self.settings.get("playback.volume", 0.72)),
            "quality": str(self.settings.get("playback.quality", "standard")),
            "online_fallback": bool(self.settings.get("online.cross_source_fallback", True)),
            "shuffle": bool(self.settings.get("playback.shuffle", False)),
            "repeat": str(self.settings.get("playback.repeat", "off")),
            "replaygain": str(self.settings.get("playback.replaygain", "off")),
        }
        self.player.configure(**playback)

    def _restore_session(self) -> None:
        try:
            position = self.keeper.restore()
        except Exception as exc:  # noqa: BLE001
            log_exception("恢复播放队列失败", exc)
            return
        if position or self.player.queue.count:
            try:
                self.player.restore_current(position)
            except Exception as exc:  # noqa: BLE001
                log_exception("恢复当前歌曲失败", exc)

    def _maybe_rescan(self) -> None:
        folders = [str(p) for p in (self.settings.get("library.folders", []) or []) if p]
        if not folders:
            return
        auto = bool(self.settings.get("library.auto_scan_on_start", True))
        if not auto:
            return
        QTimer.singleShot(
            1200,
            lambda: self.library.scan(folders) if not getattr(self.library, "scanning", False) else None,
        )

    def _watch_client(self) -> None:
        self.client.failure.connect(self._on_client_failure)
        self.client.ready.connect(lambda info: log.info("在线音源运行时就绪：%s", info))
        if self.runtime_ok:
            QTimer.singleShot(400, self.client.ensure_started)

    def _on_client_failure(self, message: str) -> None:
        log.warning("在线音源不可用：%s", message)
        window = self.window
        if window is not None:
            window.toast("在线音源暂不可用，本地播放不受影响", "warning")

    # -------------------------------------------------------------------- stop
    def shutdown(self) -> None:
        log.info("正在退出 HushPlayer")
        try:
            self.keeper.flush()
        except Exception:  # noqa: BLE001
            pass
        for name in (
            "integration",
            "player",
            "lyrics",
            "downloads",
            "updater",
            "library",
            "cache",
            "client",
            "proxy",
        ):
            service = getattr(self, name, None)
            if service is None:
                continue
            method = getattr(service, "shutdown", None) or getattr(service, "close", None)
            if method is None:
                continue
            try:
                method()
            except Exception as exc:  # noqa: BLE001
                log_exception(f"关闭 {name} 失败", exc)
        try:
            self.db.close_current_thread()
        except Exception:  # noqa: BLE001
            pass
        self.settings.flush()


def _install_excepthook(app: QApplication) -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("未捕获异常\n%s", text)
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle("HushPlayer 遇到了问题")
            box.setText("程序遇到了一个未处理的错误，已记录到日志。")
            box.setInformativeText(
                f"{exc_type.__name__}: {exc_value}\n\n日志：{recent_log_text(1200)[-500:]}"
            )
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def _wait_for_pid_exit(pid: int, timeout_s: float = 6.0, poll_s: float = 0.1) -> float:
    """Poll until ``pid`` is gone; returns the seconds spent waiting.

    Uses ``GetExitCodeProcess`` instead of a wait handle: the old process may be
    a different integrity level, where ``OpenProcess(SYNCHRONIZE)`` is denied,
    and a lingering mutex holder (another HushPlayer instance) must not be
    mistaken for our parent.
    """
    import time

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # pragma: no cover - non Windows
        return 0.0
    started = time.monotonic()
    deadline = started + max(0.5, timeout_s)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    still_active = 259
    while time.monotonic() < deadline:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return time.monotonic() - started  # already gone
        code = wintypes.DWORD(0)
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        if not ok or code.value != still_active:
            return time.monotonic() - started
        time.sleep(poll_s)
    return time.monotonic() - started


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    # A restarted instance passes the old process id; block until it is gone so
    # the named mutex is free and we don't bounce off our own single-instance guard.
    wait_pid = 0
    if "--wait-pid" in argv:
        index = argv.index("--wait-pid")
        try:
            wait_pid = int(argv[index + 1])
        except (IndexError, ValueError):
            wait_pid = 0
        del argv[index:index + 2]
    ensure_dirs()
    default_console = "0" if is_frozen() else "1"
    setup_logging(console=os.environ.get("HUSH_CONSOLE", default_console) != "0")
    log.info("启动 HushPlayer %s", VERSION)

    # BUG-05: scale Qt's logical pixels for high-resolution displays. Must run
    # before QApplication exists, otherwise the factor is ignored.
    from .core.display import apply_scale_environment, scale_text

    if wait_pid:
        waited = _wait_for_pid_exit(wait_pid)
        log.info("重启：旧进程 %s 已退出（等待 %.2fs）", wait_pid, waited)
    ui_scale = apply_scale_environment()
    log.info("界面缩放：%s（字体与布局 ×%.2f，DPI 1.0）", scale_text(), ui_scale)

    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("HushPlayer")
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    from .core.fonts import load_bundled_fonts

    load_bundled_fonts()
    try:
        app.setQuitOnLastWindowClosed(True)
    except Exception:  # noqa: BLE001
        pass

    from .core.single_instance import SingleInstance

    guard = SingleInstance(app)
    if not guard.try_lock():
        guard.notify_existing()
        return 0

    _install_excepthook(app)
    hush = HushApp(app)
    hush.start()
    guard.activate.connect(hush.bring_to_front)
    app.aboutToQuit.connect(hush.shutdown)
    app.aboutToQuit.connect(guard.close)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

