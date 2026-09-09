"""A stacked content/empty surface with an explicit legacy safe inset."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedLayout, QWidget


class ContentSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.stack = QStackedLayout(self)

    def set_insets(self, inset: int, safe_bottom: int) -> None:
        self.stack.setContentsMargins(inset, inset, inset, safe_bottom + inset)
