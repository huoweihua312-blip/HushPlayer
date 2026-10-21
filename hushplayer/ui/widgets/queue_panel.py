"""Slide-in play queue panel."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...core.theme import DARK, css_rgba, rgba, theme
from ..context import ctx
from ..menus import track_menu
from .common import IconButton, paint_badge
from .tracklist import TrackListWidget


class QueuePanel(QWidget):
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, immersive: bool = False) -> None:
        super().__init__(parent)
        self._immersive = immersive
        self._palette_active = False
        self.setObjectName("QueuePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # The duration column needs room for "4:02" plus the right
        # padding; 336 clipped it once the type scale grew.
        self.setFixedWidth(theme().scaled(336, factor=0.55))
        self._open = False
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hide_timer = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("播放队列")
        self.title.setStyleSheet(f"font-size:{theme().pt(13):.1f}pt; font-weight:700;")
        head.addWidget(self.title)
        self.count = QLabel("0 首")
        self.count.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(theme().palette.text, 0.45)};")
        head.addWidget(self.count)
        head.addStretch(1)
        self.clear_button = IconButton("trash", size=28, icon_size=15, tooltip="清空播放队列")
        self.clear_button.clicked.connect(self._clear)
        head.addWidget(self.clear_button)
        self.close_button = IconButton("close", size=28, icon_size=15, tooltip="关闭队列")
        self.close_button.clicked.connect(self.close_requested.emit)
        head.addWidget(self.close_button)
        layout.addLayout(head)

        self.context_label = QLabel("")
        self.context_label.setStyleSheet(
            f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(theme().palette.text, 0.45)};"
        )
        layout.addWidget(self.context_label)

        self.list = TrackListWidget()
        self.list.set_drag_reorder(True)
        self.list.set_empty_text("队列是空的", "播放歌曲后队列会显示在这里")
        self.list.play_requested.connect(self._on_play)
        self.list.menu_requested.connect(self._on_menu)
        self.list.remove_requested.connect(self._on_remove)
        self.list.reordered.connect(self._on_reordered)
        self.list.favorite_clicked.connect(self._on_favorite)
        layout.addWidget(self.list, 1)

        self.setStyleSheet(
            f"""
            #QueuePanel {{
                background: {theme().palette.surface};
                border-left: 1px solid {theme().palette.border};
            }}
            """
        )
        player = ctx().player
        player.queue_changed.connect(self.refresh)
        player.track_changed.connect(lambda _t: self.refresh())
        player.state_changed.connect(lambda _s: self.refresh())
        player.shuffle_changed.connect(lambda _v: self.refresh())
        player.repeat_changed.connect(lambda _v: self.refresh())
        self.hide()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        player = ctx().player
        items = player.queue.items
        self.list.set_tracks(items)
        self.list.set_favorites({t.id for t in items if t.favorite})
        current = player.current_track
        if current is not None:
            self.list.set_current(current.id, player.state == "playing")
        self.count.setText(f"{len(items)} 首")
        queue = player.queue
        bits = [queue.context or "当前队列"]
        if queue.shuffle:
            bits.append("随机播放")
        if queue.repeat == "one":
            bits.append("单曲循环")
        elif queue.repeat == "all":
            bits.append("列表循环")
        self.context_label.setText(" · ".join(bits))
        self.clear_button.setEnabled(bool(items))

    def toggle(self) -> None:
        self.open_panel() if not self._open else self.close_panel()

    def _panel_height(self, parent) -> int:
        """Height of the panel: the content area minus the player bar."""
        try:
            from ..context import ctx

            window = ctx().window
            playerbar = getattr(window, "playerbar", None)
            if playerbar is not None:
                return max(120, parent.height() - playerbar.height())
        except Exception:  # noqa: BLE001
            pass
        return parent.height()

    def open_panel(self) -> None:
        if self._open:
            return
        self._open = True
        self.refresh()
        self.show()
        self.raise_()
        parent = self.parentWidget()
        if parent is None:
            return
        end_x = parent.width() - self.width()
        start_x = parent.width()
        self.setGeometry(end_x, 0, self.width(), self._panel_height(parent))
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        from PySide6.QtCore import QPoint

        self._anim.setEndValue(QPoint(end_x, 0))
        self._anim.start()

    def close_panel(self) -> None:
        if not self._open:
            return
        self._open = False
        parent = self.parentWidget()
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        from PySide6.QtCore import QPoint

        self._anim.setEndValue(QPoint(parent.width() if parent else self.x(), 0))
        self._anim.start()
        self._anim.finished.connect(self._finish_hide)

    def _finish_hide(self) -> None:
        try:
            self._anim.finished.disconnect(self._finish_hide)
        except (RuntimeError, TypeError):
            pass
        if not self._open:
            self.hide()

    # ------------------------------------------------------------------ events
    def _on_play(self, tracks: list, index: int) -> None:
        row = ctx().player.queue.row_of(tracks[index].id) if tracks else -1
        if row >= 0:
            ctx().player.queue.set_current_row(row)
            ctx().player.play()

    def _on_menu(self, tracks: list, position) -> None:
        if not tracks:
            return
        menu = track_menu(
            self,
            tracks,
            on_play=lambda items: self._on_play(items, 0),
            on_remove=lambda items: self._on_remove(items),
        )
        menu.exec(position)

    def _on_remove(self, tracks: list) -> None:
        rows = [ctx().player.queue.row_of(t.id) for t in tracks]
        rows = [r for r in rows if r >= 0]
        if rows:
            ctx().player.remove_rows(rows)

    def _on_reordered(self, from_row: int, to_row: int) -> None:
        ctx().player.move_row(from_row, to_row)

    def _on_favorite(self, track) -> None:
        value = ctx().library.toggle_favorite(track)
        self.refresh()
        window = ctx().window
        if window is not None:
            window.toast("已添加到「我喜欢」" if value else "已从「我喜欢」移除", "success" if value else "info")

    def _clear(self) -> None:
        ctx().player.clear_queue()
        self.refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        parent = self.parentWidget()
        if parent is not None and self._open:
            self.move(parent.width() - self.width(), 0)

    def activate_palette(self) -> None:
        """Paint this panel in the dark palette while it floats over the stage."""
        if self._immersive and not self._palette_active:
            self._palette_active = True
            self.list.set_palette_override(DARK)
            self.refresh_theme()

    def release_palette(self) -> None:
        """Undo the dark override taken for the immersive stage."""
        if self._palette_active:
            self._palette_active = False
            self.list.set_palette_override(None)
            self.refresh_theme()

    def refresh_theme(self) -> None:
        palette = DARK if self._palette_active else theme().palette
        if self._palette_active:
            # Translucent so the stage colour still shows through the panel.
            self.setStyleSheet(
                """
                #QueuePanel {
                    background: rgba(16, 16, 18, 0.84);
                    border-left: 1px solid rgba(255, 255, 255, 0.08);
                    border-top-left-radius: 14px;
                    border-bottom-left-radius: 14px;
                }
                """
            )
        else:
            self.setStyleSheet(
                f"""
                #QueuePanel {{
                    background: {palette.surface};
                    border-left: 1px solid {palette.border};
                }}
                """
            )
        self.title.setStyleSheet(
            f"font-size:{theme().pt(13):.1f}pt; font-weight:700;"
            f" color:{css_rgba(palette.text, 0.95)};"
        )
        self.count.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.45)};")
        self.context_label.setStyleSheet(
            f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.45)};"
        )
        self.list.refresh_theme()

