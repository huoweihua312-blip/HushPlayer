"""Playlist import wizard: source → fetch → match → confirm.

A modal dialog on purpose (it owns a long-running async job and must not be
reopened twice), but it is styled with the app's own widgets so it looks like a
page rather than a system box.
"""

from __future__ import annotations

import time

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QStyle,
    QStackedWidget,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..core.logging_setup import log_exception
from .dialogs import ask_text, choose, notify
from ..core.theme import css_rgba, qcolor, rgba, theme
from ..model.track import format_duration
from ..online import matching
from ..services.playlist_import import PlaylistEntry, parse_playlist, parse_playlist_text
from ..services.playlist_link import PLATFORM_LABELS, PlaylistLinkError, detect_platform, fetch_link
from ..services.playlist_matcher import STATUS, MatchRow, PlaylistMatcher, apply_import, find_playlist
from .context import ctx
from .widgets.common import IconButton, TextButton
from .widgets.popup import PopupMenu
from .widgets.searchfield import SegmentedControl

__all__ = ["PlaylistImportDialog"]

_STEPS = ("选择来源", "获取歌曲", "智能匹配", "完成导入")


class _MatchModel(QAbstractTableModel):
    HEADERS = ("状态", "原始歌曲", "匹配结果", "评分", "来源")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[MatchRow] = []

    def set_rows(self, rows: list[MatchRow]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        column = index.column()
        if role == Qt.DisplayRole:
            if column == 0:
                return row.status_label
            if column == 1:
                artist = f" · {row.display_artist}" if row.display_artist else ""
                return f"{row.display_title}{artist}"
            if column == 2:
                if row.track is None:
                    return row.note or "—"
                artist = f" · {row.track.artist}" if row.track.artist else ""
                return f"{row.track.title}{artist}"
            if column == 3:
                return str(row.score) if row.score else ""
            if column == 4:
                return row.source_name
        if role == Qt.ToolTipRole:
            if row.track is None:
                return row.note or "还没有匹配结果"
            album = f"\n专辑：{row.track.album}" if row.track.album else ""
            verified = {True: "已验证可播放", False: "未能验证播放"}.get(row.verified, "")
            return f"{row.display_title}\n→ {row.track.title} · {row.track.artist}{album}{('\\n' + verified) if verified else ''}"
        if role == Qt.ForegroundRole:
            if column == 0:
                return QColor(
                    {
                        "local": "#3E9B6A",
                        "online": "#3E9B6A",
                        "unverified": "#C98A2E",
                        "review": "#C95770",
                        "unmatched": "#9A9AA2",
                        "skipped": "#9A9AA2",
                    }.get(row.status, theme().palette.text)
                )
            if row.status in ("unmatched", "skipped"):
                return rgba(theme().palette.text, 0.45)
        if role == Qt.UserRole:
            return row
        return None


class _MatchDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(0, 2, 0, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(theme().palette.accent, 0.16))
            painter.drawRoundedRect(rect.adjusted(3, 0, -3, 0), 7, 7)
        text = index.data(Qt.DisplayRole)
        color = index.data(Qt.ForegroundRole) or qcolor(theme().palette.text)
        font = theme().font(9.6, 500 if index.column() <= 2 else 400)
        painter.setFont(font)
        painter.setPen(QPen(color))
        pad = 10
        painter.drawText(
            rect.adjusted(pad, 0, -pad, 0),
            Qt.AlignVCenter | (Qt.AlignRight if index.column() == 3 else Qt.AlignLeft),
            str(text or ""),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(120, theme().scaled(34, factor=0.8))


class _StepBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = 0
        self.setFixedHeight(theme().scaled(34, factor=0.8))

    def set_index(self, index: int) -> None:
        self._index = index
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = theme().font(9.2, 500)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = self.width() / len(_STEPS)
        for index, label in enumerate(_STEPS):
            active = index <= self._index
            current = index == self._index
            x = index * width
            colour = theme().palette.accent if active else rgba(theme().palette.text, 0.35)
            painter.setPen(QPen(colour))
            text = f"{index + 1}. {label}"
            painter.drawText(
                int(x), 0, int(width), self.height(), Qt.AlignCenter, text
            )
            if index < len(_STEPS) - 1:
                pen = QPen(rgba(theme().palette.text, 0.18), 1)
                painter.setPen(pen)
                y = self.height() / 2
                painter.drawLine(int(x + width - metrics.horizontalAdvance(text) / 2 - 40), int(y), int(x + width - 10), int(y))
        painter.end()



def _setting(key: str, default=None):
    try:
        settings = getattr(ctx(), "settings", None)
    except RuntimeError:
        return default
    return settings.get(key, default) if settings is not None else default


def _remember(key: str, value) -> None:
    try:
        settings = getattr(ctx(), "settings", None)
    except RuntimeError:
        return
    if settings is not None:
        settings.set(key, value)

class _TableHeader(QWidget):
    """自绘表头：不依赖 QHeaderView 的原生配色，主题切换后随重绘更新。"""

    def __init__(self, table: QTableView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = table
        self.setFixedHeight(theme().scaled(30, factor=0.55))
        table.horizontalHeader().sectionResized.connect(lambda *_: self.update())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.setFixedHeight(theme().scaled(30, factor=0.55))

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = theme().font(9.0, 500)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        table = self._table
        for column in range(table.model().columnCount()):
            left = table.columnViewportPosition(column)
            width = table.columnWidth(column)
            if width <= 0:
                continue
            text = _MatchModel.HEADERS[column]
            align = Qt.AlignRight if column == 3 else Qt.AlignLeft
            padding = theme().scaled(10, factor=0.6)
            rect = self.rect().adjusted(left + padding, 0, -(self.width() - left - width) - padding, 0)
            painter.setPen(rgba(palette.text, 0.62))
            painter.drawText(rect, align | Qt.AlignVCenter, metrics.elidedText(text, Qt.ElideRight, max(10, width - padding * 2)))
        painter.setPen(QPen(rgba(palette.text, 0.12), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.end()


class _TableHeaderSpacer(QWidget):
    pass


class _DialogTitleBar(QWidget):
    """Self-drawn caption so the title lines up with the content padding.

    The native Windows caption is inset ~8px and cannot be laid out, which made
    the wizard look misaligned next to its 24px content margin.
    """

    PAD = 24

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme().scaled(58, factor=0.8))
        self.title_label = QLabel(title, self)
        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setWordWrap(True)
        self.setMouseTracking(True)
        self._drag_offset: QPoint | None = None
        self._close: QWidget | None = None

    def attach_close(self, button: QWidget) -> None:
        self._close = button
        button.setParent(self)
        button.raise_()
        self._place_close()

    def _place_close(self) -> None:
        if self._close is None:
            return
        size = theme().scaled(32, factor=0.8)
        pad = theme().scaled(self.PAD, factor=0.8)
        top = (self.height() - size) // 2
        self._close.setGeometry(self.width() - pad - size, top, size, size)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        pad = theme().scaled(self.PAD, factor=0.8)
        top = theme().scaled(12, factor=0.8)
        close_w = theme().scaled(32, factor=0.8)
        right = self.width() - pad - close_w - theme().scaled(8, factor=0.6)
        self.title_label.setGeometry(pad, top, max(120, right - pad), theme().scaled(24, factor=0.8))
        self.subtitle_label.setGeometry(
            pad,
            top + theme().scaled(24, factor=0.8),
            max(120, right - pad),
            theme().scaled(18, factor=0.8),
        )
        self._place_close()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), theme().palette.window)
        painter.setPen(QPen(rgba(theme().palette.text, 0.08), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._drag_offset = None
            else:
                self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class PlaylistImportDialog(QDialog):
    imported = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入歌单")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(960, 640)
        self.resize(1040, 700)
        self._entries: list[PlaylistEntry] = []
        self._playlist_name = ""
        self._note = ""
        self._matcher: PlaylistMatcher | None = None
        self._stage = 0

        self._build()
        self._apply_theme()
        theme().changed.connect(self._apply_theme)

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        pad = theme().scaled(_DialogTitleBar.PAD, factor=0.8)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = _DialogTitleBar(
            "导入歌单",
            "从文件或其他音乐平台导入，并匹配到你的本地与在线音源",
            self,
        )
        self.title_label = self.title_bar.title_label
        self.subtitle_label = self.title_bar.subtitle_label
        self.close_button = IconButton("close", size=32, icon_size=16, tooltip="关闭")
        self.close_button.clicked.connect(self.reject)
        self.title_bar.attach_close(self.close_button)
        root.addWidget(self.title_bar)

        body = QWidget(self)
        content = QVBoxLayout(body)
        content.setContentsMargins(pad, theme().scaled(12, factor=0.8), pad, theme().scaled(18, factor=0.8))
        content.setSpacing(12)
        root.addWidget(body, 1)

        self.steps = _StepBar()
        content.addWidget(self.steps)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_source_page())
        self.stack.addWidget(self._build_match_page())
        self.stack.addWidget(self._build_done_page())
        content.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        footer.addWidget(self.status_label, 1)
        footer.addStretch(1)
        self.cancel_button = TextButton("取消", size=32)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        self.back_button = TextButton("上一步", size=32)
        self.back_button.clicked.connect(self._go_back)
        footer.addWidget(self.back_button)
        self.next_button = TextButton("下一步", icon_name="chevron_right", size=32, accent=True)
        self.next_button.clicked.connect(self._go_next)
        self.adopt_all = TextButton("全部采用最佳候选", icon_name="check", size=30)
        self.adopt_all.clicked.connect(self._adopt_all)
        self.adopt_all.setVisible(False)
        footer.addWidget(self.adopt_all)
        footer.addWidget(self.next_button)
        content.addLayout(footer)

    def _build_source_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        file_row = QHBoxLayout()
        self.file_button = TextButton("选择歌单文件…", icon_name="folder", size=34, accent=True)
        self.file_button.clicked.connect(self._pick_file)
        file_row.addWidget(self.file_button)
        self.file_hint = QLabel("支持 m3u / m3u8 / pls / csv / txt / Apple Music 的 Library.xml")
        file_row.addWidget(self.file_hint, 1)
        layout.addLayout(file_row)

        link_row = QHBoxLayout()
        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("粘贴歌单链接，例如 https://music.163.com/playlist?id=3778678")
        self.link_input.returnPressed.connect(self._fetch_link)
        link_row.addWidget(self.link_input, 1)
        self.link_button = TextButton("获取歌单", icon_name="cloud", size=34)
        self.link_button.clicked.connect(self._fetch_link)
        link_row.addWidget(self.link_button)
        layout.addLayout(link_row)

        self.source_info = QLabel("")
        self.source_info.setWordWrap(True)
        layout.addWidget(self.source_info)

        self.source_hint = QLabel(
            "链接导入：网易云公开歌单可直接读取；Apple Music 需要开发者令牌，"
            "QQ / 酷狗 / 酷我需要登录 Cookie，这些情况请导出文件后再导入。"
        )
        self.source_hint.setWordWrap(True)
        layout.addWidget(self.source_hint)
        layout.addStretch(1)

        self.source_guide = QLabel(
            "还没有选择歌单来源\n\n"
            "粘贴公开歌单链接后点「获取歌单」，或者选择一个导出的歌单文件。\n"
            "歌曲会先在本机音乐库里找，找不到再到在线音源里匹配。"
        )
        self.source_guide.setWordWrap(True)
        self.source_guide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.source_guide, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)
        return page

    def _build_match_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("歌单名称"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("导入后的歌单名")
        top.addWidget(self.name_input, 1)
        self.online_toggle = QCheckBox("在线音源补齐")
        self.online_toggle.setChecked(True)
        self.online_toggle.setToolTip("本地没有的歌曲，用已启用的在线音源搜索")
        top.addWidget(self.online_toggle)
        top.addSpacing(10)
        self.strength = SegmentedControl(["严格", "平衡", "宽松"])
        self.strength.setToolTip(
            "严格：同时要求高分与明显领先；平衡：推荐；宽松：只取最高分，允许低置信导入"
        )
        saved = str(_setting("playlist.import_strength", "balanced"))
        self.strength.set_current({"strict": 0, "balanced": 1, "loose": 2}.get(saved, 1))
        top.addWidget(self.strength)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        self.counts_label = QLabel("")
        layout.addWidget(self.counts_label)

        self.table = QTableView()
        self.model = _MatchModel(self)
        self.table.setModel(self.model)
        self.table.setItemDelegate(_MatchDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setVisible(False)
        header_view.setSectionsClickable(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, theme().scaled(74, factor=0.6))
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, theme().scaled(56, factor=0.6))
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, theme().scaled(96, factor=0.6))
        self.table.doubleClicked.connect(self._open_candidates)
        self.table_header = _TableHeader(self.table)
        self.table_frame = QFrame()
        self.table_frame.setObjectName("ImportTableFrame")
        frame_layout = QVBoxLayout(self.table_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        frame_layout.addWidget(self.table_header)
        frame_layout.addWidget(self.table, 1)
        layout.addWidget(self.table_frame, 1)

        self.match_hint = QLabel(
            "双击一行可换候选 / 手动搜索 / 跳过；只导入「本地」「在线已匹配」与「在线未验证」的行。"
        )
        self.match_hint.setWordWrap(True)
        layout.addWidget(self.match_hint)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(10)
        self.done_title = QLabel("导入完成")
        layout.addWidget(self.done_title)
        self.done_detail = QLabel("")
        self.done_detail.setWordWrap(True)
        layout.addWidget(self.done_detail)
        row = QHBoxLayout()
        row.addStretch(1)
        self.open_button = TextButton("打开歌单", icon_name="play", size=34, accent=True)
        self.open_button.clicked.connect(self._open_playlist)
        row.addWidget(self.open_button)
        self.finish_button = TextButton("完成", size=34)
        self.finish_button.clicked.connect(self.accept)
        row.addWidget(self.finish_button)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ theme
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_round_mask()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_round_mask()

    def _apply_round_mask(self) -> None:
        """Frameless window: clip the corners ourselves (no translucent window)."""
        radius = theme().scaled(14, factor=0.7)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def _apply_theme(self, *_args) -> None:
        palette = theme().palette
        self.setStyleSheet(
            f"QDialog {{ background: {palette.window}; }}"
            f"QLabel {{ color: {palette.text}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size:{theme().pt(15):.1f}pt; font-weight:600; color:{palette.text};"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.55)};"
        )
        self.title_bar.update()
        self._apply_round_mask()
        self.file_hint.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.5)};")
        self.source_info.setStyleSheet(f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.75)};")
        self.source_hint.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.5)};")
        self.source_guide.setStyleSheet(
            f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.42)};"
            f" padding: {theme().scaled(18, factor=0.8)}px {theme().scaled(22, factor=0.8)}px;"
            f" border: 1px dashed {css_rgba(palette.text, 0.16)};"
            f" border-radius: {theme().scaled(12, factor=0.6)}px;"
        )
        self.counts_label.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.55)};")
        self.match_hint.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.5)};")
        self.status_label.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.55)};")
        self.done_title.setStyleSheet(f"font-size:{theme().pt(15):.1f}pt; font-weight:600; color:{palette.text};")
        self.done_detail.setStyleSheet(f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.72)};")
        self.progress.setStyleSheet(
            f"QProgressBar {{ background:{css_rgba(palette.text, 0.10)}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{palette.accent}; border-radius:3px; }}"
        )
        self.table.setStyleSheet("QTableView { background: transparent; border: none; }")
        self.table_frame.setStyleSheet(
            f"QFrame#ImportTableFrame {{ background: {palette.surface};"
            f" border: none; }}"
        )
        self._table_frame_inset = theme().scaled(1, factor=0.6)

    # ------------------------------------------------------------------ flow
    @property
    def stage(self) -> int:
        return self._stage

    def _set_stage(self, stage: int) -> None:
        self._stage = stage
        self.steps.set_index((0, 2, 3)[stage])
        self.stack.setCurrentIndex(0 if stage == 0 else 1 if stage == 1 else 2)
        self.back_button.setVisible(stage == 1)
        self.next_button.setVisible(stage in (0, 1))
        # The finished page has its own 打开歌单 / 完成 buttons; the footer would
        # only duplicate them, so it is hidden there.
        self.cancel_button.setVisible(stage in (0, 1))
        self.status_label.setVisible(stage == 1)
        self.cancel_button.setText("取消")
        if stage == 0:
            self.next_button.setEnabled(bool(self._entries))
            self._set_next("下一步")
        elif stage == 1:
            self._set_next("开始导入" if self._matcher and self._matcher.total else "下一步")
        elif stage == 2:
            self.next_button.setVisible(False)

    def _set_next(self, text: str) -> None:
        """TextButton paints its own label, so plain setText() would not show."""
        if hasattr(self.next_button, "set_text"):
            self.next_button.set_text(text)
        else:
            self.next_button.setText(text)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择歌单文件",
            "",
            "歌单文件 (*.m3u *.m3u8 *.pls *.csv *.txt *.xml *.plist);;所有文件 (*)",
        )
        if not path:
            return
        try:
            parsed = parse_playlist(path)
        except Exception as exc:  # noqa: BLE001
            log_exception("解析歌单文件失败", exc)
            self._set_info(f"无法解析这个文件：{exc}", error=True)
            return
        self._accept_entries(parsed.name, parsed.entries, f"来自文件 {Path(path).name}（{parsed.kind}）")

    def _fetch_link(self) -> None:
        url = self.link_input.text().strip()
        if not url:
            self._set_info("先粘贴一个歌单链接。", error=True)
            return
        platform = detect_platform(url)
        self._set_info(f"正在读取 {PLATFORM_LABELS.get(platform, '歌单')} …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = fetch_link(url)
        except PlaylistLinkError as exc:
            self._set_info(str(exc), error=True)
            return
        except Exception as exc:  # noqa: BLE001
            log_exception("读取歌单链接失败", exc)
            self._set_info(f"读取失败：{exc}", error=True)
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not result.supported:
            self._set_info(result.reason or "这个平台暂不支持链接导入。", error=True)
            return
        if not result.entries:
            self._set_info("这个歌单是空的，或者平台没有返回歌曲。", error=True)
            return
        self._accept_entries(result.name, result.entries, f"来自 {PLATFORM_LABELS.get(result.platform, '歌单')} 链接")

    def _accept_entries(self, name: str, entries: list[PlaylistEntry], note: str) -> None:
        self._entries = list(entries)
        self.source_guide.setVisible(not self._entries)
        self._playlist_name = (name or "").strip() or "导入的歌单"
        self._note = note
        self.name_input.setText(self._playlist_name)
        detail = f"{self._playlist_name} · {len(entries)} 首 · {note}"
        self._set_info(detail)
        self._set_stage(0)
        self.next_button.setEnabled(True)

    def _set_info(self, text: str, *, error: bool = False) -> None:
        self.source_info.setText(text)
        colour = theme().palette.danger if error else rgba(theme().palette.text, 0.75)
        self.source_info.setStyleSheet(
            f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(colour, 1.0)};"
        )

    def _go_back(self) -> None:
        if self._stage == 2:
            self._set_stage(1)
        elif self._stage == 1:
            self._matcher and self._matcher.cancel()
            self._set_stage(0)

    def _go_next(self) -> None:
        if self._stage == 0:
            if not self._entries:
                self._set_info("先选择文件或粘贴链接。", error=True)
                return
            self._start_matching()
        elif self._stage == 1:
            self._apply()

    # ------------------------------------------------------------------ match
    def _start_matching(self) -> None:
        library = ctx().library
        client = ctx().client
        self._playlist_name = self.name_input.text().strip() or self._playlist_name
        self._matcher = PlaylistMatcher(client, library, self)
        self._matcher.row_changed.connect(self._on_row_changed)
        self._matcher.progress.connect(self._on_progress)
        self._matcher.finished.connect(self._on_finished)
        self.progress.setMaximum(max(1, len(self._entries)))
        self.progress.setValue(0)
        self._set_stage(1)
        self.next_button.setEnabled(False)
        self._set_next("匹配中…")
        strength = ("strict", "balanced", "loose")[max(0, min(2, self.strength.current()))]
        _remember("playlist.import_strength", strength)
        self._matcher.start(
            self._entries,
            online=self.online_toggle.isChecked(),
            verify=True,
            strength=strength,
        )
        # Bind the model only after start() has created the rows.
        self.model.set_rows(self._matcher.rows)

    def _on_row_changed(self, index: int) -> None:
        if 0 <= index < self.model.rowCount():
            self.model.dataChanged.emit(
                self.model.index(index, 0), self.model.index(index, 4)
            )
            self._refresh_counts()

    def _on_progress(self, done: int, total: int) -> None:
        if total and done >= total:
            self._set_next("开始导入")
            self.progress.setVisible(False)
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        self.progress.setVisible(done < total)
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        if self._matcher is None:
            return
        counts = self._matcher.counts()
        settled = bool(self._matcher.rows) and all(
            row.status != "pending" for row in self._matcher.rows
        )
        if settled:
            self._set_next("开始导入")
            self.progress.setVisible(False)
        parts = [f"{STATUS['local']} {counts['local']}"]
        parts.append(f"在线 {counts['online']}")
        if counts["unverified"]:
            parts.append(f"未验证 {counts['unverified']}")
        if counts["review"]:
            parts.append(f"待确认 {counts['review']}")
        if counts["unmatched"]:
            parts.append(f"未匹配 {counts['unmatched']}")
        if counts["skipped"]:
            parts.append(f"已跳过 {counts['skipped']}")
        self.counts_label.setText("  ·  ".join(parts))
        self.status_label.setText(f"{self._matcher.done} / {self._matcher.total}")

    def _on_finished(self) -> None:
        self.next_button.setEnabled(True)
        self._set_next("开始导入")
        self.status_label.setText(f"匹配完成：{self._matcher.done} / {self._matcher.total}")
        counts = self._matcher.counts()
        if counts["review"]:
            self.status_label.setText(
                f"还有 {counts['review']} 首待确认，双击可以换候选或跳过"
            )

    # ------------------------------------------------------------------ actions
    def _open_candidates(self, index) -> None:
        if self._matcher is None or not index.isValid():
            return
        row_index = index.row()
        row = self._matcher.rows[row_index]
        menu = PopupMenu(self)
        for candidate in row.candidates[:18]:
            track = candidate.track
            label = f"{track.title} · {track.artist}（{candidate.score}）"
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, i=row_index, t=track: self._choose(i, t)
            )
        if row.candidates:
            menu.addSeparator()
        search = menu.addAction("手动搜索…")
        search.triggered.connect(lambda: self._manual_search(row_index))
        if row.track is not None:
            clear = menu.addAction("清除匹配")
            clear.triggered.connect(lambda: self._choose(row_index, None))
        if row.skipped:
            unskip = menu.addAction("取消跳过")
            unskip.triggered.connect(lambda: self._unskip(row_index))
        else:
            skip = menu.addAction("跳过这首歌")
            skip.triggered.connect(lambda: self._skip(row_index))
        menu.exec(self._menu_anchor(index))

    def _menu_anchor(self, index) -> QPoint:
        """Place the candidate menu away from the click point.

        Double-clicking a row opens this menu; if it appeared under the cursor the
        second click would land on the first item. So offset it below-right of the
        cursor, flipping up when the screen has no room below.
        """
        from PySide6.QtGui import QCursor

        cursor = QCursor.pos()
        width, height = 340, 280
        screen = self.screen().availableGeometry() if self.screen() else None
        x = cursor.x() + 28
        y = cursor.y() + 30
        if screen is not None:
            if x + width > screen.right():
                x = max(screen.left() + 8, cursor.x() - width - 20)
            if y + height > screen.bottom():
                y = max(screen.top() + 8, cursor.y() - height - 20)
        return QPoint(x, y)

    def _choose(self, index: int, track) -> None:
        self._matcher.choose(index, track)
        self._on_row_changed(index)

    def _skip(self, index: int) -> None:
        self._matcher.skip(index)
        self._on_row_changed(index)

    def _unskip(self, index: int) -> None:
        self._matcher.unskip(index)
        self._on_row_changed(index)

    def _manual_search(self, index: int) -> None:
        text, ok = ask_text(self, "手动搜索", "输入歌曲名，或「歌手 歌名」", placeholder="例如：晴天 周杰伦")
        if not ok or not text.strip():
            return
        self._matcher.search(index, text)
        self._on_row_changed(index)

    # ------------------------------------------------------------------ apply
    def _adopt_all(self) -> None:
        matcher = self._matcher
        if matcher is None:
            return
        for index, row in enumerate(matcher.rows):
            if row.status == "review" and row.candidates:
                matcher.choose(index, row.candidates[0].track)
        self._refresh_counts()

    def _export_missing(self, rows) -> None:
        import csv
        from pathlib import Path

        from ..core.paths import data_dir

        target_dir = Path(data_dir()) / "exports"
        target_dir.mkdir(parents=True, exist_ok=True)
        name = (self.name_input.text().strip() or self._playlist_name or "playlist").replace("/", "-")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = target_dir / f"{name}-unmatched-{stamp}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["状态", "原始歌名", "歌手", "专辑", "候选数", "最佳候选", "说明"])
            for row in rows:
                if row.status in ("review", "unmatched", "pending", "skipped"):
                    best = row.candidates[0].track if row.candidates else None
                    writer.writerow([
                        row.status_label,
                        row.entry.title,
                        row.entry.artist,
                        row.entry.album,
                        len(row.candidates),
                        f"{best.title} - {best.artist}" if best else "",
                        row.note,
                    ])
        self.source_hint.setText(f"未导入清单已导出到 {path}")

    def _apply(self) -> None:
        if self._matcher is None:
            return
        rows = self._matcher.rows
        counts = self._matcher.counts()
        missing = counts["review"] + counts["unmatched"] + counts.get("pending", 0) + counts["skipped"]
        if missing:
            choice = choose(
                self,
                "还有未处理的歌曲",
                f"将导入 {counts['local'] + counts['online'] + counts['unverified']} 首；"
                f"{counts['review']} 首待确认、{counts['unmatched']} 首未匹配、"
                f"{counts['skipped']} 首已跳过不会被导入。\n\n"
                "可以先返回处理，也可以继续导入，或继续并导出未导入清单。",
                [
                    ("back", "返回处理"),
                    ("export", "导出清单并导入"),
                    ("proceed", "仍然导入"),
                ],
                kind="warning",
                accent="proceed",
            )
            if choice in (None, "back"):
                return
            if choice == "export":
                self._export_missing(rows)
        if False:  # kept for readability of the original guard
            return
        library = ctx().library
        name = self.name_input.text().strip() or self._playlist_name or "导入的歌单"
        existing = find_playlist(library, name)
        mode = "new"
        playlist_id = None
        if existing is not None:
            menu = PopupMenu(self)
            merge = menu.addAction(f"合并到「{existing.name}」（保留现有歌曲）")
            merge.triggered.connect(lambda: None)
            replace = menu.addAction("覆盖同名歌单（清空后重填）")
            replace.triggered.connect(lambda: None)
            create = menu.addAction("新建一个不同名的歌单")
            create.triggered.connect(lambda: None)
            chosen = menu.exec(self.next_button.mapToGlobal(QPoint(0, -menu.height() - 6)))
            if chosen is merge:
                mode = "merge"
                playlist_id = existing.id
            elif chosen is replace:
                mode = "replace"
                playlist_id = existing.id
            elif chosen is create:
                text, ok = ask_text(self, "新建歌单", "给导入的歌单起个名字", text=f"{name}（导入）")
                if not ok or not text.strip():
                    return
                name = text.strip()
                mode = "new"
            else:
                return
        try:
            outcome = apply_import(library, name, rows, mode=mode, playlist_id=playlist_id)
        except Exception as exc:  # noqa: BLE001
            log_exception("写入歌单失败", exc)
            notify(self, "导入失败", f"写入歌单时出错：{exc}", kind="error")
            return
        self._outcome = outcome
        self.done_detail.setText(
            f"「{outcome.playlist_name}」已导入 {outcome.added} 首"
            + (f"，重复 {outcome.duplicates} 首" if outcome.duplicates else "")
            + (f"，跳过 {outcome.skipped} 首" if outcome.skipped else "")
            + (f"，待确认未导入 {outcome.pending} 首" if outcome.pending else "")
            + (f"，未匹配 {outcome.unmatched} 首" if outcome.unmatched else "")
            + "。"
        )
        counts = self._matcher.counts() if self._matcher else {}
        self.done_detail.setText(
            self.done_detail.text()
            + f" 本地 {counts.get('local', 0)} 首 · 在线 {counts.get('online', 0)} 首。"
        )
        self._set_stage(2)
        self.imported.emit(outcome.playlist_id, outcome.playlist_name)

    def _open_playlist(self) -> None:
        outcome = getattr(self, "_outcome", None)
        if outcome is None:
            return
        window = ctx().window
        self.accept()
        if window is not None:
            window.navigate(f"playlist:{outcome.playlist_id}")

    # ------------------------------------------------------------------ misc
    def reject(self) -> None:  # noqa: D401
        if self._matcher is not None:
            self._matcher.cancel()
        super().reject()
