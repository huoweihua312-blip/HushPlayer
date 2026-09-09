"""Presentation-only identity layout; callers own text, artwork and playback state."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


class TrackIdentity(QWidget):
    def __init__(self, title_label, metadata_label, parent=None, *, spacing=3):
        super().__init__(parent)
        self.title_label = title_label
        self.metadata_label = metadata_label
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title_label)
        layout.addWidget(metadata_label)
