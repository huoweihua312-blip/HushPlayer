"""Left navigation: library sections, favourites, playlists, settings."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QPointF,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core import icons
from ...core import brand
from ...core.theme import css_rgba, qcolor, rgba, theme
from ...model.track import Playlist


@dataclass(frozen=True)
class NavEntry:
    route: str
    label: str
    icon: str


PRIMARY: tuple[NavEntry, ...] = (
    NavEntry("home", "首页", "home"),
    NavEntry("search", "搜索", "search"),
)

LIBRARY: tuple[NavEntry, ...] = (
    NavEntry("songs", "歌曲", "music_note"),
    NavEntry("albums", "专辑", "disc"),
    NavEntry("artists", "歌手", "mic"),
)

COLLECTION: tuple[NavEntry, ...] = (
    NavEntry("favorites", "我喜欢", "heart_fill"),
    NavEntry("recent", "最近播放", "clock"),
)


class LogoMark(QWidget):
    def __init__(self, size: int = 26, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # BUG-07: the official logo, once supplied, replaces the placeholder mark
        # everywhere (sidebar, about card, window/tray icon, installer).
        official = brand.rounded_logo_pixmap(max(12, self.width()), theme().mode)
        if official is not None:
            painter.drawPixmap(QPointF(0, 0), official)
            if not brand.has_official_logo():
                # The generated placeholder mark is charcoal on charcoal in the
                # dark sidebar; a hairline keeps it legible until the official
                # logo lands (see assets/brand/README.md).
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(rgba(theme().palette.text, 0.18), 1.0))
                painter.drawRoundedRect(rect, rect.width() * 0.30, rect.width() * 0.30)
            painter.end()
            return
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        accent = qcolor(theme().palette.accent)
        gradient.setColorAt(0.0, accent.lighter(112))
        gradient.setColorAt(1.0, accent.darker(118))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, rect.width() * 0.30, rect.width() * 0.30)

        # stylised "h" made of a stem and a rising wave
        pen = QPen(QColor(255, 255, 255, 236), max(1.6, rect.width() * 0.085))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        path = QPainterPath()
        cx = rect.center().x()
        path.moveTo(rect.x() + rect.width() * 0.30, rect.y() + rect.height() * 0.26)
        path.lineTo(rect.x() + rect.width() * 0.30, rect.y() + rect.height() * 0.74)
        path.moveTo(rect.x() + rect.width() * 0.30, rect.center().y())
        path.cubicTo(
            cx,
            rect.y() + rect.height() * 0.34,
            cx + rect.width() * 0.18,
            rect.y() + rect.height() * 0.66,
            rect.x() + rect.width() * 0.71,
            rect.y() + rect.height() * 0.62,
        )
        painter.drawPath(path)
        painter.end()


class SidebarItem(QAbstractButton):
    def __init__(self, entry: NavEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self._selected = False
        self._hover = False
        self._collapsed = False
        self._badge = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(entry.label)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.update()

    def set_badge(self, text: str) -> None:
        self._badge = text
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        radius = 8.0
        if self._selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.accent, 0.15 if palette.is_dark else 0.12))
            painter.drawRoundedRect(rect, radius, radius)
        elif self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.055))
            painter.drawRoundedRect(rect, radius, radius)

        color = (
            qcolor(palette.accent)
            if self._selected
            else rgba(palette.text, 0.82 if self._hover else 0.70)
        )
        if self._selected:
            color = qcolor(palette.accent)
        icon_size = 17
        if self._collapsed:
            icon_rect = QRectF(0, 0, icon_size, icon_size)
            icon_rect.moveCenter(rect.center())
        else:
            icon_rect = QRectF(0, 0, icon_size, icon_size)
            icon_rect.moveCenter(QPointF(rect.x() + 11 + icon_size / 2, rect.center().y()))
        icons.draw(painter, self.entry.icon, icon_rect, color)

        if not self._collapsed:
            font = theme().font(9.6, 600 if self._selected else 500)
            painter.setFont(font)
            painter.setPen(QPen(color))
            text_x = rect.x() + 38
            available = rect.width() - 44
            if self._badge:
                badge_font = theme().font(8.2, 600)
                badge_width = QFontMetrics(badge_font).horizontalAdvance(self._badge) + 14
                available -= badge_width + 4
                painter.setFont(badge_font)
                painter.setPen(QPen(rgba(palette.text, 0.45)))
                painter.drawText(
                    QRectF(rect.right() - badge_width - 6, rect.y(), badge_width, rect.height()),
                    Qt.AlignRight | Qt.AlignVCenter,
                    self._badge,
                )
                painter.setFont(font)
                painter.setPen(QPen(color))
            text = QFontMetrics(font).elidedText(self.entry.label, Qt.ElideRight, max(10, int(available)))
            painter.drawText(
                QRectF(text_x, rect.y(), max(10, available), rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                text,
            )
        painter.end()


class PlaylistItem(QAbstractButton):
    def __init__(self, playlist: Playlist, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playlist = playlist
        self._selected = False
        self._hover = False
        self._collapsed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(playlist.name)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        if self._selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.accent, 0.15 if palette.is_dark else 0.12))
            painter.drawRoundedRect(rect, 8, 8)
        elif self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.055))
            painter.drawRoundedRect(rect, 8, 8)
        color = qcolor(palette.accent) if self._selected else rgba(palette.text, 0.72)
        icon_size = 16
        if self._collapsed:
            icon_rect = QRectF(0, 0, icon_size, icon_size)
            icon_rect.moveCenter(rect.center())
        else:
            icon_rect = QRectF(rect.x() + 12, rect.center().y() - icon_size / 2, icon_size, icon_size)
        icon_name = "heart_fill" if self.playlist.is_favorites else "list"
        icons.draw(painter, icon_name, icon_rect, color)
        if not self._collapsed:
            font = theme().font(9.5, 600 if self._selected else 500)
            painter.setFont(font)
            painter.setPen(QPen(color))
            text = QFontMetrics(font).elidedText(
                self.playlist.name, Qt.ElideRight, int(rect.width() - 44)
            )
            painter.drawText(
                QRectF(rect.x() + 36, rect.y(), rect.width() - 44, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                text,
            )
        painter.end()


class Sidebar(QWidget):
    navigate = Signal(str)
    playlist_context_menu = Signal(int, QPoint)
    create_playlist_requested = Signal()
    collapsed_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self._route = "home"
        self._nav_items: dict[str, SidebarItem] = {}
        self._playlist_items: dict[int, PlaylistItem] = {}
        self.setObjectName("Sidebar")
        self.setMinimumWidth(72)
        self.setMaximumWidth(260)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.resize(236, self.height())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 12)
        outer.setSpacing(4)

        # wordmark
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 4, 10)
        header_layout.setSpacing(9)
        self.logo = LogoMark(26, header)
        self.wordmark = QLabel("HushPlayer", header)
        self.wordmark.setFont(theme().font(11.5, 800))
        self.wordmark.setStyleSheet(f"color: {theme().palette.text};")
        header_layout.addWidget(self.logo)
        header_layout.addWidget(self.wordmark)
        header_layout.addStretch(1)
        self._header = header
        self._header_layout = header_layout
        outer.addWidget(header)

        for entry in PRIMARY:
            outer.addWidget(self._make_nav(entry))
        outer.addSpacing(8)
        outer.addWidget(self._section_label("音乐库"))
        for entry in LIBRARY:
            outer.addWidget(self._make_nav(entry))
        outer.addSpacing(4)
        for entry in COLLECTION:
            outer.addWidget(self._make_nav(entry))

        playlist_header = QWidget(self)
        header_layout_row = QHBoxLayout(playlist_header)
        header_layout_row.setContentsMargins(10, 12, 4, 4)
        header_layout_row.setSpacing(4)
        self.playlist_label = QLabel("歌单", playlist_header)
        self.playlist_label.setFont(theme().font(8.6, 700))
        self.playlist_label.setStyleSheet(f"color: {css_rgba(theme().palette.text_secondary, 0.85)};")
        self.add_playlist_button = _PlusButton(playlist_header)
        self.add_playlist_button.clicked.connect(self.create_playlist_requested)
        self.add_playlist_button.setToolTip("新建歌单")
        header_layout_row.addWidget(self.playlist_label)
        header_layout_row.addStretch(1)
        header_layout_row.addWidget(self.add_playlist_button)
        self._playlist_header = playlist_header
        outer.addWidget(playlist_header)

        self.playlist_area = QScrollArea(self)
        self.playlist_area.setWidgetResizable(True)
        self.playlist_area.setFrameShape(QFrame.NoFrame)
        self.playlist_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.playlist_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.playlist_area.viewport().setAutoFillBackground(False)
        self.playlist_host = QWidget(self.playlist_area)
        self.playlist_host.setStyleSheet("background: transparent;")
        self.playlist_layout = QVBoxLayout(self.playlist_host)
        self.playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.playlist_layout.setSpacing(2)
        self.playlist_layout.addStretch(1)
        self.playlist_area.setWidget(self.playlist_host)
        outer.addWidget(self.playlist_area, 1)

        self.separator = QFrame(self)
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet(f"background: {css_rgba(theme().palette.border, 0.65)};")
        outer.addWidget(self.separator)
        outer.addSpacing(4)
        self.settings_item = self._make_nav(NavEntry("settings", "设置", "settings"))
        outer.addWidget(self.settings_item)

        self._width_anim = QPropertyAnimation(self, b"minimumWidth", self)
        self._width_anim.setDuration(200)
        self._width_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._width_anim2 = QPropertyAnimation(self, b"maximumWidth", self)
        self._width_anim2.setDuration(200)
        self._width_anim2.setEasingCurve(QEasingCurve.OutCubic)
        self._width_anim.finished.connect(self._sync_width_finished)

        self.set_collapsed(False)
        self.set_route("home")

    # ------------------------------------------------------------------ api
    def _make_nav(self, entry: NavEntry) -> SidebarItem:
        item = SidebarItem(entry, self)
        item.clicked.connect(lambda _checked=False, route=entry.route: self.navigate.emit(route))
        self._nav_items[entry.route] = item
        return item

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setFont(theme().font(8.6, 700))
        label.setStyleSheet(f"color: {css_rgba(theme().palette.text_secondary, 0.85)}; padding: 8px 10px 2px 10px;")
        label.setProperty("section", True)
        if not hasattr(self, "_section_labels"):
            self._section_labels: list[QLabel] = []
        self._section_labels.append(label)
        return label

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        if collapsed == self._collapsed and self.width() in (236, 72):
            pass
        self._collapsed = collapsed
        target = 72 if collapsed else 236
        for item in list(self._nav_items.values()) + list(self._playlist_items.values()):
            item.set_collapsed(collapsed)
        self.wordmark.setVisible(not collapsed)
        self.playlist_label.setVisible(not collapsed)
        self.add_playlist_button.setVisible(not collapsed)
        self.separator.setVisible(not collapsed)
        for label in getattr(self, "_section_labels", []):
            label.setVisible(not collapsed)
        self._header_layout.setContentsMargins(8 if not collapsed else 22, 4, 4, 10 if not collapsed else 10)
        if animate and not theme().reduce_motion:
            for anim, prop_value in (
                (self._width_anim, target),
                (self._width_anim2, target),
            ):
                anim.stop()
                anim.setStartValue(self.width())
                anim.setEndValue(prop_value)
                anim.start()
        else:
            self._width_anim.stop()
            self._width_anim2.stop()
            self.setMinimumWidth(target)
            self.setMaximumWidth(target)
            self.updateGeometry()

    def _sync_width_finished(self) -> None:
        pass

    def set_route(self, route: str) -> None:
        self._route = route
        for key, item in self._nav_items.items():
            item.set_selected(key == route)
        playlist_id = _playlist_id_from_route(route)
        for key, item in self._playlist_items.items():
            item.set_selected(key == playlist_id)

    def set_playlists(self, playlists: list[Playlist]) -> None:
        for item in self._playlist_items.values():
            self.playlist_layout.removeWidget(item)
            item.deleteLater()
        self._playlist_items.clear()
        index = 0
        for playlist in playlists:
            if playlist.system:
                continue
            item = PlaylistItem(playlist, self.playlist_host)
            item.set_collapsed(self._collapsed)
            item.clicked.connect(
                lambda _checked=False, pid=playlist.id: self.navigate.emit(f"playlist:{pid}")
            )
            item.customContextMenuRequested.connect(
                lambda pos, pid=playlist.id, widget=item: self.playlist_context_menu.emit(
                    pid, widget.mapToGlobal(pos)
                )
            )
            self.playlist_layout.insertWidget(index, item)
            self._playlist_items[playlist.id] = item
            index += 1
        self.set_route(self._route)

    def set_counts(self, counts: dict[str, str]) -> None:
        for key, text in counts.items():
            item = self._nav_items.get(key)
            if item is not None:
                item.set_badge(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        if palette.is_dark:
            gradient = QLinearGradient(0, 0, 0, self.height())
            gradient.setColorAt(0.0, qcolor(palette.sidebar))
            gradient.setColorAt(1.0, qcolor(palette.window).darker(102))
            painter.setBrush(gradient)
        else:
            painter.setBrush(qcolor(palette.sidebar))
        painter.drawRect(self.rect())
        painter.setPen(QPen(rgba(palette.border, 0.55), 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()

    def refresh_theme(self) -> None:
        self.wordmark.setStyleSheet(f"color: {theme().palette.text};")
        for label in getattr(self, "_section_labels", []):
            label.setStyleSheet(
                f"color: {css_rgba(theme().palette.text_secondary, 0.85)}; padding: 8px 10px 2px 10px;"
            )
        self.playlist_label.setStyleSheet(f"color: {css_rgba(theme().palette.text_secondary, 0.85)};")
        self.separator.setStyleSheet(f"background: {css_rgba(theme().palette.border, 0.65)};")
        self.update()


class _PlusButton(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hover = False
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.09))
            painter.drawEllipse(rect)
        icons.draw(
            painter,
            "plus",
            QRectF(0, 0, 13, 13).translated(rect.center() - QRectF(0, 0, 13, 13).center()),
            rgba(palette.text, 0.65),
        )
        painter.end()


def _playlist_id_from_route(route: str) -> int:
    if route.startswith("playlist:"):
        try:
            return int(route.split(":", 1)[1])
        except ValueError:
            return -1
    return -1


__all__ = ["Sidebar", "SidebarItem", "PlaylistItem", "LogoMark", "PRIMARY", "LIBRARY", "COLLECTION"]

