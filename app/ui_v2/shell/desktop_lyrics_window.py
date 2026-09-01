"""Lightweight top-level desktop lyrics presentation for UI V2."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QFont,
    QGuiApplication,
    QMouseEvent,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.desktop_lyrics_settings import (
    DESKTOP_LYRICS_COLORS,
    normalize_desktop_lyrics_font,
)
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES, Theme


def clamp_desktop_lyrics_position(position: QPoint, size, available: QRect) -> QPoint:
    """Keep a floating window visible after display or DPI changes."""

    width = max(1, int(size.width()))
    height = max(1, int(size.height()))
    max_x = available.right() - width + 1
    max_y = available.bottom() - height + 1
    return QPoint(
        max(available.left(), min(int(position.x()), max_x)),
        max(available.top(), min(int(position.y()), max_y)),
    )


class DesktopLyricsWindow(QWidget):
    """A shared-adapter lyrics overlay with smart input pass-through."""

    position_changed = Signal(int, int)
    visible_changed = Signal(bool)
    enabled_changed = Signal(bool)
    interaction_mode_changed = Signal(bool)
    settings_requested = Signal(QPoint)
    lock_state_change_requested = Signal(bool)

    _CURSOR_POLL_MS = 160
    _INTERACTION_IDLE_MS = 1_500

    def __init__(
        self,
        playback_adapter: PlaybackAdapter,
        lyrics_adapter: LyricsAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        # A parent would make this a child surface rather than a desktop
        # window. MainWindow keeps the Python reference and owns shutdown.
        super().__init__(None)
        self._playback_adapter = playback_adapter
        self._lyrics_adapter = lyrics_adapter
        self._theme = theme
        self._drag_offset: QPoint | None = None
        self._saved_x = -1
        self._saved_y = -1
        self._locked = True
        self._input_passthrough = True
        self._suppress_unlock_until_exit = False
        self._enabled = False
        self._has_renderable_lyric = False
        self._changing_input_mode = False
        self._rendered_main: str | None = None
        self._rendered_secondary: str | None = None
        self._settings = {
            "floating_lyrics_color": "white",
            "floating_lyrics_opacity": 100,
            "floating_lyrics_font_size": 42,
            "floating_lyrics_width": 980,
            "floating_lyrics_height": 135,
            "floating_lyrics_font_family": OPEN_FONT_FAMILIES[0],
            "floating_lyrics_x": -1,
            "floating_lyrics_y": -1,
            "floating_lyrics_passthrough": True,
        }
        self.setObjectName("desktopLyricsWindow")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._build_ui()

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(0)
        self._render_timer.timeout.connect(self._render)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(self._CURSOR_POLL_MS)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._interaction_timer = QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(self._INTERACTION_IDLE_MS)
        self._interaction_timer.timeout.connect(self._hide_lock_affordance)

        playback_adapter.track_changed.connect(self._schedule_render)
        lyrics_adapter.document_changed.connect(self._schedule_render)
        lyrics_adapter.state_changed.connect(self._schedule_render)
        lyrics_adapter.active_line_changed.connect(self._schedule_render)
        lyrics_adapter.display_options_changed.connect(self._schedule_render)
        self.apply_settings(self._settings)

    def _build_ui(self) -> None:
        self._surface = QFrame(self)
        self._surface.setObjectName("desktopLyricsSurface")
        self._surface.setMouseTracking(True)
        self._surface.installEventFilter(self)
        surface_layout = QVBoxLayout(self._surface)
        surface_layout.setContentsMargins(18, 8, 18, 8)
        surface_layout.setSpacing(4)

        self._main_label = QLabel(self._surface)
        self._main_label.setObjectName("desktopLyricsMain")
        self._main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_label.setWordWrap(True)
        self._main_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._secondary_label = QLabel(self._surface)
        self._secondary_label.setObjectName("desktopLyricsSecondary")
        self._secondary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._secondary_label.setWordWrap(True)
        self._secondary_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        for label in (self._main_label, self._secondary_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        surface_layout.addStretch(1)
        surface_layout.addWidget(self._main_label)
        self._secondary_layout = QHBoxLayout()
        self._secondary_layout.setContentsMargins(28, 0, 0, 0)
        self._secondary_layout.setSpacing(0)
        self._secondary_layout.addWidget(self._secondary_label, 1)
        surface_layout.addLayout(self._secondary_layout)
        surface_layout.addStretch(1)

        self._lock_button = QToolButton(self)
        self._lock_button.setObjectName("desktopLyricsLockButton")
        self._lock_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._lock_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._lock_button.setFixedSize(32, 32)
        self._lock_button.setIconSize(QSize(17, 17))
        self._lock_button.clicked.connect(self._request_lock_toggle)
        self._lock_button.hide()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_visuals()

    def apply_settings(self, values: Mapping[str, object]) -> None:
        """Apply validated-or-defaulted settings without touching playback."""

        self._settings.update(dict(values or {}))
        self._settings["floating_lyrics_font_family"] = normalize_desktop_lyrics_font(
            self._settings.get("floating_lyrics_font_family")
        )
        self._settings["floating_lyrics_color"] = str(
            self._settings.get("floating_lyrics_color") or "white"
        ).strip().casefold()
        if self._settings["floating_lyrics_color"] not in DESKTOP_LYRICS_COLORS:
            self._settings["floating_lyrics_color"] = "white"
        for key, default, low, high in (
            ("floating_lyrics_opacity", 100, 20, 100),
            ("floating_lyrics_font_size", 42, 22, 84),
            ("floating_lyrics_width", 980, 420, 1600),
            ("floating_lyrics_height", 135, 90, 320),
        ):
            try:
                value = int(self._settings.get(key, default))
            except (TypeError, ValueError):
                value = default
            self._settings[key] = max(low, min(high, value))
        for key in ("floating_lyrics_x", "floating_lyrics_y"):
            try:
                self._settings[key] = int(self._settings.get(key, -1))
            except (TypeError, ValueError):
                self._settings[key] = -1
        self._settings["floating_lyrics_passthrough"] = bool(
            self._settings.get("floating_lyrics_passthrough", True)
        )
        self._saved_x = int(self._settings["floating_lyrics_x"])
        self._saved_y = int(self._settings["floating_lyrics_y"])
        self.resize(
            int(self._settings["floating_lyrics_width"]),
            int(self._settings["floating_lyrics_height"]),
        )
        self._apply_visuals()
        self._apply_lock_preference(bool(self._settings["floating_lyrics_passthrough"]))
        if self.isVisible():
            self._place_on_screen()
        self._schedule_render()

    def _apply_visuals(self) -> None:
        color_name = str(self._settings.get("floating_lyrics_color") or "white")
        lyric_color = QColor(DESKTOP_LYRICS_COLORS.get(color_name, DESKTOP_LYRICS_COLORS["white"]))
        secondary = (
            f"rgba({lyric_color.red()}, {lyric_color.green()}, {lyric_color.blue()}, 0.72)"
        )
        self.setWindowOpacity(int(self._settings.get("floating_lyrics_opacity", 100)) / 100.0)
        self._surface.setStyleSheet(
            "QFrame#desktopLyricsSurface { background: transparent; border: 0; }"
        )
        colors = self._theme.colors
        self._lock_button.setStyleSheet(
            "QToolButton#desktopLyricsLockButton { background: transparent; border: 0; "
            "border-radius: 8px; padding: 0; }"
            f"QToolButton#desktopLyricsLockButton:hover {{ background: {colors.hover_background}; }}"
            f"QToolButton#desktopLyricsLockButton:pressed {{ background: {colors.surface_pressed}; }}"
            f"QToolButton#desktopLyricsLockButton:focus {{ border: 1px solid {colors.focus_ring}; }}"
        )
        self._update_lock_button()
        family = normalize_desktop_lyrics_font(self._settings.get("floating_lyrics_font_family"))
        size = int(self._settings.get("floating_lyrics_font_size", 42))
        self._main_label.setStyleSheet(
            f"color: {lyric_color.name()}; font-family: '{family}'; "
            f"font-size: {size}px; font-weight: 600;"
        )
        self._secondary_label.setStyleSheet(
            f"color: {secondary}; font-family: '{family}'; "
            f"font-size: {max(14, size // 2)}px; font-weight: 400;"
        )
        main_font = QFont(family)
        main_font.setPixelSize(size)
        main_font.setWeight(QFont.Weight.DemiBold)
        secondary_font = QFont(family)
        secondary_font.setPixelSize(max(14, size // 2))
        secondary_font.setWeight(QFont.Weight.Normal)
        self._main_label.setFont(main_font)
        self._secondary_label.setFont(secondary_font)
        self._update_lock_button_geometry()

    @property
    def is_enabled(self) -> bool:
        """Return the user's logical desktop-lyrics choice, independent of empty lyrics."""

        return self._enabled

    @property
    def is_locked(self) -> bool:
        """Return the persisted mouse-pass-through preference."""

        return self._locked

    def _schedule_render(self, *_args) -> None:
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _render(self, *_args) -> None:
        line = self._lyrics_adapter.active_line
        main_text = ""
        secondary_text = ""
        if line is not None and str(line.text or "").strip():
            main_text = str(line.text).strip()
            options = self._lyrics_adapter.display_options
            if bool(options.get("translation")) and str(line.translation or "").strip():
                secondary_text = str(line.translation).strip()
            elif bool(options.get("romanization")) and str(line.romanization or "").strip():
                secondary_text = str(line.romanization).strip()
        if main_text != self._rendered_main:
            self._rendered_main = main_text
            self._main_label.setText(main_text)
        if secondary_text != self._rendered_secondary:
            self._rendered_secondary = secondary_text
            self._secondary_label.setText(secondary_text)
            self._secondary_label.setVisible(bool(secondary_text))
        self._has_renderable_lyric = bool(main_text)
        self._sync_render_visibility()

    def _sync_render_visibility(self) -> None:
        should_show = self._enabled and self._has_renderable_lyric
        if should_show and not self.isVisible():
            self._place_on_screen()
            self.show()
            self.raise_()
        elif not should_show and self.isVisible():
            self.hide()

    def show_for_current_screen(self) -> None:
        if not self._enabled:
            self._enabled = True
            self.enabled_changed.emit(True)
        self._place_on_screen()
        self._render()

    def hide_for_user(self) -> None:
        if self._enabled:
            self._enabled = False
            self.enabled_changed.emit(False)
        if self.isVisible():
            self.hide()

    def _place_on_screen(self) -> None:
        # Negative coordinates are valid on a left/top secondary monitor.
        # Only the paired (-1, -1) value means "never positioned".
        saved = not (self._saved_x == -1 and self._saved_y == -1)
        saved_point = QPoint(self._saved_x, self._saved_y)
        screen = QGuiApplication.screenAt(saved_point) if saved else None
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        if saved:
            position = saved_point
        else:
            position = QPoint(
                available.left() + max(0, (available.width() - self.width()) // 2),
                available.bottom() - self.height() - 48,
            )
        self.move(clamp_desktop_lyrics_position(position, self.size(), available))

    def reset_position(self) -> None:
        self._saved_x = -1
        self._saved_y = -1
        self._place_on_screen()
        self._emit_position()

    def _update_lock_button_geometry(self) -> None:
        if not hasattr(self, "_lock_button"):
            return
        self._lock_button.move(max(8, (self.width() - self._lock_button.width()) // 2), 6)
        self._lock_button.raise_()

    def _apply_lock_preference(self, locked: bool) -> None:
        locked = bool(locked)
        changed = locked != self._locked
        self._locked = locked
        if changed and locked:
            self._suppress_unlock_until_exit = self.frameGeometry().contains(QCursor.pos())
            self._lock_button.hide()
            self._set_input_passthrough(True)
        elif changed:
            self._suppress_unlock_until_exit = False
            self._set_input_passthrough(False)
            if self.frameGeometry().contains(QCursor.pos()):
                self._show_lock_affordance()
        elif not locked:
            self._set_input_passthrough(False)
        elif not self._lock_button.isVisible():
            self._set_input_passthrough(True)
        self._update_lock_button()

    def _set_input_passthrough(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._input_passthrough:
            return
        self._input_passthrough = enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        was_visible = self.isVisible()
        self._changing_input_mode = True
        try:
            self.setWindowFlags(flags)
            if was_visible:
                self.show()
                self.raise_()
                self._update_lock_button_geometry()
        finally:
            self._changing_input_mode = False
        self.interaction_mode_changed.emit(not enabled)

    def _show_lock_affordance(self) -> None:
        if self._suppress_unlock_until_exit:
            return
        self._interaction_timer.stop()
        if self._locked:
            self._set_input_passthrough(False)
        self._lock_button.show()
        self._lock_button.raise_()

    def _hide_lock_affordance(self) -> None:
        if self._drag_offset is not None:
            return
        self._lock_button.hide()
        if self._locked:
            self._set_input_passthrough(True)

    def _request_lock_toggle(self) -> None:
        self.lock_state_change_requested.emit(not self._locked)

    def _update_lock_button(self) -> None:
        if not hasattr(self, "_lock_button"):
            return
        action = "解锁" if self._locked else "锁定"
        self._lock_button.setIcon(icon("unlock" if self._locked else "lock", self._theme))
        self._lock_button.setToolTip(f"{action}桌面歌词")
        self._lock_button.setAccessibleName(f"{action}桌面歌词")

    def _poll_cursor(self) -> None:
        if not self.isVisible():
            return
        cursor = QCursor.pos()
        frame = self.frameGeometry()
        if frame.contains(cursor):
            self._interaction_timer.stop()
            if not self._suppress_unlock_until_exit and not self._lock_button.isVisible():
                self._show_lock_affordance()
            return
        self._suppress_unlock_until_exit = False
        if self._lock_button.isVisible() and not self._interaction_timer.isActive():
            self._interaction_timer.start()

    def _emit_position(self) -> None:
        self._saved_x = int(self.x())
        self._saved_y = int(self.y())
        self.position_changed.emit(self._saved_x, self._saved_y)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._locked and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._locked:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self._emit_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self._surface and isinstance(event, QContextMenuEvent):
            if not self._locked:
                self.settings_requested.emit(event.globalPos())
            event.accept()
            return True
        if watched is self._surface and isinstance(event, QMouseEvent):
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self.mousePressEvent(event)
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.mouseMoveEvent(event)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._drag_offset is not None:
                self.mouseReleaseEvent(event)
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._surface.setGeometry(self.rect())
        self._update_lock_button_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        input_mode_change = self._changing_input_mode
        super().showEvent(event)
        if not input_mode_change:
            self._place_on_screen()
            self._cursor_timer.start()
            self.visible_changed.emit(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        input_mode_change = self._changing_input_mode
        if not input_mode_change:
            self._lock_button.hide()
            self._suppress_unlock_until_exit = False
            if self._locked:
                self._set_input_passthrough(True)
            self._cursor_timer.stop()
            self._interaction_timer.stop()
            self._drag_offset = None
        super().hideEvent(event)
        if not input_mode_change:
            self.visible_changed.emit(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._enabled:
            self._enabled = False
            self.enabled_changed.emit(False)
        self._cursor_timer.stop()
        self._interaction_timer.stop()
        event.accept()
