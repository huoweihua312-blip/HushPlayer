"""Large header panel used by album / artist / playlist detail pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core.theme import css_rgba, rgba, theme
from .common import IconButton, TextButton
from .cover import HeroCover


class HeroPanel(QWidget):
    """Artwork on the left, big title and metadata on the right."""

    play_requested = Signal()
    shuffle_requested = Signal()
    menu_requested = Signal()

    def __init__(
        self,
        *,
        cover_size: int = 196,
        round_cover: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cover_size = cover_size
        self.setMinimumHeight(cover_size)
        self.cover = HeroCover(cover_size, radius=cover_size // 2 if round_cover else 12)
        self.cover.set_round(round_cover)

        self.eyebrow = QLabel("")
        self.title = QLabel("")
        self.meta = QLabel("")
        self.eyebrow.setVisible(False)
        for label in (self.eyebrow, self.title, self.meta):
            label.setTextInteractionFlags(Qt.NoTextInteraction)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.play_button = TextButton("播放", icon_name="play", accent=True, size=34)
        self.play_button.clicked.connect(self.play_requested)
        self.shuffle_button = TextButton("随机播放", icon_name="shuffle", size=34)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        self.more_button = IconButton("more", size=34, icon_size=16, tooltip="更多操作")
        self.more_button.clicked.connect(self.menu_requested)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        actions.addWidget(self.play_button)
        actions.addWidget(self.shuffle_button)
        actions.addWidget(self.more_button)
        actions.addStretch(1)
        self._actions = actions

        text = QVBoxLayout()
        text.setContentsMargins(0, 4, 0, 2)
        text.setSpacing(2)
        text.addStretch(1)
        text.addWidget(self.eyebrow)
        text.addWidget(self.title)
        text.addWidget(self.meta)
        text.addSpacing(8)
        text.addLayout(actions)
        text.addStretch(1)
        self._text_layout = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        layout.addWidget(self.cover, 0, Qt.AlignVCenter)
        layout.addLayout(text, 1)
        self.refresh_theme()

    # ------------------------------------------------------------------ data
    def set_cover_track(self, item) -> None:
        self.cover.set_track(item)

    def set_text(self, title: str, subtitle: str = "", meta: str = "") -> None:
        self.title.setText(title or "")
        self.eyebrow.setText((subtitle or "").upper())
        self.eyebrow.setVisible(bool(subtitle))
        self.meta.setText(meta or "")
        self.meta.setVisible(bool(meta))

    def set_actions_visible(self, visible: bool) -> None:
        for widget in (self.play_button, self.shuffle_button, self.more_button):
            widget.setVisible(visible)

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget)

    # ----------------------------------------------------------------- theme
    def refresh_theme(self) -> None:
        palette = theme().palette
        self.eyebrow.setStyleSheet(
            f"color:{css_rgba(palette.text, 0.5)}; font-size:{theme().pt(8.6):.1f}pt; font-weight:600;"
        )
        self.title.setStyleSheet(
            f"color:{css_rgba(palette.text, 0.98)}; font-size:{theme().pt(26):.1f}pt; font-weight:700;"
        )
        self.title.setWordWrap(True)
        self.meta.setStyleSheet(
            f"color:{css_rgba(palette.text, 0.55)}; font-size:{theme().pt(9):.1f}pt; font-weight:400;"
        )
        self.update()
