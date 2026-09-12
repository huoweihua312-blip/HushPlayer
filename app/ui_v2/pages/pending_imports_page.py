"""UI V2 review surface for songs waiting to enter the local library."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.page_header import PageHeader
from app.ui_v2.widgets.placeholder_cover import cover_pixmap
from app.ui_v2.widgets.online_presentation import style_action, style_caption


class _PendingRecordDelegate(QStyledItemDelegate):
    """Paint the existing pending record without replacing its selection model."""

    def paint(self, painter, option, index):
        record = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            return super().paint(painter, option, index)
        theme = self.parent().parent()._theme
        c = theme.colors
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.fillRect(option.rect, QColor(c.selected_background if selected else c.hover_background if hovered else c.app_background))
        bounds = QRectF(option.rect).adjusted(12, 8, -12, -8)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        marker = QRectF(bounds.left(), bounds.center().y() - 6, 12, 12)
        painter.setPen(QColor(c.accent if selected else c.border_strong))
        painter.setBrush(QColor(c.accent) if selected else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(marker, 2, 2)
        if selected:
            painter.setPen(QColor(c.app_background))
            painter.drawText(marker.adjusted(-2, -4, 2, 4), Qt.AlignmentFlag.AlignCenter, "✓")
        artwork = cover_pixmap(str(record.get("path") or record.get("title") or "pending"), 44, 44)
        painter.drawPixmap(int(bounds.left() + 32), int(bounds.center().y() - 22), artwork)
        suffix = Path(str(record.get("path") or "")).suffix.lstrip(".").upper()
        font = QFont(option.font)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor(c.subtle_text))
        painter.drawText(bounds, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, suffix)
        bounds.adjust(92, 0, -70, 0)
        title = str(record.get("title") or Path(str(record.get("path") or "")).stem or "未知歌曲")
        lines = (
            (title, 15, c.primary_text),
            (f"{record.get('artist') or '未知艺术家'} · {record.get('album') or '未知专辑'}", theme.fonts.caption, c.secondary_text),
            (str(record.get("path") or ""), 11, c.subtle_text),
        )
        for row, (text, size, color) in enumerate(lines):
            font = QFont(option.font)
            font.setPixelSize(size)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(color))
            value = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle if row == 2 else Qt.TextElideMode.ElideRight, int(bounds.width()))
            painter.drawText(QRectF(bounds.left(), bounds.top() + row * 22, bounds.width(), 22), Qt.AlignmentFlag.AlignVCenter, value)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QColor(c.focus_ring))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        painter.restore()


class PendingImportsPage(QWidget):
    """Review pending local tracks without owning persistence or scanning."""

    import_requested = Signal(object)
    ignore_requested = Signal(object)
    open_folder_requested = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._records: list[dict] = []
        self.setObjectName("pendingImportsPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.header = PageHeader("待导入音乐", self)
        self.header.set_context("资料库")
        self.header.title_label.setMinimumWidth(110)
        self.header.count_label.setMinimumWidth(64)
        self.header.accent_rail.hide()
        self.header.title_row.layout().removeWidget(self.header.count_label)
        self.header.identity.layout().addWidget(self.header.count_label)
        self.header.identity.layout().setSpacing(9)

        self.description = QLabel(
            "扫描发现的新音乐会先在这里确认；加入音乐库或忽略后，记录会从列表移除。",
            self,
        )
        self.description.setObjectName("pendingImportsDescription")
        self.description.setWordWrap(True)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("pendingImportsStatus")
        self.status_label.setWordWrap(True)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("pendingImportsList")
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setWordWrap(True)
        self.list_widget.setSpacing(0)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setItemDelegate(_PendingRecordDelegate(self.list_widget))
        self.list_widget.setMouseTracking(True)

        self.empty_label = QLabel("当前没有待导入音乐。", self)
        self.empty_label.setObjectName("pendingImportsEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)

        self.select_all_button = self._button("全选")
        self.clear_selection_button = self._button("取消选择")
        self.import_button = self._button("加入音乐库", primary=True)
        self.ignore_button = self._button("忽略", danger=True)
        self.open_folder_button = self._button("打开文件夹")
        self.select_all_button.clicked.connect(self.list_widget.selectAll)
        self.clear_selection_button.clicked.connect(self.list_widget.clearSelection)
        self.import_button.clicked.connect(self._request_import)
        self.ignore_button.clicked.connect(self._request_ignore)
        self.open_folder_button.clicked.connect(self._request_open_folder)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.selection_count = QLabel(self)
        action_row.addWidget(self.selection_count)
        action_row.addWidget(self.select_all_button)
        action_row.addWidget(self.clear_selection_button)
        action_row.addStretch(1)
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.ignore_button)
        action_row.addWidget(self.open_folder_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            42, 32, 42, 30,
        )
        layout.setSpacing(theme.metrics.spacing_md)
        layout.addWidget(self.header)
        layout.addWidget(self.description)
        layout.addSpacing(14)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.empty_label, 1)
        self.list_widget.itemSelectionChanged.connect(self._sync_action_state)
        self.set_theme(theme)
        self.set_records(())

    def _button(
        self,
        text: str,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setObjectName("pendingImportsActionButton")
        button.setMinimumSize(QSize(0, 34))
        button.setProperty("pendingPrimary", primary)
        button.setProperty("pendingDanger", danger)
        return button

    def set_records(self, records) -> None:
        self._records = [
            dict(record) for record in records if isinstance(record, dict)
        ]
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for record in self._records:
                item = QListWidgetItem(self._format_record(record))
                item.setData(Qt.ItemDataRole.UserRole, record)
                item.setToolTip(str(record.get("path") or ""))
                item.setSizeHint(QSize(0, 82))
                self.list_widget.addItem(item)
        finally:
            self.list_widget.blockSignals(False)
        self.header.set_count(len(self._records))
        self.empty_label.setVisible(not self._records)
        self.list_widget.setVisible(bool(self._records))
        self._sync_action_state()

    def records(self) -> tuple[dict, ...]:
        return tuple(dict(record) for record in self._records)

    def selected_records(self) -> list[dict]:
        return [
            dict(item.data(Qt.ItemDataRole.UserRole))
            for item in self.list_widget.selectedItems()
            if isinstance(item.data(Qt.ItemDataRole.UserRole), dict)
        ]

    def set_theme(self, theme: Theme) -> None:
        theme = get_theme(theme.mode, profile="b2")
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QWidget#pendingImportsPage {{ background: {c.app_background}; }}"
            f"QLabel#pendingImportsDescription {{ color: {c.secondary_text}; font-size: {theme.fonts.secondary}px; }}"
            f"QLabel#pendingImportsStatus {{ color: {c.secondary_text}; font-size: {theme.fonts.secondary}px; }}"
            f"QLabel#pendingImportsEmpty {{ color: {c.secondary_text}; font-size: {theme.fonts.body}px; }}"
            f"QListWidget#pendingImportsList {{ background: {c.app_background}; border: 0; "
            f"border-radius: {theme.metrics.radius_md}px; color: {c.primary_text}; padding: 0; }}"
            f"QListWidget#pendingImportsList::item {{ padding: 0; border-radius: {theme.metrics.radius_sm}px; }}"
            f"QListWidget#pendingImportsList::item:selected {{ background: {c.selected_background}; color: {c.primary_text}; }}"
        )
        self.header.set_theme(theme)
        style_caption(self.header.count_label, theme)
        style_caption(self.selection_count, theme)
        style_caption(self.description, theme)
        style_caption(self.status_label, theme, subtle=True)
        for button in (
            self.select_all_button,
            self.clear_selection_button,
            self.import_button,
            self.ignore_button,
            self.open_folder_button,
        ):
            primary = bool(button.property("pendingPrimary"))
            danger = bool(button.property("pendingDanger"))
            style_action(button, theme, primary=primary, danger=danger)

    def set_responsive_reference_width(self, width: int) -> None:
        inset = 28 if width < 950 else 42
        self.layout().setContentsMargins(inset, 32, inset, 30)

    def _format_record(self, record: dict) -> str:
        title = str(record.get("title") or Path(str(record.get("path") or "")).stem or "未知歌曲")
        artist = str(record.get("artist") or "未知艺术家")
        album = str(record.get("album") or "未知专辑")
        path = str(record.get("path") or "")
        return f"{title}\n{artist} · {album}\n{path}"

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))

    def _sync_action_state(self) -> None:
        self.selection_count.setText(f"已选择 {len(self.list_widget.selectedItems())} 首")
        has_records = bool(self._records)
        has_selection = bool(self.list_widget.selectedItems())
        self.select_all_button.setEnabled(has_records)
        self.clear_selection_button.setEnabled(has_selection)
        self.import_button.setEnabled(has_selection)
        self.ignore_button.setEnabled(has_selection)
        self.open_folder_button.setEnabled(has_selection)

    def _selected_paths(self) -> list[str]:
        return [
            str(record.get("path") or "")
            for record in self.selected_records()
            if str(record.get("path") or "").strip()
        ]

    def _request_import(self) -> None:
        self.import_requested.emit(self._selected_paths())

    def _request_ignore(self) -> None:
        self.ignore_requested.emit(self._selected_paths())

    def _request_open_folder(self) -> None:
        paths = self._selected_paths()
        if paths:
            self.open_folder_requested.emit(paths[0])
