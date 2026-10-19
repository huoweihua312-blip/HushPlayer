"""下载中心：进行中的下载、失败重试与下载历史。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ...core.theme import css_rgba, rgba, theme
from ...model.track import format_bytes
from ...services.downloads import (
    STATE_CANCELLED,
    STATE_DONE,
    STATE_DOWNLOADING,
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RESOLVING,
)
from ..context import ctx
from ..widgets.common import IconButton, TextButton
from ..widgets.cover import CoverWidget
from .page import Page, PageHeader


class _Progress(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(3)

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        if abs(value - self._value) > 0.002:
            self._value = value
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(palette.text, 0.10))
        painter.drawRoundedRect(rect, 1.5, 1.5)
        if self._value > 0:
            fill = QRectF(rect)
            fill.setWidth(rect.width() * self._value)
            painter.setBrush(rgba(palette.accent, 0.90))
            painter.drawRoundedRect(fill, 1.5, 1.5)
        painter.end()


class _DownloadRow(QWidget):
    cancelled = Signal(str)
    retried = Signal(str)

    def __init__(self, *, job=None, item: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._item = item
        self.setFixedHeight(66)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(12)

        track = job.track if job is not None else None
        self.cover = CoverWidget(42, radius=7)
        if track is not None:
            self.cover.set_track(track)
        layout.addWidget(self.cover, 0, Qt.AlignVCenter)

        info = QVBoxLayout()
        info.setContentsMargins(0, 4, 0, 4)
        info.setSpacing(3)
        self.title_label = QLabel()
        self.title_label.setFont(theme().font(9.8, 600))
        self.subtitle = QLabel()
        self.subtitle.setFont(theme().font(8.4))
        self.progress = _Progress()
        info.addWidget(self.title_label)
        info.addWidget(self.subtitle)
        info.addWidget(self.progress)
        layout.addLayout(info, 1)

        self.cancel_button = IconButton("close", size=28, icon_size=13, tooltip="取消下载")
        self.cancel_button.clicked.connect(lambda: self.cancelled.emit(job.id if job else ""))
        self.retry_button = TextButton("重试", icon_name="refresh", size=28)
        self.retry_button.clicked.connect(lambda: self.retried.emit(job.id if job else ""))
        self.open_button = IconButton("folder", size=28, icon_size=14, tooltip="在资源管理器中显示")
        self.open_button.clicked.connect(self._reveal)
        self.remove_button = IconButton("trash", size=28, icon_size=14, tooltip="从列表移除")
        for button in (self.cancel_button, self.retry_button, self.remove_button, self.open_button):
            layout.addWidget(button, 0, Qt.AlignVCenter)
        self.refresh()

    def _reveal(self) -> None:
        path = ""
        if self._job is not None:
            path = self._job.path
        elif self._item is not None:
            path = str(self._item.get("path", ""))
        if path:
            from ..menus import reveal_in_explorer

            reveal_in_explorer(path)

    def refresh(self) -> None:
        palette = theme().palette
        self.title_label.setStyleSheet(f"color: {css_rgba(palette.text, 1.0)};")
        self.subtitle.setStyleSheet(f"color: {css_rgba(palette.text, 0.55)};")
        job = self._job
        if job is not None:
            self.title_label.setText(job.title)
            state = job.state
            if state == STATE_DOWNLOADING:
                size = (
                    f"{format_bytes(job.downloaded)} / {format_bytes(job.total)}"
                    if job.total
                    else format_bytes(job.downloaded)
                )
                self.subtitle.setText(f"下载中 · {size}")
                self.progress.set_value(job.progress)
                self.progress.show()
            elif state in (STATE_QUEUED, STATE_RESOLVING):
                self.subtitle.setText("正在解析下载地址…")
                self.progress.set_value(0.0)
                self.progress.show()
            elif state == STATE_DONE:
                self.subtitle.setText(f"已完成 · {format_bytes(job.downloaded or job.total)}")
                self.progress.set_value(1.0)
                self.progress.hide()
            elif state == STATE_CANCELLED:
                self.subtitle.setText("已取消")
                self.progress.hide()
            else:
                self.subtitle.setText(f"下载失败 · {job.error or '未知错误'}")
                self.progress.hide()
            active = state in (STATE_QUEUED, STATE_RESOLVING, STATE_DOWNLOADING)
            self.cancel_button.setVisible(active)
            self.retry_button.setVisible(state in (STATE_FAILED, STATE_CANCELLED))
            self.remove_button.setVisible(not active)
            self.open_button.setVisible(state == STATE_DONE and bool(job.path))
        else:
            item = self._item or {}
            self.title_label.setText(str(item.get("title", "未知歌曲")))
            artist = str(item.get("artist", ""))
            size = format_bytes(int(item.get("size", 0) or 0))
            self.subtitle.setText(f"{artist} · {size}" if artist else size)
            self.progress.hide()
            self.cancel_button.setVisible(False)
            self.retry_button.setVisible(False)
            self.remove_button.setVisible(False)
            self.open_button.setVisible(bool(item.get("path")))


class DownloadsPage(Page):
    route = "downloads"
    title = "下载"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.header = PageHeader("下载", "查看进行中的下载与历史")
        self.content_layout.addWidget(self.header)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self.open_folder_button = TextButton("打开文件夹", icon_name="folder", size=30)
        self.open_folder_button.clicked.connect(self._open_folder)
        self.clear_button = TextButton("清空已完成", icon_name="trash", size=30)
        self.clear_button.clicked.connect(self._clear_finished)
        actions_layout.addWidget(self.clear_button)
        actions_layout.addWidget(self.open_folder_button)
        self.header.add_action(actions)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._container = QWidget()
        self._container.setStyleSheet("background:transparent;")
        self._body = QVBoxLayout(self._container)
        self._body.setContentsMargins(0, 4, 0, 12)
        self._body.setSpacing(8)
        self._scroll.setWidget(self._container)
        self.content_layout.addWidget(self._scroll, 1)

        self._active_title = QLabel("进行中")
        self._active_title.setFont(theme().font(11, 600))
        self._active_box = QVBoxLayout()
        self._active_box.setContentsMargins(0, 0, 0, 0)
        self._active_box.setSpacing(2)
        self._history_title = QLabel("下载历史")
        self._history_title.setFont(theme().font(11, 600))
        self._history_box = QVBoxLayout()
        self._history_box.setContentsMargins(0, 0, 0, 0)
        self._history_box.setSpacing(2)
        self._body.addWidget(self._active_title)
        self._body.addLayout(self._active_box)
        self._body.addSpacing(8)
        self._body.addWidget(self._history_title)
        self._body.addLayout(self._history_box)
        self._body.addStretch(1)

        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(150)
        self._reload_timer.timeout.connect(self.reload)
        self._wired = False
        self._rows: dict[str, _DownloadRow] = {}

    # ------------------------------------------------------------------ 生命周期
    def _wire(self) -> None:
        if self._wired:
            return
        downloads = ctx().downloads
        if downloads is None:
            return
        downloads.jobs_changed.connect(self._schedule_reload)
        downloads.job_updated.connect(self._on_job_updated)
        downloads.job_finished.connect(lambda _job: self._schedule_reload())
        self._wired = True

    def on_show(self, payload=None) -> None:  # noqa: ANN001
        self._wire()
        self.reload()

    def _on_job_updated(self, job) -> None:  # noqa: ANN001
        """Refresh just the affected row; rebuilding the list is only needed
        when jobs appear/disappear."""
        row = self._rows.get(job.id)
        if row is None:
            self._schedule_reload()
            return
        row.refresh()
        self._update_header()

    def _update_header(self) -> None:
        downloads = ctx().downloads
        if downloads is None:
            return
        pending = [job for job in downloads.jobs if job.state != STATE_DONE]
        history = downloads.history()
        active_count = len(downloads.active())
        failed = len([job for job in pending if job.state in (STATE_FAILED, STATE_CANCELLED)])
        parts = []
        if active_count:
            parts.append(f"{active_count} 个进行中")
        if failed:
            parts.append(f"{failed} 个待处理")
        if history:
            parts.append(f"已下载 {len(history)} 首")
        self.header.set_subtitle(" · ".join(parts) if parts else "还没有下载任务")

    def _schedule_reload(self) -> None:
        # The page lives in a QStackedWidget; isVisible() can lag behind the
        # first job_updated signal, so always schedule the refresh.
        self._reload_timer.start()

    def refresh_theme(self) -> None:
        super().refresh_theme()

    # ------------------------------------------------------------------ 内容
    def reload(self) -> None:
        self._wire()
        downloads = ctx().downloads
        if downloads is None:
            return
        active = downloads.active()
        history = downloads.history()
        # Failed/cancelled jobs are not "active" but must stay visible so the
        # user can retry them; only finished jobs move to the history list.
        pending = [job for job in downloads.jobs if job.state != STATE_DONE]
        self._rows.clear()
        self._clear_layout(self._active_box)
        self._clear_layout(self._history_box)

        for job in pending:
            row = _DownloadRow(job=job)
            row.cancelled.connect(downloads.cancel)
            row.retried.connect(downloads.retry)
            row.remove_button.clicked.connect(lambda _=False, jid=job.id: downloads.remove(jid))
            self._active_box.addWidget(row)
            self._rows[job.id] = row
        self._active_title.setVisible(bool(pending))
        if not pending:
            hint = QLabel("没有正在下载的歌曲")
            hint.setFont(theme().font(9))
            hint.setStyleSheet(f"color: {css_rgba(theme().palette.text, 0.5)};")
            self._active_box.addWidget(hint)

        for item in history[:60]:
            row = _DownloadRow(item=item)
            self._history_box.addWidget(row)
        self._history_title.setVisible(bool(history))
        if not history:
            hint = QLabel("下载完成的歌曲会出现在这里")
            hint.setFont(theme().font(9))
            hint.setStyleSheet(f"color: {css_rgba(theme().palette.text, 0.5)};")
            self._history_box.addWidget(hint)

        self._update_header()
        self.clear_button.setEnabled(bool(history))

    def _clear_layout(self, layout) -> None:  # noqa: ANN001
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    # ------------------------------------------------------------------ 操作
    def _open_folder(self) -> None:
        downloads = ctx().downloads
        if downloads is not None:
            downloads.open_folder()

    def _clear_finished(self) -> None:
        downloads = ctx().downloads
        if downloads is not None:
            downloads.clear_finished()
            self._schedule_reload()
