"""The reduced cover, title, artist group used in immersive lyrics."""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_atmosphere import AbstractArtwork
from app.ui_v2.widgets.track_display import present_track_identity


class ElidedTrackLabel(QLabel):
    """A title may use two real lines before the final line is elided."""

    def __init__(self, parent: QWidget | None = None, *, max_lines: int = 1) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._max_lines = max(1, int(max_lines))
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setWordWrap(True)
        self.setText("")

    @property
    def line_count(self) -> int:
        return min(self._max_lines, len(self._wrapped_lines()))

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        self.update()

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        return QSize(max(hint.width(), self.fontMetrics().horizontalAdvance("M")), self.fontMetrics().height() * self._max_lines)

    def _wrapped_lines(self) -> list[str]:
        width = max(1, self.contentsRect().width())
        metrics = self.fontMetrics()
        lines: list[str] = []
        current = ""
        for token in re.findall(r"\S+\s*|\s+", self._full_text):
            candidate = current + token
            if current and metrics.horizontalAdvance(candidate) > width:
                lines.append(current.rstrip())
                current = token.lstrip()
            else:
                current = candidate
            while current and metrics.horizontalAdvance(current) > width:
                fragment = ""
                for character in current:
                    if fragment and metrics.horizontalAdvance(fragment + character) > width:
                        break
                    fragment += character
                if not fragment:
                    fragment, current = current[:1], current[1:]
                else:
                    current = current[len(fragment) :].lstrip()
                lines.append(fragment.rstrip())
        if current or not lines:
            lines.append(current.rstrip())
        return lines

    def paintEvent(self, event) -> None:  # noqa: N802
        lines = self._wrapped_lines()
        if len(lines) > self._max_lines:
            if self._max_lines == 1:
                lines = [self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.contentsRect().width())]
            else:
                remainder = " ".join(lines[self._max_lines - 1 :])
                lines = lines[: self._max_lines - 1] + [
                    self.fontMetrics().elidedText(remainder, Qt.TextElideMode.ElideRight, self.contentsRect().width())
                ]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        height = self.fontMetrics().height()
        start_y = self.contentsRect().y() + max(0, (self.contentsRect().height() - height * len(lines)) // 2)
        for index, text in enumerate(lines):
            painter.drawText(
                QRect(self.contentsRect().x(), start_y + index * height, self.contentsRect().width(), height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )


class ImmersiveTrackIdentity(QWidget):
    """Artwork plus the compact title, artist, and album identity block."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.cover = AbstractArtwork(theme, self)
        self.title_label = ElidedTrackLabel(self, max_lines=2)
        self.artist_label = ElidedTrackLabel(self)
        self.album_label = ElidedTrackLabel(self)
        self.title_label.setObjectName("immersiveTrackTitle")
        self.artist_label.setObjectName("immersiveTrackArtist")
        self.album_label.setObjectName("immersiveTrackAlbum")
        self._text_layout = QVBoxLayout()
        self._text_layout.setContentsMargins(0, 0, 0, 0)
        self._text_layout.setSpacing(10)
        self._text_layout.addWidget(self.title_label)
        self._text_layout.addWidget(self.artist_label)
        self._text_layout.addWidget(self.album_label)
        self._group = QWidget(self)
        self._group_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self._group)
        self._group_layout.setContentsMargins(0, 0, 0, 0)
        self._group_layout.setSpacing(8)
        self._group_layout.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignLeft)
        self._group_layout.addLayout(self._text_layout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._group, 0, Qt.AlignmentFlag.AlignLeft)
        self.setObjectName("immersiveTrackIdentity")
        self.set_theme(theme)
        self.set_track(None)

    def set_track(self, track: Track | None) -> None:
        self.cover.set_track(track)
        if track is None:
            self.title_label.set_full_text("未播放歌曲")
            self.artist_label.set_full_text("")
            self.album_label.set_full_text("")
            return
        identity = present_track_identity(track)
        self.title_label.set_full_text(identity.title)
        self.artist_label.set_full_text(identity.artist)
        self.album_label.set_full_text(identity.album)
        if identity.availability.is_visible:
            self.album_label.setToolTip(
                f"{identity.metadata}\n状态: {identity.availability.label}\n"
                f"{identity.availability.tooltip}"
            )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.cover.set_theme(theme)
        self.title_label.setStyleSheet(f"font-size: 29px; font-weight: 600; color: {theme.colors.primary_text};")
        self.artist_label.setStyleSheet(f"font-size: 18px; color: {theme.colors.secondary_text};")
        self.album_label.setStyleSheet(f"font-size: {theme.fonts.secondary}px; color: {theme.colors.subtle_text};")
        self.title_label.setMinimumHeight(self.title_label.fontMetrics().height() * 2)
        self.artist_label.setMinimumHeight(self.artist_label.fontMetrics().height())
        self.album_label.setMinimumHeight(self.album_label.fontMetrics().height())

    def apply_responsive_layout(
        self,
        width: int,
        compact: bool,
        artwork_percent: int = 100,
        *,
        reference_width: int | None = None,
    ) -> None:
        size_reference = max(int(width), int(reference_width or width))
        if compact:
            extent = 150 if size_reference < 900 else 205
        elif size_reference < 980:
            extent = 230
        elif size_reference < 1400:
            extent = 285
        elif size_reference < 1700:
            extent = 330
        else:
            extent = 335
        extent = max(120, min(410, round(extent * max(70, min(130, artwork_percent)) / 100)))
        self.cover.setFixedSize(extent, extent)
        self._group_layout.setDirection(QBoxLayout.Direction.LeftToRight if compact else QBoxLayout.Direction.TopToBottom)
        self._group_layout.setSpacing(12 if compact else 8)
        self._text_layout.setSpacing(10)
        self._group.setMaximumWidth(max(300, width))
        self.setMaximumHeight(195 if compact else 16_777_215)
