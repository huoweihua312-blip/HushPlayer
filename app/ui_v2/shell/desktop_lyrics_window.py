"""Lightweight top-level desktop lyrics presentation for UI V2."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.desktop_lyrics_settings import (
    DESKTOP_LYRICS_COLORS,
    normalize_desktop_lyrics_font,
)
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

    _HOT_ZONE_PX = 24
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
        self._passthrough = True
        self._enabled = False
        self._has_renderable_lyric = False
        self._interaction_mode = False
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
        self._interaction_timer.timeout.connect(self._leave_interactive_mode)

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

        self._toolbar = QFrame(self)
        self._toolbar.setObjectName("desktopLyricsToolbar")
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(3)
        self._reset_button = self._toolbar_button("归位", "将桌面歌词放回当前屏幕底部中央")
        self._passthrough_button = self._toolbar_button("穿透", "切换鼠标穿透")
        self._close_button = self._toolbar_button("关闭", "隐藏桌面歌词")
        toolbar_layout.addWidget(self._reset_button)
        toolbar_layout.addWidget(self._passthrough_button)
        toolbar_layout.addWidget(self._close_button)
        self._reset_button.clicked.connect(self.reset_position)
        self._passthrough_button.clicked.connect(self._toggle_passthrough)
        self._close_button.clicked.connect(self.hide_for_user)
        self._toolbar.hide()

    def _toolbar_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton(self._toolbar)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(text)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setMinimumSize(42, 30)
        return button

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
        self._set_passthrough(bool(self._settings["floating_lyrics_passthrough"]))
        if self.isVisible():
            self._place_on_screen()
        self._schedule_render()

    def _apply_visuals(self) -> None:
        color_name = str(self._settings.get("floating_lyrics_color") or "white")
        lyric_color = QColor(DESKTOP_LYRICS_COLORS.get(color_name, DESKTOP_LYRICS_COLORS["white"]))
        secondary = (
            f"rgba({lyric_color.red()}, {lyric_color.green()}, {lyric_color.blue()}, 0.72)"
        )
        accent = self._theme.colors.accent if self._theme is not None else "#7AA2F7"
        self.setWindowOpacity(int(self._settings.get("floating_lyrics_opacity", 100)) / 100.0)
        self._surface.setStyleSheet(
            "QFrame#desktopLyricsSurface { background: transparent; border: 0; }"
        )
        self._toolbar.setStyleSheet(
            "QFrame#desktopLyricsToolbar { background: rgba(18, 20, 25, 0.94); border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 10px; }"
            f"QToolButton {{ color: #F7F8FA; background: transparent; border: 0; border-radius: 7px; padding: 0 8px; font-size: 12px; }}"
            f"QToolButton:hover {{ background: {accent}; color: #101114; }}"
            "QToolButton:pressed { background: rgba(255, 255, 255, 0.22); }"
            "QToolButton:focus { border: 1px solid rgba(255, 255, 255, 0.78); }"
        )
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
        self._update_toolbar_geometry()

    @property
    def is_enabled(self) -> bool:
        """Return the user's logical desktop-lyrics choice, independent of empty lyrics."""

        return self._enabled

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

    def _update_toolbar_geometry(self) -> None:
        if not hasattr(self, "_toolbar"):
            return
        self._toolbar.adjustSize()
        self._toolbar.setGeometry(
            max(8, self.width() - self._toolbar.sizeHint().width() - 12),
            8,
            self._toolbar.sizeHint().width(),
            self._toolbar.sizeHint().height(),
        )
        self._toolbar.raise_()

    def _set_interactive(self) -> None:
        self._interaction_mode = True
        self._interaction_timer.stop()
        self._toolbar.show()
        self._toolbar.raise_()
        self._set_passthrough(False)

    def _leave_interactive_mode(self) -> None:
        if self._drag_offset is not None:
            return
        self._toolbar.hide()
        self._set_passthrough(True)
        self._interaction_mode = False

    def _set_passthrough(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._passthrough:
            self._toolbar.setVisible(not enabled)
            self._interaction_mode = not enabled
            self._update_passthrough_button()
            return
        self._passthrough = enabled
        self._interaction_mode = not enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        was_visible = self.isVisible()
        self._changing_input_mode = True
        try:
            self.setWindowFlags(flags)
        finally:
            self._changing_input_mode = False
        self._toolbar.setVisible(not enabled)
        self._update_passthrough_button()
        self.interaction_mode_changed.emit(not enabled)
        if was_visible:
            self.show()
            self.raise_()
            self._update_toolbar_geometry()

    def _toggle_passthrough(self) -> None:
        target_passthrough = not self._passthrough
        self._set_passthrough(target_passthrough)
        self._interaction_mode = not target_passthrough
        if not self._passthrough:
            self._interaction_timer.stop()

    def _update_passthrough_button(self) -> None:
        if not hasattr(self, "_passthrough_button"):
            return
        self._passthrough_button.setText("穿透" if not self._passthrough else "交互")
        self._passthrough_button.setToolTip(
            "当前为交互模式，点击后恢复鼠标穿透"
            if not self._passthrough
            else "当前为鼠标穿透，点击边缘或使用工具栏进入交互"
        )

    def _poll_cursor(self) -> None:
        if not self.isVisible():
            return
        cursor = QCursor.pos()
        frame = self.frameGeometry()
        if self._passthrough:
            if frame.adjusted(-8, -8, 8, 8).contains(cursor) and self._near_hot_zone(cursor, frame):
                self._set_interactive()
            return
        if frame.contains(cursor):
            self._interaction_timer.stop()
        elif not self._interaction_timer.isActive():
            self._interaction_timer.start()

    def _near_hot_zone(self, cursor: QPoint, frame: QRect) -> bool:
        margin = self._HOT_ZONE_PX
        return (
            abs(cursor.x() - frame.left()) <= margin
            or abs(cursor.x() - frame.right()) <= margin
            or abs(cursor.y() - frame.top()) <= margin
            or abs(cursor.y() - frame.bottom()) <= margin
        )

    def _emit_position(self) -> None:
        self._saved_x = int(self.x())
        self._saved_y = int(self.y())
        self.position_changed.emit(self._saved_x, self._saved_y)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            not self._passthrough
            and event.button() == Qt.MouseButton.LeftButton
            and not self._toolbar.geometry().contains(event.position().toPoint())
        ):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._passthrough:
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
        self._update_toolbar_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._place_on_screen()
        self._cursor_timer.start()
        self.visible_changed.emit(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        if not self._changing_input_mode and not self._passthrough:
            # Interaction mode is temporary. Reopening from the player bar
            # should return to the safe default instead of blocking input.
            self._passthrough = True
            self._toolbar.hide()
            self._changing_input_mode = True
            try:
                self.setWindowFlags(
                    self.windowFlags() | Qt.WindowType.WindowTransparentForInput
                )
            finally:
                self._changing_input_mode = False
            self._update_passthrough_button()
            self._interaction_mode = False
        self._cursor_timer.stop()
        self._interaction_timer.stop()
        self._drag_offset = None
        super().hideEvent(event)
        self.visible_changed.emit(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._enabled:
            self._enabled = False
            self.enabled_changed.emit(False)
        self._cursor_timer.stop()
        self._interaction_timer.stop()
        event.accept()
