"""Playlist import wizard: source → fetch → match → confirm.

A modal dialog on purpose (it owns a long-running async job and must not be
reopened twice), but it is styled with the app's own widgets so it looks like a
page rather than a system box.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QStyle,
    QStackedWidget,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..core.logging_setup import log_exception
from ..core.theme import css_rgba, qcolor, rgba, theme
from ..model.track import format_duration
from ..online import matching
from ..services.playlist_import import PlaylistEntry, parse_playlist, parse_playlist_text
from ..services.playlist_link import PLATFORM_LABELS, PlaylistLinkError, detect_platform, fetch_link
from ..services.playlist_matcher import STATUS, MatchRow, PlaylistMatcher, apply_import, find_playlist
from .context import ctx
from .widgets.common import IconButton, TextButton
from .widgets.popup import PopupMenu

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


class PlaylistImportDialog(QDialog):
    imported = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入歌单")
        self.setModal(True)
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
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel("导入歌单")
        self.subtitle_label = QLabel("从文件或其他音乐平台导入，并匹配到你的本地与在线音源")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        header.addLayout(titles, 1)
        self.close_button = IconButton("close", size=32, icon_size=16, tooltip="关闭")
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button, 0, Qt.AlignTop)
        root.addLayout(header)

        self.steps = _StepBar()
        root.addWidget(self.steps)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_source_page())
        self.stack.addWidget(self._build_match_page())
        self.stack.addWidget(self._build_done_page())
        root.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        footer.addWidget(self.status_label, 1)
        self.cancel_button = TextButton("取消", size=32)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        self.back_button = TextButton("上一步", size=32)
        self.back_button.clicked.connect(self._go_back)
        footer.addWidget(self.back_button)
        self.next_button = TextButton("下一步", icon_name="chevron_right", size=32, accent=True)
        self.next_button.clicked.connect(self._go_next)
        footer.addWidget(self.next_button)
        root.addLayout(footer)

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
        layout.addWidget(self.table, 1)

        hint = QLabel("双击一行可换候选 / 手动搜索 / 跳过；只导入「本地」「在线已匹配」与「在线未验证」的行。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
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
    def _apply_theme(self, *_args) -> None:
        palette = theme().palette
        self.setStyleSheet(
            f"QDialog {{ background: {palette.window}; }}"
            f"QLabel {{ color: {palette.text}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size:{theme().pt(17):.1f}pt; font-weight:700; color:{palette.text};"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.5)};"
        )
        self.file_hint.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.45)};")
        self.source_info.setStyleSheet(f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.75)};")
        self.source_hint.setStyleSheet(f"font-size:{theme().pt(8.8):.1f}pt; color:{css_rgba(palette.text, 0.45)};")
        self.source_guide.setStyleSheet(
            f"font-size:{theme().pt(9.4):.1f}pt; color:{css_rgba(palette.text, 0.38)};"
            f" padding: {theme().scaled(18, factor=0.8)}px {theme().scaled(22, factor=0.8)}px;"
            f" border: 1px dashed {css_rgba(palette.text, 0.16)};"
            f" border-radius: {theme().scaled(12, factor=0.6)}px;"
        )
        self.counts_label.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.55)};")
        self.status_label.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(palette.text, 0.55)};")
        self.done_title.setStyleSheet(f"font-size:{theme().pt(16):.1f}pt; font-weight:700; color:{palette.text};")
        self.done_detail.setStyleSheet(f"font-size:{theme().pt(9.6):.1f}pt; color:{css_rgba(palette.text, 0.7)};")
        self.progress.setStyleSheet(
            f"QProgressBar {{ background:{css_rgba(palette.text, 0.10)}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{palette.accent}; border-radius:3px; }}"
        )
        self.table.setStyleSheet("QTableView { background: transparent; border: none; }")

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
            self.next_button.setText("下一步")
        elif stage == 1:
            self.next_button.setText("开始导入" if self._matcher and self._matcher.total else "下一步")
        elif stage == 2:
            self.next_button.setVisible(False)

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
        self.next_button.setText("匹配中…")
        self._matcher.start(self._entries, online=self.online_toggle.isChecked(), verify=True)
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
            self.next_button.setText("开始导入")
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
            self.next_button.setText("开始导入")
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
        self.next_button.setText("开始导入")
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
        for candidate in row.candidates[:5]:
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
        position = self.table.viewport().mapToGlobal(
            self.table.visualRect(index).bottomLeft() + QPoint(0, 2)
        )
        menu.exec(position)

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
        text, ok = QInputDialog.getText(self, "手动搜索", "输入歌曲名或「歌手 歌名」：")
        if not ok or not text.strip():
            return
        self._matcher.search(index, text)
        self._on_row_changed(index)

    # ------------------------------------------------------------------ apply
    def _apply(self) -> None:
        if self._matcher is None:
            return
        rows = self._matcher.rows
        if self._matcher.counts()["review"]:
            answer = QMessageBox.question(
                self,
                "还有待确认的歌曲",
                "还有待确认的歌曲没有处理。继续导入会跳过它们，确定继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
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
                text, ok = QInputDialog.getText(self, "新建歌单", "歌单名称：", text=f"{name}（导入）")
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
            QMessageBox.warning(self, "导入失败", f"写入歌单时出错：{exc}")
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
