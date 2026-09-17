"""Lightweight top-level desktop lyrics presentation for UI V2."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

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


class DesktopLyricsLockButton(QToolButton):
    """A non-activating top-level control that remains clickable over pass-through lyrics."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setObjectName("desktopLyricsLockButton")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(32, 32)
        self.setIconSize(QSize(17, 17))


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
    _GLYPH_SAFETY_PADDING = 4

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
        self._settings_popover_visible = False
        self._right_button_pressed = False
        self._mouse_grabbed = False
        self._pending_drag_position: QPoint | None = None
        self._system_drag_active = False
        self._geometry_update_pending = False
        self._deferred_settings_resize = False
        self._enabled = False
        self._has_renderable_lyric = False
        self._changing_input_mode = False
        self._lock_button_closing = False
        self._rendered_main: str | None = None
        self._rendered_secondary: str | None = None
        self._stable_document_text_width: int | None = None
        self._stable_geometry_reset_pending = True
        self._runtime_position_initialized = False
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
        self._last_applied_layout: tuple[int, int] | None = None
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
        self._drag_move_timer = QTimer(self)
        self._drag_move_timer.setInterval(16)
        self._drag_move_timer.timeout.connect(self._apply_pending_drag_move)
        self._geometry_flush_timer = QTimer(self)
        self._geometry_flush_timer.setSingleShot(True)
        self._geometry_flush_timer.setInterval(0)
        self._geometry_flush_timer.timeout.connect(self._flush_deferred_geometry)

        playback_adapter.track_changed.connect(self._schedule_render)
        lyrics_adapter.document_changed.connect(self._invalidate_stable_geometry)
        lyrics_adapter.state_changed.connect(self._schedule_render)
        lyrics_adapter.active_line_changed.connect(self._schedule_render)
        lyrics_adapter.display_options_changed.connect(self._invalidate_stable_geometry)
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
        self._main_label.setWordWrap(False)
        self._main_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._main_label.setMinimumWidth(0)
        self._main_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._secondary_label = QLabel(self._surface)
        self._secondary_label.setObjectName("desktopLyricsSecondary")
        self._secondary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._secondary_label.setWordWrap(False)
        self._secondary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._secondary_label.setMinimumWidth(0)
        self._secondary_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        for label in (self._main_label, self._secondary_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.installEventFilter(self)

        surface_layout.addStretch(1)
        surface_layout.addWidget(self._main_label)
        self._secondary_layout = QHBoxLayout()
        self._secondary_layout.setContentsMargins(28, 0, 0, 0)
        self._secondary_layout.setSpacing(0)
        self._secondary_layout.addWidget(self._secondary_label, 1)
        surface_layout.addLayout(self._secondary_layout)
        surface_layout.addStretch(1)

        self._lock_button = DesktopLyricsLockButton()
        self._lock_button.clicked.connect(self._request_lock_toggle)
        self._lock_button.hide()
        self._drag_handle = QToolButton(self)
        self._drag_handle.setObjectName("desktopLyricsDragHandle")
        self._drag_handle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag_handle.setFixedSize(30, 30)
        self._drag_handle.setIconSize(QSize(18, 18))
        self._drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_handle.setToolTip("拖动桌面歌词")
        self._drag_handle.setAccessibleName("拖动桌面歌词")
        self._drag_handle.installEventFilter(self)
        self._drag_handle.hide()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_visuals()

    def apply_settings(
        self,
        values: Mapping[str, object],
        *,
        live_preview: bool = False,
    ) -> None:
        """Apply validated-or-defaulted settings without touching playback."""

        previous_typography = (
            self._settings.get("floating_lyrics_color"),
            self._settings.get("floating_lyrics_font_family"),
            self._settings.get("floating_lyrics_font_size"),
        )
        previous_measurement = (
            self._settings.get("floating_lyrics_font_family"),
            self._settings.get("floating_lyrics_font_size"),
            self._settings.get("floating_lyrics_width"),
        )
        previous_saved_position = (self._saved_x, self._saved_y)
        visible_center = QPoint(self.frameGeometry().center()) if self.isVisible() else None
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
        measurement_changed = previous_measurement != (
            self._settings["floating_lyrics_font_family"],
            self._settings["floating_lyrics_font_size"],
            self._settings["floating_lyrics_width"],
        )
        if measurement_changed:
            self._stable_document_text_width = None
            self._stable_geometry_reset_pending = True
        self._saved_x = int(self._settings["floating_lyrics_x"])
        self._saved_y = int(self._settings["floating_lyrics_y"])
        # The persisted height remains the user's baseline; the larger value
        # is only a runtime safety floor for the current lyric layout.
        target_width = int(self._settings["floating_lyrics_width"])
        target_height = int(self._settings["floating_lyrics_height"])
        layout_settings = (target_width, target_height)
        layout_settings_changed = self._last_applied_layout != layout_settings
        dragging = self._drag_offset is not None
        self._last_applied_layout = layout_settings
        typography_changed = previous_typography != (
            self._settings["floating_lyrics_color"],
            self._settings["floating_lyrics_font_family"],
            self._settings["floating_lyrics_font_size"],
        )
        if dragging:
            if layout_settings_changed:
                self._deferred_settings_resize = True
                self._geometry_update_pending = True
            self._sync_surface_geometry()
            self._apply_live_preview_visuals(typography_changed=typography_changed)
        elif live_preview:
            # Keep the current runtime floor during a continuous drag. This
            # prevents the window from repeatedly shrinking and growing while
            # the user is changing the font size or width.
            if layout_settings_changed:
                self.resize(target_width, max(self.height(), target_height))
                self._sync_surface_geometry()
            self._apply_live_preview_visuals(typography_changed=typography_changed)
        else:
            if layout_settings_changed:
                self.setMinimumHeight(0)
                self.resize(target_width, target_height)
                self._sync_surface_geometry()
            self._apply_visuals()
        self._apply_lock_preference(bool(self._settings["floating_lyrics_passthrough"]))
        if self.isVisible():
            position_changed = (self._saved_x, self._saved_y) != previous_saved_position
            if position_changed:
                if self._drag_offset is not None:
                    self._geometry_update_pending = True
                else:
                    self._place_on_screen()
            elif visible_center is not None and self._drag_offset is None:
                self._restore_window_center(visible_center)
        if not live_preview:
            self._schedule_render()

    def _apply_visuals(self) -> None:
        self.setWindowOpacity(int(self._settings.get("floating_lyrics_opacity", 100)) / 100.0)
        self._apply_surface_interaction_style()
        colors = self._theme.colors
        self._lock_button.setStyleSheet(
            "QToolButton#desktopLyricsLockButton { background: transparent; border: 0; "
            "border-radius: 8px; padding: 0; }"
            f"QToolButton#desktopLyricsLockButton:hover {{ background: {colors.hover_background}; }}"
            f"QToolButton#desktopLyricsLockButton:pressed {{ background: {colors.surface_pressed}; }}"
            "QToolButton#desktopLyricsLockButton:focus { background: transparent; border: 0; }"
        )
        self._drag_handle.setIcon(icon("more", self._theme))
        self._drag_handle.setStyleSheet(
            "QToolButton#desktopLyricsDragHandle { background: transparent; border: 0; "
            "border-radius: 7px; padding: 0; }"
            f"QToolButton#desktopLyricsDragHandle:hover {{ background: {colors.hover_background}; }}"
            f"QToolButton#desktopLyricsDragHandle:pressed {{ background: {colors.surface_pressed}; }}"
        )
        self._update_lock_button()
        self._apply_lyrics_fonts()
        self._apply_content_height_floor()
        self._update_lock_button_geometry()

    def _apply_surface_interaction_style(self) -> None:
        if self._locked:
            self._surface.setStyleSheet(
                "QFrame#desktopLyricsSurface { background: transparent; border: 0; }"
            )
            return
        border = QColor(self._theme.colors.border_strong)
        border.setAlpha(150)
        background = QColor(self._theme.colors.surface_primary)
        background.setAlpha(18)
        self._surface.setStyleSheet(
            "QFrame#desktopLyricsSurface { "
            f"background: rgba({background.red()}, {background.green()}, {background.blue()}, {background.alpha()}); "
            f"border: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha()}); "
            "border-radius: 9px; }"
        )

    def _apply_live_preview_visuals(self, *, typography_changed: bool) -> None:
        """Update only typography and geometry during continuous slider drags."""

        if typography_changed:
            self._apply_lyrics_fonts()
        self._apply_content_height_floor()
        self._sync_surface_geometry()
        self._update_lock_button_geometry()

    def _apply_lyrics_fonts(self) -> None:
        """Apply the selected lyric font and its matching visual styles."""

        color_name = str(self._settings.get("floating_lyrics_color") or "white")
        lyric_color = QColor(
            DESKTOP_LYRICS_COLORS.get(color_name, DESKTOP_LYRICS_COLORS["white"])
        )
        family = normalize_desktop_lyrics_font(
            self._settings.get("floating_lyrics_font_family")
        )
        size = int(self._settings.get("floating_lyrics_font_size", 42))
        # Keep the lyric itself as the surface: a restrained shadow improves
        # readability over both light and dark wallpapers without creating a
        # subtitle-style outline.
        secondary = f"rgba({lyric_color.red()}, {lyric_color.green()}, {lyric_color.blue()}, 0.58)"
        shadow = "text-shadow: 0 1px 5px rgba(0, 0, 0, 0.72);"
        # The application-wide QLabel stylesheet supplies a default font size,
        # so keep the explicit size here and update only these two labels during
        # a throttled preview tick instead of rebuilding the lyric contents.
        self._main_label.setStyleSheet(
            f"color: {lyric_color.name()}; font-family: '{family}'; "
            f"font-size: {size}px; font-weight: 600; {shadow}"
        )
        self._secondary_label.setStyleSheet(
            f"color: {secondary}; font-family: '{family}'; "
            f"font-size: {max(14, size // 2)}px; font-weight: 400; {shadow}"
        )
        main_font = QFont(family)
        main_font.setPixelSize(size)
        main_font.setWeight(QFont.Weight.DemiBold)
        secondary_font = QFont(family)
        secondary_font.setPixelSize(max(14, size // 2))
        secondary_font.setWeight(QFont.Weight.Normal)
        self._main_label.setFont(main_font)
        self._secondary_label.setFont(secondary_font)

    def _apply_content_height_floor(self, *, reset_to_settings_size: bool = False) -> None:
        """Keep two fixed lyric rows and widen the overlay for long text."""

        dragging = self._drag_offset is not None
        visible_center = (
            QPoint(self.frameGeometry().center())
            if (self.isVisible() or self._runtime_position_initialized) and not dragging
            else None
        )
        if not dragging:
            self._sync_surface_geometry()
        surface_layout = self._surface.layout()
        margins = surface_layout.contentsMargins()
        secondary_margins = self._secondary_layout.contentsMargins()
        # The layout contains a top stretch, main row, secondary row and a
        # bottom stretch, so there are three inter-item spacing slots.
        layout_spacing = max(0, int(surface_layout.spacing())) * 3
        main_metrics = QFontMetrics(self._main_label.font())
        secondary_metrics = QFontMetrics(self._secondary_label.font())
        main_height = main_metrics.height()
        secondary_height = secondary_metrics.height()
        width_safety = max(16, self._GLYPH_SAFETY_PADDING * 2)
        main_text_width = main_metrics.horizontalAdvance(self._main_label.text())
        secondary_text_width = secondary_metrics.horizontalAdvance(self._secondary_label.text())
        stable_text_width = self._stable_text_width(main_metrics, secondary_metrics)
        content_width = max(
            main_text_width + margins.left() + margins.right() + width_safety,
            secondary_text_width
            + margins.left()
            + margins.right()
            + secondary_margins.left()
            + width_safety,
            stable_text_width + margins.left() + margins.right() + width_safety,
            1,
        )
        baseline_width = int(self._settings.get("floating_lyrics_width", 980))
        required_width = max(baseline_width, int(content_width))
        required = (
            margins.top()
            + margins.bottom()
            + layout_spacing
            + main_height
            + secondary_height
            + self._GLYPH_SAFETY_PADDING
        )

        if dragging:
            if self.width() < required_width or self.height() < required:
                self._geometry_update_pending = True
            if reset_to_settings_size:
                self._deferred_settings_resize = True
                self._geometry_update_pending = True
            return

        self.setMinimumHeight(max(0, int(required)))
        self._sync_surface_geometry()
        if reset_to_settings_size:
            desired_width = required_width
            desired_height = max(
                int(self._settings.get("floating_lyrics_height", 135)),
                int(required),
            )
        else:
            # Do not shrink during lyric updates. Explicit settings changes
            # use reset_to_settings_size=True after their preview is released.
            desired_width = max(self.width(), required_width)
            desired_height = max(self.height(), int(required))
        resized = self.size() != QSize(int(desired_width), int(desired_height))
        if resized:
            self.resize(int(desired_width), int(desired_height))
            self._sync_surface_geometry()
        if resized and visible_center is not None:
            self._restore_window_center(visible_center)

    def _stable_text_width(
        self,
        main_metrics: QFontMetrics,
        secondary_metrics: QFontMetrics,
    ) -> int:
        """Measure a lyric document once so ordinary line changes never resize."""

        if self._stable_document_text_width is not None:
            return self._stable_document_text_width
        document = self._lyrics_adapter.document
        lines = tuple(document.lines) if document is not None else ()
        options = self._lyrics_adapter.display_options
        translation_visible = bool(options.get("translation"))
        secondary_indent = self._secondary_layout.contentsMargins().left()
        widest = 0
        for index, line in enumerate(lines):
            widest = max(
                widest,
                main_metrics.horizontalAdvance(str(line.text or "").strip()),
            )
            secondary_text = ""
            if translation_visible and str(line.translation or "").strip():
                secondary_text = str(line.translation).strip()
            elif index + 1 < len(lines):
                secondary_text = str(lines[index + 1].text or "").strip()
            if secondary_text:
                widest = max(
                    widest,
                    secondary_metrics.horizontalAdvance(secondary_text)
                    + secondary_indent,
                )
        self._stable_document_text_width = max(0, int(widest))
        return self._stable_document_text_width

    @property
    def is_enabled(self) -> bool:
        """Return the user's logical desktop-lyrics choice, independent of empty lyrics."""

        return self._enabled

    @property
    def is_locked(self) -> bool:
        """Return the persisted mouse-pass-through preference."""

        return self._locked

    def _schedule_deferred_geometry(self) -> None:
        if self._geometry_update_pending and not self._geometry_flush_timer.isActive():
            self._geometry_flush_timer.start()

    def _flush_deferred_geometry(self) -> None:
        if self._drag_offset is not None:
            self._schedule_deferred_geometry()
            return
        if self._render_timer.isActive():
            self._geometry_flush_timer.start()
            return
        if not self._geometry_update_pending:
            return
        reset_to_settings_size = self._deferred_settings_resize
        self._geometry_update_pending = False
        self._deferred_settings_resize = False
        self._apply_content_height_floor(
            reset_to_settings_size=reset_to_settings_size
        )
        self._sync_surface_geometry()
        self._update_lock_button_geometry()

    def _schedule_render(self, *_args) -> None:
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _invalidate_stable_geometry(self, *_args) -> None:
        self._stable_document_text_width = None
        self._stable_geometry_reset_pending = True
        self._schedule_render()

    def _render(self, *_args) -> None:
        line = self._lyrics_adapter.active_line
        main_text = ""
        secondary_text = ""
        if line is not None and str(line.text or "").strip():
            main_text = str(line.text).strip()
            options = self._lyrics_adapter.display_options
            if bool(options.get("translation")) and str(line.translation or "").strip():
                secondary_text = str(line.translation).strip()
            else:
                next_line = self._lyrics_adapter.next_line
                if next_line is not None and str(next_line.text or "").strip():
                    secondary_text = str(next_line.text).strip()
        if main_text != self._rendered_main:
            self._rendered_main = main_text
            self._main_label.setText(main_text)
        if secondary_text != self._rendered_secondary:
            self._rendered_secondary = secondary_text
            self._secondary_label.setText(secondary_text)
            self._secondary_label.setVisible(bool(secondary_text))
        reset_geometry = self._stable_geometry_reset_pending
        self._stable_geometry_reset_pending = False
        self._apply_content_height_floor(
            reset_to_settings_size=reset_geometry
        )
        self._has_renderable_lyric = bool(main_text)
        self._sync_render_visibility()

    def _sync_render_visibility(self) -> None:
        should_show = self._enabled and self._has_renderable_lyric
        if should_show and not self.isVisible():
            if not self._runtime_position_initialized:
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
        position = saved_point
        if not saved:
            position = QPoint()
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        if not saved:
            position = QPoint(
                available.left() + max(0, (available.width() - self.width()) // 2),
                available.bottom() - self.height() - 48,
            )
        self.move(clamp_desktop_lyrics_position(position, self.size(), available))
        self._runtime_position_initialized = True

    def _restore_window_center(self, center: QPoint) -> None:
        """Keep the visible lyric anchor stable after a transparent resize."""

        delta = center - self.frameGeometry().center()
        if delta != QPoint(0, 0):
            self.move(self.pos() + delta)
        self._runtime_position_initialized = True

    def reset_position(self) -> None:
        self._saved_x = -1
        self._saved_y = -1
        self._place_on_screen()
        self._emit_position()

    def _update_lock_button_geometry(self) -> None:
        if (
            not hasattr(self, "_lock_button")
            or self._lock_button_closing
            or self._drag_offset is not None
        ):
            return
        frame = self.frameGeometry()
        position = QPoint(
            frame.left() + max(8, (frame.width() - self._lock_button.width()) // 2),
            frame.top() + 6,
        )
        screen = QGuiApplication.screenAt(frame.center()) or QGuiApplication.primaryScreen()
        if screen is not None:
            position = clamp_desktop_lyrics_position(
                position,
                self._lock_button.size(),
                screen.availableGeometry(),
            )
        self._lock_button.move(position)
        if self._lock_button.isVisible():
            self._lock_button.raise_()
        self._update_drag_handle_geometry()

    def _update_drag_handle_geometry(self) -> None:
        if not hasattr(self, "_drag_handle"):
            return
        frame = self.frameGeometry()
        position = QPoint(
            frame.left() + 8,
            frame.top() + max(8, (frame.height() - self._drag_handle.height()) // 2),
        )
        self._drag_handle.move(position)
        if self._drag_handle.isVisible():
            self._drag_handle.raise_()

    def _apply_lock_preference(self, locked: bool) -> None:
        locked = bool(locked)
        changed = locked != self._locked
        self._locked = locked
        self._apply_surface_interaction_style()
        cursor = (
            Qt.CursorShape.ArrowCursor
            if locked
            else Qt.CursorShape.SizeAllCursor
        )
        self.setCursor(cursor)
        self._surface.setCursor(cursor)
        if changed and locked:
            self._finish_drag(persist_position=True)
            self._right_button_pressed = False
            self._suppress_unlock_until_exit = self._pointer_in_lyrics_or_button(QCursor.pos())
            self._lock_button.hide()
            self._drag_handle.hide()
            self._set_input_passthrough(True)
        elif changed:
            self._suppress_unlock_until_exit = False
            self._set_input_passthrough(False)
            if self.frameGeometry().contains(QCursor.pos()) and not self._settings_popover_visible:
                self._show_lock_affordance()
            self._update_drag_handle_geometry()
            self._drag_handle.show()
            self._drag_handle.raise_()
        elif not locked:
            self._set_input_passthrough(False)
            self._update_drag_handle_geometry()
            self._drag_handle.show()
            self._drag_handle.raise_()
        else:
            self._set_input_passthrough(True)
            self._drag_handle.hide()
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
        if (
            self._suppress_unlock_until_exit
            or self._settings_popover_visible
            or not self.isVisible()
        ):
            return
        self._interaction_timer.stop()
        self._update_lock_button_geometry()
        self._lock_button.show()
        self._lock_button.raise_()

    def _hide_lock_affordance(self) -> None:
        if self._drag_offset is not None:
            return
        self._lock_button.hide()

    def _request_lock_toggle(self) -> None:
        self._finish_drag(persist_position=True)
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
        if self._drag_offset is not None:
            if not (QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                self._finish_drag(persist_position=True)
            return
        cursor = QCursor.pos()
        if self._pointer_in_lyrics_or_button(cursor):
            self._interaction_timer.stop()
            if (
                not self._suppress_unlock_until_exit
                and not self._settings_popover_visible
                and not self._lock_button.isVisible()
            ):
                self._show_lock_affordance()
            return
        self._suppress_unlock_until_exit = False
        if self._lock_button.isVisible() and not self._interaction_timer.isActive():
            self._interaction_timer.start()

    def _pointer_in_lyrics_or_button(self, position: QPoint) -> bool:
        if self.frameGeometry().contains(position):
            return True
        return self._lock_button.isVisible() and self._lock_button.frameGeometry().contains(
            position
        )

    def set_settings_popover_visible(self, visible: bool) -> None:
        """Suspend pointer gestures while the quick-settings popup owns interaction."""

        visible = bool(visible)
        if visible == self._settings_popover_visible:
            return
        self._settings_popover_visible = visible
        self._right_button_pressed = False
        if visible:
            self._finish_drag(persist_position=True)
            self._interaction_timer.stop()
            self._lock_button.hide()
            self._drag_handle.hide()
        elif self.isVisible():
            if not self._locked:
                self._update_drag_handle_geometry()
                self._drag_handle.show()
                self._drag_handle.raise_()
            self._poll_cursor()

    def _emit_position(self) -> None:
        self._saved_x = int(self.x())
        self._saved_y = int(self.y())
        self.position_changed.emit(self._saved_x, self._saved_y)

    def _begin_drag(self, event: QMouseEvent) -> bool:
        if (
            self._locked
            or self._settings_popover_visible
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return False
        self._right_button_pressed = False
        self._lock_button.hide()
        self._drag_handle.hide()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._surface.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._cursor_timer.stop()
        self._interaction_timer.stop()
        self._pending_drag_position = None
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._system_drag_active = False
        window_handle = self.windowHandle()
        start_system_move = getattr(window_handle, "startSystemMove", None)
        if callable(start_system_move):
            try:
                self._system_drag_active = bool(start_system_move())
            except RuntimeError:
                self._system_drag_active = False
        if self._system_drag_active:
            self._cursor_timer.start()
            event.accept()
            return True
        self._drag_move_timer.start()
        try:
            self.grabMouse()
            self._mouse_grabbed = True
        except RuntimeError:
            self._mouse_grabbed = False
        event.accept()
        return True

    def _finish_drag(self, *, persist_position: bool) -> None:
        was_dragging = self._drag_offset is not None
        system_drag_active = self._system_drag_active
        pending_position = self._pending_drag_position
        self._pending_drag_position = None
        self._drag_move_timer.stop()
        if was_dragging and not system_drag_active and pending_position is not None:
            self.move(pending_position)
        self._drag_offset = None
        self._system_drag_active = False
        if self._mouse_grabbed:
            try:
                self.releaseMouse()
            except RuntimeError:
                pass
            self._mouse_grabbed = False
        if was_dragging and persist_position:
            self._emit_position()
        if was_dragging:
            self._schedule_deferred_geometry()
        if was_dragging and self.isVisible():
            self._cursor_timer.start()
            if not self._locked:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self._surface.setCursor(Qt.CursorShape.SizeAllCursor)
                self._update_drag_handle_geometry()
                self._drag_handle.show()
                self._drag_handle.raise_()
            if not self._locked and not self._settings_popover_visible:
                self._poll_cursor()

    def _handle_right_press(self, event: QMouseEvent) -> bool:
        if (
            self._locked
            or self._settings_popover_visible
            or event.button() != Qt.MouseButton.RightButton
        ):
            return False
        self._finish_drag(persist_position=True)
        self._right_button_pressed = True
        event.accept()
        return True

    def _handle_right_release(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.RightButton:
            return False
        requested = (
            self._right_button_pressed
            and not self._locked
            and not self._settings_popover_visible
        )
        self._right_button_pressed = False
        if requested:
            position = event.globalPosition().toPoint()
            self._finish_drag(persist_position=True)
            event.accept()
            QTimer.singleShot(0, lambda point=QPoint(position): self._emit_settings_request(point))
            return True
        return False

    def _emit_settings_request(self, position: QPoint) -> None:
        if self._locked or self._settings_popover_visible or not self.isVisible():
            return
        self._finish_drag(persist_position=True)
        self._lock_button.hide()
        self.settings_requested.emit(QPoint(position))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_right_press(event) or self._begin_drag(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._locked:
            if self._system_drag_active:
                event.accept()
                return
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._finish_drag(persist_position=True)
                event.accept()
                return
            self._pending_drag_position = event.globalPosition().toPoint() - self._drag_offset
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _apply_pending_drag_move(self) -> None:
        if self._drag_offset is None or self._locked or self._system_drag_active:
            self._drag_move_timer.stop()
            return
        pending_position = self._pending_drag_position
        if pending_position is None:
            return
        self._pending_drag_position = None
        self.move(pending_position)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_right_release(event):
            return
        if self._drag_offset is not None and event.button() == Qt.MouseButton.LeftButton:
            self._finish_drag(persist_position=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        drag_handle = getattr(self, "_drag_handle", None)
        if watched is drag_handle and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                return self._begin_drag(event)
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.mouseMoveEvent(event)
                return event.isAccepted()
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and self._drag_offset is not None
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._finish_drag(persist_position=True)
                event.accept()
                return True
        if watched is self._surface and isinstance(event, QContextMenuEvent):
            event.accept()
            return True
        if watched is self._surface and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                return self._handle_right_press(event) or self._begin_drag(event)
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.mouseMoveEvent(event)
                return event.isAccepted()
            if event.type() == QEvent.Type.MouseButtonRelease:
                if self._handle_right_release(event):
                    return True
                if self._drag_offset is not None and event.button() == Qt.MouseButton.LeftButton:
                    self._finish_drag(persist_position=True)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._drag_offset is not None:
            self._finish_drag(persist_position=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate:
            self._finish_drag(persist_position=True)
            self._right_button_pressed = False
        return super().event(event)

    def _sync_surface_geometry(self) -> None:
        """Keep the transparent child surface aligned after a runtime resize."""

        self._surface.setGeometry(self.rect())
        layout = self._surface.layout()
        if layout is not None:
            layout.setGeometry(self._surface.rect())
            layout.activate()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_surface_geometry()
        self._update_lock_button_geometry()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._update_lock_button_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        input_mode_change = self._changing_input_mode
        super().showEvent(event)
        if not input_mode_change:
            if not self._runtime_position_initialized:
                self._place_on_screen()
            self._cursor_timer.start()
            if not self._locked:
                self._update_drag_handle_geometry()
                self._drag_handle.show()
                self._drag_handle.raise_()
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
            self._finish_drag(persist_position=False)
            self._right_button_pressed = False
        super().hideEvent(event)
        if not input_mode_change:
            self.visible_changed.emit(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._lock_button_closing = True
        if self._enabled:
            self._enabled = False
            self.enabled_changed.emit(False)
        self._cursor_timer.stop()
        self._interaction_timer.stop()
        self._finish_drag(persist_position=False)
        self._right_button_pressed = False
        self._lock_button.hide()
        self._lock_button.close()
        self._lock_button.deleteLater()
        event.accept()
