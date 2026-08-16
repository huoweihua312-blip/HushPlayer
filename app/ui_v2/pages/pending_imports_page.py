"""UI V2 review surface for songs waiting to enter the local library."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.page_header import PageHeader


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

        self.header = PageHeader("待导入音乐", self)
        self.header.set_context("资料库")
        self.header.title_label.setMinimumWidth(110)
        self.header.count_label.setMinimumWidth(64)

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
        self.list_widget.setSpacing(4)

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
        for button in (
            self.select_all_button,
            self.clear_selection_button,
            self.import_button,
            self.ignore_button,
            self.open_folder_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.metrics.page_margin,
            theme.metrics.spacing_lg,
            theme.metrics.page_margin,
            theme.metrics.page_margin,
        )
        layout.setSpacing(theme.metrics.spacing_md)
        layout.addWidget(self.header)
        layout.addWidget(self.description)
        layout.addWidget(self.status_label)
        layout.addLayout(action_row)
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
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QWidget#pendingImportsPage {{ background: {c.content_background}; }}"
            f"QLabel#pendingImportsDescription {{ color: {c.secondary_text}; font-size: {theme.fonts.secondary}px; }}"
            f"QLabel#pendingImportsStatus {{ color: {c.accent}; font-size: {theme.fonts.secondary}px; }}"
            f"QLabel#pendingImportsEmpty {{ color: {c.secondary_text}; font-size: {theme.fonts.body}px; }}"
            f"QListWidget#pendingImportsList {{ background: {c.surface_primary}; border: 1px solid {c.border}; "
            f"border-radius: {theme.metrics.radius_md}px; color: {c.primary_text}; padding: {theme.metrics.spacing_sm}px; }}"
            f"QListWidget#pendingImportsList::item {{ padding: {theme.metrics.spacing_sm}px; border-radius: {theme.metrics.radius_sm}px; }}"
            f"QListWidget#pendingImportsList::item:selected {{ background: {c.playing_background}; color: {c.primary_text}; }}"
        )
        self.header.set_theme(theme)
        for button in (
            self.select_all_button,
            self.clear_selection_button,
            self.import_button,
            self.ignore_button,
            self.open_folder_button,
        ):
            primary = bool(button.property("pendingPrimary"))
            danger = bool(button.property("pendingDanger"))
            background = c.accent if primary else c.danger if danger else c.surface_secondary
            foreground = c.app_background if primary or danger else c.primary_text
            hover = c.accent_hover if primary else c.hover_background
            button.setStyleSheet(
                f"QToolButton {{ min-height: 34px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.border}; "
                f"border-radius: {theme.metrics.radius_sm}px; background: {background}; color: {foreground}; }}"
                f"QToolButton:hover {{ background: {hover}; }}"
                f"QToolButton:disabled {{ background: {c.surface_secondary}; color: {c.disabled_text}; }}"
            )

    def _format_record(self, record: dict) -> str:
        title = str(record.get("title") or Path(str(record.get("path") or "")).stem or "未知歌曲")
        artist = str(record.get("artist") or "未知艺术家")
        album = str(record.get("album") or "未知专辑")
        path = str(record.get("path") or "")
        return f"{title}\n{artist} · {album}\n{path}"

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))

    def _sync_action_state(self) -> None:
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
