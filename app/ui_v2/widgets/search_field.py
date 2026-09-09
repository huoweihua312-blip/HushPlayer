"""Reusable search presentation, preserving the existing debounced query contract."""
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget
from app.ui_v2.theme.icons import search
from app.ui_v2.widgets.line_edit import apply_optical_vertical_center
from app.ui_v2.widgets.search_input_controller import SearchInputController


class SearchField(QWidget):
    text_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_icon = QToolButton(self)
        self.search_icon.setObjectName('searchIcon')
        self.search_icon.setEnabled(False)
        self.line_edit = QLineEdit(self)
        self.line_edit.setObjectName('searchInput')
        apply_optical_vertical_center(self.line_edit)
        self.line_edit.setPlaceholderText('搜索歌曲、歌手、专辑')
        self.line_edit.setClearButtonEnabled(True)
        self.line_edit.setAccessibleName('搜索当前列表')
        self.line_edit.setToolTip('搜索当前列表中的歌曲、歌手或专辑；按 Enter 立即筛选')
        self.input_controller = SearchInputController(self.line_edit)
        self.input_controller.query_ready.connect(self.text_changed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.search_icon)
        layout.addWidget(self.line_edit)

    def set_theme(self, theme):
        self.search_icon.setIcon(search(theme))
        self.search_icon.setIconSize(QSize(theme.metrics.icon_md, theme.metrics.icon_md))

    def set_text(self, text):
        self.line_edit.setText(text)
