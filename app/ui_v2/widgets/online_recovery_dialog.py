"""Candidate picker used when online recovery finds multiple close matches."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.widgets.online_presentation import style_action, style_caption
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.styles import build_dialog_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail


class _CandidateRow(QFrame):
    """A compact, fixed-height candidate row with a clear visual hierarchy."""

    def __init__(self, track: OnlineTrack, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("onlineRecoveryCandidateRow")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_label = ElidedLabel(self)
        self.title_label.set_full_text(track.title)
        self.detail_label = ElidedLabel(self)
        self.detail_label.set_full_text(
            f"{track.artist} · {track.album}"
        )
        self.title_label.setAccessibleName("歌曲标题和歌手")
        self.detail_label.setAccessibleName("专辑、来源和时长")
        self.artwork = ArtworkThumbnail(theme, self, size=38)
        self.artwork.set_track(track.as_track())
        text = QVBoxLayout()
        text.setSpacing(5)
        text.addWidget(self.title_label)
        text.addWidget(self.detail_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(14)
        layout.addWidget(self.artwork)
        layout.addLayout(text, 1)
        self.source_label = ElidedLabel(self)
        self.source_label.set_full_text(track.source_name)
        self.source_label.setFixedWidth(116)
        self.source_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.duration_label = QLabel(format_duration(track.duration_ms), self)
        self.duration_label.setFixedWidth(44)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.source_label)
        layout.addWidget(self.duration_label)
        style_caption(self.source_label, theme, subtle=True)
        style_caption(self.duration_label, theme, subtle=True)
        self.setMinimumHeight(70)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 400; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )


class OnlineRecoveryCandidateDialog(QDialog):
    """Choose a recoverable online source without changing song identity."""

    def __init__(self, candidates: tuple[OnlineTrack, ...], theme: Theme, parent=None, *, original_track: Track | None = None) -> None:
        super().__init__(parent)
        theme = get_theme(theme.mode, profile="b2")
        self._candidates = tuple(candidates)
        self.selected_track: OnlineTrack | None = None
        self.setWindowTitle("选择在线版本")
        self.setObjectName("onlineRecoveryCandidateDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumSize(640, 560)
        self.resize(760, 636)
        self._apply_theme(theme)

        self.surface = QFrame(self)
        self.surface.setObjectName("onlineRecoveryDialogSurface")

        title_bar = QFrame(self.surface)
        title_bar.setObjectName("onlineRecoveryTitleBar")
        window_title = QLabel("修复歌曲的播放来源" if self._candidates else "暂未找到可用版本", title_bar)
        window_title.setObjectName("onlineRecoveryWindowTitle")
        self.close_button = QToolButton(title_bar)
        self.close_button.setObjectName("onlineRecoveryCloseButton")
        self.close_button.setIcon(icon("window_close", theme))
        self.close_button.setIconSize(QSize(16, 16))
        self.close_button.setToolTip("关闭")
        self.close_button.setAccessibleName("关闭在线版本选择")
        self.close_button.clicked.connect(self.reject)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(28, 24, 20, 4)
        title_bar_layout.setSpacing(10)
        title_bar_layout.addWidget(window_title)
        title_bar_layout.addStretch(1)
        title_bar_layout.addWidget(self.close_button)

        content = QWidget(self.surface)
        eyebrow = QLabel("播放恢复", content)
        eyebrow.setObjectName("onlineRecoveryEyebrow")
        title = QLabel("修复歌曲的播放来源" if self._candidates else "暂未找到可用版本", content)
        title.setObjectName("onlineRecoveryTitle")
        detail = QLabel(
            f"请选择最符合的一首。只会替换播放来源，歌单位置、收藏和本地信息都会保留（{len(self._candidates)} 个候选）。",
            content,
        )
        detail.setObjectName("onlineRecoveryDetail")
        detail.setWordWrap(True)

        self.list_widget = QListWidget(content)
        self.list_widget.setObjectName("onlineRecoveryCandidateList")
        self.list_widget.setAccessibleName("在线候选歌曲")
        self.list_widget.setAccessibleDescription("使用方向键选择版本，按 Enter 替换播放来源并播放")
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(2)
        self.list_widget.itemActivated.connect(lambda _item: self._accept_selected())
        for track in self._candidates:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setToolTip(self._label_for(track))
            row = _CandidateRow(track, theme, self.list_widget)
            item.setSizeHint(QSize(0, 76))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        else:
            self.list_widget.setEnabled(False)

        self.selection_surface = QFrame(content)
        self.selection_surface.setObjectName("onlineRecoverySelectionSurface")
        selection_caption = QLabel("当前选择", self.selection_surface)
        selection_caption.setObjectName("onlineRecoverySelectionCaption")
        self.selection_label = ElidedLabel(self.selection_surface)
        self.selection_label.setAccessibleName("当前选中的在线版本")
        self.selection_label.setMinimumHeight(24)
        selection_layout = QHBoxLayout(self.selection_surface)
        selection_layout.setContentsMargins(0, 7, 0, 7)
        style_caption(self.selection_label, theme)
        selection_layout.setSpacing(10)
        selection_layout.addWidget(selection_caption)
        selection_layout.addWidget(self.selection_label, 1)

        footer = QFrame(self.surface)
        footer.setObjectName("onlineRecoveryFooter")
        cancel = QPushButton("取消", footer)
        cancel.setAccessibleName("取消在线版本选择")
        cancel.clicked.connect(self.reject)
        play = QPushButton("替换播放来源并播放", footer)
        play.setAccessibleName("替换播放来源并播放")
        play.setProperty("role", "primary")
        play.setMinimumWidth(188)
        play.setDefault(True)
        play.setEnabled(bool(self._candidates))
        play.clicked.connect(self._accept_selected)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(28, 12, 28, 22)
        footer_layout.setSpacing(8)
        self.keyboard_hint = QLabel("↑ ↓ 选择 · Enter 确认", footer)
        style_caption(self.keyboard_hint, theme, subtle=True)
        footer_layout.addWidget(self.keyboard_hint)
        footer_layout.addStretch(1)
        style_action(cancel, theme)
        style_action(play, theme, primary=True)
        footer_layout.addWidget(cancel)
        footer_layout.addWidget(play)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 12, 28, 8)
        content_layout.setSpacing(8)
        eyebrow.hide()
        title.hide()
        content_layout.addWidget(detail)
        content_layout.addSpacing(16)
        self.original_surface = QFrame(content)
        self.original_surface.setObjectName("onlineRecoveryOriginal")
        original_layout = QHBoxLayout(self.original_surface)
        original_layout.setContentsMargins(0, 0, 0, 18)
        original_layout.setSpacing(14)
        self.original_artwork = ArtworkThumbnail(theme, self.original_surface, size=44)
        self.original_artwork.set_track(original_track)
        self.original_title = ElidedLabel(self.original_surface)
        self.original_title.set_full_text(original_track.title if original_track else "原歌曲")
        self.original_metadata = ElidedLabel(self.original_surface)
        self.original_metadata.set_full_text(
            f"{original_track.artist} · {original_track.album}" if original_track else "仅替换播放来源，保留歌曲信息"
        )
        identity_layout = QVBoxLayout()
        identity_layout.setSpacing(4)
        identity_layout.addWidget(self.original_title)
        identity_layout.addWidget(self.original_metadata)
        original_layout.addWidget(self.original_artwork)
        original_layout.addLayout(identity_layout, 1)
        self.original_title.setStyleSheet(f"font-size: 15px; color: {theme.colors.primary_text};")
        style_caption(self.original_metadata, theme)
        content_layout.addWidget(self.original_surface)
        self.original_surface.setVisible(original_track is not None)
        content_layout.addSpacing(8)
        content_layout.addWidget(self.list_widget, 1)
        content_layout.addWidget(self.selection_surface)

        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        surface_layout.addWidget(title_bar)
        surface_layout.addWidget(content, 1)
        surface_layout.addWidget(footer)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.surface)
        self.list_widget.currentRowChanged.connect(self._sync_selection_label)
        self._sync_selection_label(self.list_widget.currentRow())
        self.list_widget.setFocus()

    def _apply_theme(self, theme: Theme) -> None:
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            build_dialog_stylesheet(theme)
            + f"""
            QDialog#onlineRecoveryCandidateDialog {{
                background: {colors.app_background};
                border: 0;
                border-radius: 10px;
            }}
            QFrame#onlineRecoveryDialogSurface {{
                background: {colors.surface_elevated};
                border: 0;
                border-radius: 10px;
            }}
            QFrame#onlineRecoveryTitleBar {{
                min-height: 40px;
                background: transparent;
                border: 0;
                border-bottom: 0;
                border-top-left-radius: {metrics.radius_lg}px;
                border-top-right-radius: {metrics.radius_lg}px;
            }}
            QLabel#onlineRecoveryWindowTitle {{
                color: {colors.primary_text};
                font-size: 22px;
                font-weight: 600;
            }}
            QToolButton#onlineRecoveryCloseButton {{
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                padding: 0;
                border: 0;
                border-radius: {metrics.radius_sm}px;
                background: transparent;
            }}
            QToolButton#onlineRecoveryCloseButton:hover {{ background: {colors.hover_background}; }}
            QLabel#onlineRecoveryEyebrow {{
                color: {colors.accent};
                font-size: {theme.fonts.caption}px;
                font-weight: 600;
            }}
            QLabel#onlineRecoveryTitle {{
                color: {colors.primary_text};
                font-size: {theme.fonts.section_title}px;
                font-weight: 600;
            }}
            QLabel#onlineRecoveryDetail {{ color: {colors.secondary_text}; font-size: 13px; }}
            QFrame#onlineRecoveryOriginal {{ background: transparent; border: 0; border-bottom: 1px solid {colors.divider}; }}
            QListWidget#onlineRecoveryCandidateList {{
                padding: 0;
                border: 0;
                border-radius: {metrics.radius_md}px;
                background: transparent;
            }}
            QListWidget#onlineRecoveryCandidateList::item {{
                margin: 1px 0;
                padding: 0;
                border: 1px solid transparent;
                border-radius: {metrics.radius_sm}px;
            }}
            QFrame#onlineRecoveryCandidateRow {{
                background: transparent;
                border: 0;
            }}
            QListWidget#onlineRecoveryCandidateList::item:selected {{
                background: {colors.selected_background};
                border: 1px solid {colors.accent};
            }}
            QFrame#onlineRecoverySelectionSurface {{
                background: transparent;
                border: 0;
                border-radius: {metrics.radius_sm}px;
            }}
            QLabel#onlineRecoverySelectionCaption {{
                color: {colors.text_tertiary};
                font-size: {theme.fonts.caption}px;
                font-weight: 600;
            }}
            QFrame#onlineRecoveryFooter {{
                background: transparent;
                border: 0;
                border-top: 0;
                border-bottom-left-radius: {metrics.radius_lg}px;
                border-bottom-right-radius: {metrics.radius_lg}px;
            }}
            """
        )

    @staticmethod
    def _label_for(track: OnlineTrack) -> str:
        duration = format_duration(track.duration_ms)
        return f"{track.title}  —  {track.artist}\n{track.album} · {track.source_name} · {duration}"

    def _accept_selected(self) -> None:
        item = self.list_widget.currentItem()
        track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(track, OnlineTrack):
            self.selected_track = track
            self.accept()

    def _sync_selection_label(self, row: int) -> None:
        if not (0 <= int(row) < len(self._candidates)):
            self.selection_label.set_full_text("没有可用的在线版本")
            self.selection_label.setToolTip("")
            return
        track = self._candidates[int(row)]
        text = (
            f"第 {int(row) + 1}/{len(self._candidates)} 项 · "
            f"已选择：{track.title} · {track.source_name} · {format_duration(track.duration_ms)}"
        )
        self.selection_label.set_full_text(text)
        self.selection_label.setToolTip(text)
