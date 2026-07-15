import os
import hashlib
import json
import random
import re
import shutil
import sys
import time
from copy import deepcopy
from pathlib import Path

import requests
from mutagen import File as MutagenFile
from app.models.media_item import MediaItem
from app.models.playback_queue_item import PlaybackQueueItem
from app.core.app_paths import AppPaths
from app.services.lyrics_cache import LyricsCache
from app.services.online_artwork_service import OnlineArtworkService
from app.services.online_download_manager import OnlineDownloadManager
from app.services.online_lyrics_service import OnlineLyricsService
from app.services.online_source_client import OnlineSourceClient
from app.services.playlist_membership import PlaylistMembership
from app.services.playback_queue import PlaybackQueue
from app.services.remote_track_store import RemoteTrackStore, RemoteTrackStoreError
from app.services.source_registry import SourceRegistryManager
from app.services.unified_search_service import UnifiedSearchService
from app.ui.custom_source_manager_page import CustomSourceManagerPage
from app.ui.library_page import LibraryPage
from app.ui.media_interaction_controller import MediaInteractionController
from app.ui.search_page import SearchPage
from app.ui.track_list_view import SearchEntryLineEdit
from PySide6.QtCore import QEasingCurve, QEvent, QItemSelectionModel, QObject, QPropertyAnimation, QRectF, QRunnable, QSize, Qt, QThread, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTextEdit,
    QToolTip,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)


AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
}


# 轻量深色主题 token：供应用 Palette、通用弹窗和主窗口精细 QSS 共用。
DARK_THEME_TOKENS = {
    "app_bg": "#0d0f14",
    "shell_bg": "#141821",
    "sidebar_bg": "#10131a",
    "panel_bg": "#151922",
    "card_bg": "#151922",
    "card_bg_alt": "#1a1f2b",
    "card_bg_high": "#202631",
    "text": "#f3f4f6",
    "text_secondary": "#b5bbc7",
    "text_muted": "#8a92a3",
    "text_weak": "#8a92a3",
    "text_disabled": "#7b8494",
    "placeholder": "#7f8898",
    "border": "#2a303b",
    "border_strong": "#3a4352",
    "hover": "#202631",
    "active": "#252c3a",
    "accent": "#4c8dff",
    "accent_soft": "rgba(76, 141, 255, 0.18)",
    "danger": "#e15b64",
}


def create_dark_palette() -> QPalette:
    t = DARK_THEME_TOKENS
    palette = QPalette()

    role_colors = {
        QPalette.ColorRole.Window: t["app_bg"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["panel_bg"],
        QPalette.ColorRole.AlternateBase: t["card_bg_alt"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["card_bg_alt"],
        QPalette.ColorRole.ButtonText: t["text_secondary"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: t["card_bg_alt"],
        QPalette.ColorRole.ToolTipText: t["text"],
        QPalette.ColorRole.PlaceholderText: t["placeholder"],
        QPalette.ColorRole.Link: t["accent"],
    }

    for role, color in role_colors.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(color))

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["text_disabled"]))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(t["panel_bg"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(t["app_bg"]))
    return palette


def build_dark_dialog_qss() -> str:
    t = DARK_THEME_TOKENS
    return f"""
    QDialog, QMessageBox, QInputDialog {{
        background: {t['app_bg']};
        color: {t['text']};
        font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
    }}
    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{
        background: transparent;
        color: {t['text_secondary']};
    }}
    QDialog QLabel:disabled, QDialog QCheckBox:disabled,
    QDialog QRadioButton:disabled {{ color: {t['text_disabled']}; }}
    QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit {{
        background: {t['panel_bg']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 10px;
        padding: 8px 10px;
        selection-background-color: {t['accent']};
        selection-color: {t['text']};
    }}
    QDialog QLineEdit:focus, QDialog QTextEdit:focus,
    QDialog QPlainTextEdit:focus {{
        border: 1px solid {t['accent']};
        background: {t['card_bg_alt']};
    }}
    QDialog QLineEdit:disabled, QDialog QTextEdit:disabled,
    QDialog QPlainTextEdit:disabled {{
        background: {t['app_bg']};
        color: {t['text_disabled']};
        border-color: {t['border']};
    }}
    QDialog QLineEdit[readOnly="true"], QDialog QTextEdit[readOnly="true"],
    QDialog QPlainTextEdit[readOnly="true"] {{
        background: {t['app_bg']};
        color: {t['text_muted']};
    }}
    QDialog QComboBox {{
        background: {t['panel_bg']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 10px;
        padding: 7px 10px;
    }}
    QDialog QComboBox:hover, QDialog QComboBox:focus {{ border-color: {t['border_strong']}; }}
    QDialog QComboBox:disabled {{
        background: {t['app_bg']};
        color: {t['text_disabled']};
    }}
    QDialog QComboBox QAbstractItemView {{
        background: {t['card_bg_alt']};
        color: {t['text']};
        border: 1px solid {t['border_strong']};
        outline: none;
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
    }}
    QDialog QCheckBox, QDialog QRadioButton {{
        background: transparent;
        color: {t['text_secondary']};
        spacing: 8px;
    }}
    QDialog QListWidget, QDialog QTreeWidget, QDialog QTableWidget {{
        background: {t['panel_bg']};
        color: {t['text']};
        alternate-background-color: {t['card_bg_alt']};
        border: 1px solid {t['border']};
        outline: none;
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
    }}
    QDialog QListWidget::item:hover, QDialog QTreeWidget::item:hover,
    QDialog QTableWidget::item:hover {{ background: {t['hover']}; }}
    QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {{
        background: {t['card_bg_alt']};
        color: {t['text_secondary']};
        border: 1px solid {t['border']};
        border-radius: 10px;
        padding: 8px 14px;
        min-width: 72px;
    }}
    QDialog QPushButton:hover, QMessageBox QPushButton:hover,
    QInputDialog QPushButton:hover {{
        background: {t['hover']};
        color: {t['text']};
        border-color: {t['border_strong']};
    }}
    QDialog QPushButton:pressed, QMessageBox QPushButton:pressed,
    QInputDialog QPushButton:pressed {{ background: {t['active']}; }}
    QDialog QPushButton:disabled, QMessageBox QPushButton:disabled,
    QInputDialog QPushButton:disabled {{
        background: {t['panel_bg']};
        color: {t['text_disabled']};
        border-color: {t['border']};
    }}
    QPushButton#dangerDialogButton {{
        background: rgba(225, 91, 100, 0.14);
        color: #f3b7bc;
        border-color: rgba(225, 91, 100, 0.30);
    }}
    QPushButton#dangerDialogButton:hover {{
        background: rgba(225, 91, 100, 0.24);
        color: {t['text']};
        border-color: {t['danger']};
    }}
    QDialog QScrollArea, QDialog QScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    """


def build_dark_application_fallback_qss() -> str:
    t = DARK_THEME_TOKENS
    return build_dark_dialog_qss() + f"""
    QMenu {{
        background: {t['card_bg_alt']};
        color: {t['text_secondary']};
        border: 1px solid {t['border_strong']};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 8px 24px; border-radius: 7px; }}
    QMenu::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}
    QMenu::item:disabled {{ background: transparent; color: {t['text_disabled']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 6px 8px; }}
    QToolTip {{
        background: {t['card_bg_alt']};
        color: {t['text']};
        border: 1px solid {t['border_strong']};
        border-radius: 8px;
        padding: 6px 8px;
    }}
    """


def apply_dark_application_theme(app: QApplication) -> None:
    if app.property("hushDarkThemeApplied"):
        return

    app.setPalette(create_dark_palette())
    existing_qss = app.styleSheet()
    app.setStyleSheet(f"{existing_qss}\n{build_dark_application_fallback_qss()}")
    app.setProperty("hushDarkThemeApplied", True)


def apply_dark_dialog_style(dialog: QDialog, extra_qss: str = "") -> None:
    dialog.setPalette(create_dark_palette())
    dialog.setStyleSheet(f"{build_dark_dialog_qss()}\n{extra_qss}")


def _color_luminance(color: QColor) -> float:
    channels = []

    for value in (color.red(), color.green(), color.blue()):
        channel = value / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)

    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(first: QColor, second: QColor) -> float:
    lighter = max(_color_luminance(first), _color_luminance(second))
    darker = min(_color_luminance(first), _color_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def _composite_color(color: QColor, background: QColor) -> QColor:
    alpha = color.alphaF()

    if alpha >= 0.999:
        return QColor(color)

    return QColor.fromRgbF(
        color.redF() * alpha + background.redF() * (1.0 - alpha),
        color.greenF() * alpha + background.greenF() * (1.0 - alpha),
        color.blueF() * alpha + background.blueF() * (1.0 - alpha),
        1.0,
    )


def audit_dark_ui_contrast(roots: QWidget | list[QWidget]) -> list[str]:
    """开发/离屏测试使用；正常运行不会主动调用或打印。"""
    root_widgets = roots if isinstance(roots, list) else [roots]
    text_widgets = (QLabel, QPushButton, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QCheckBox, QRadioButton, QAbstractItemView, QMenu)
    input_widgets = (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractItemView)
    warnings = []

    for root in root_widgets:
        candidates = [root, *root.findChildren(QWidget)]
        root_palette = root.palette()
        root_active_window = root_palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
        root_disabled_window = root_palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window)

        for widget in candidates:
            if not isinstance(widget, text_widgets):
                continue

            palette = widget.palette()

            if isinstance(widget, input_widgets):
                foreground_role = QPalette.ColorRole.Text
                background_role = QPalette.ColorRole.Base
            elif isinstance(widget, QPushButton):
                foreground_role = QPalette.ColorRole.ButtonText
                background_role = QPalette.ColorRole.Button
            else:
                foreground_role = QPalette.ColorRole.WindowText
                background_role = QPalette.ColorRole.Window

            active_text = palette.color(QPalette.ColorGroup.Active, foreground_role)
            active_background = palette.color(QPalette.ColorGroup.Active, background_role)
            disabled_text = palette.color(QPalette.ColorGroup.Disabled, foreground_role)
            disabled_background = palette.color(QPalette.ColorGroup.Disabled, background_role)
            active_background = _composite_color(active_background, root_active_window)
            disabled_background = _composite_color(disabled_background, root_disabled_window)
            active_text = _composite_color(active_text, active_background)
            disabled_text = _composite_color(disabled_text, disabled_background)
            object_path = f"{root.objectName() or type(root).__name__}/{widget.objectName() or type(widget).__name__}"

            if _contrast_ratio(active_text, active_background) < 3.0:
                warnings.append(f"[ui-audit] low contrast {object_path} active")

            if _contrast_ratio(disabled_text, disabled_background) < 2.0:
                warnings.append(f"[ui-audit] low contrast {object_path} disabled")

            if isinstance(widget, QAbstractItemView):
                highlight = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
                highlighted_text = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText)
                highlight = _composite_color(highlight, active_background)
                highlighted_text = _composite_color(highlighted_text, highlight)

                if _contrast_ratio(highlighted_text, highlight) < 3.0:
                    warnings.append(f"[ui-audit] low contrast {object_path} selected")

            if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
                placeholder = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText)
                placeholder = _composite_color(placeholder, active_background)

                if _contrast_ratio(placeholder, active_background) < 2.5:
                    warnings.append(f"[ui-audit] low contrast {object_path} placeholder")

    return warnings


class NavButton(QPushButton):
    def __init__(self, text: str, active: bool = False) -> None:
        super().__init__(text)
        self.setObjectName("sidebarButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("active", active)
        self.setMinimumHeight(self.fontMetrics().height() + 18)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )


class PlayerIconButton(QPushButton):
    """Icon-only transport button that keeps the existing text-based state API."""

    def __init__(self, role: str) -> None:
        super().__init__("")
        self.role = role
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(22, 22))

        labels = {
            "previous": "上一首",
            "play": "播放",
            "next": "下一首",
        }
        self._apply_visual(labels.get(role, "播放"))

    def setText(self, text: str) -> None:
        if getattr(self, "role", "") == "play" and text in {"播放", "暂停"}:
            self._apply_visual(text)
            return

        super().setText(text)

    def _apply_visual(self, state_text: str) -> None:
        icon_role = self.role

        if self.role == "play":
            icon_role = "pause" if state_text == "暂停" else "play"

        self.setIcon(self._create_transport_icon(icon_role))
        self.setToolTip(state_text)
        self.setAccessibleName(state_text)
        super().setText("")

    @staticmethod
    def _create_transport_icon(role: str) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#ffffff" if role in {"play", "pause"} else "#dfe6f2")

        if role == "play":
            path = QPainterPath()
            path.moveTo(11, 7)
            path.lineTo(25, 16)
            path.lineTo(11, 25)
            path.closeSubpath()
            painter.fillPath(path, color)
        elif role == "pause":
            painter.fillRect(10, 8, 5, 16, color)
            painter.fillRect(18, 8, 5, 16, color)
        elif role == "previous":
            painter.fillRect(8, 9, 3, 14, color)
            path = QPainterPath()
            path.moveTo(23, 8)
            path.lineTo(12, 16)
            path.lineTo(23, 24)
            path.closeSubpath()
            painter.fillPath(path, color)
        else:
            painter.fillRect(21, 9, 3, 14, color)
            path = QPainterPath()
            path.moveTo(9, 8)
            path.lineTo(20, 16)
            path.lineTo(9, 24)
            path.closeSubpath()
            painter.fillPath(path, color)

        painter.end()
        return QIcon(pixmap)


class VolumeStatusIcon(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self._muted = False
        self._hovered = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(22, 22)
        self.setMouseTracking(True)
        self._refresh_icon()

    def set_muted(self, muted: bool) -> None:
        muted = bool(muted)

        if muted == self._muted:
            return

        self._muted = muted
        self._refresh_icon()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._refresh_icon()
        super().leaveEvent(event)

    def _refresh_icon(self) -> None:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#ffffff" if self._hovered else "#dfe6f2")

        speaker = QPainterPath()
        speaker.moveTo(4, 10)
        speaker.lineTo(8, 10)
        speaker.lineTo(13, 6)
        speaker.lineTo(13, 18)
        speaker.lineTo(8, 14)
        speaker.lineTo(4, 14)
        speaker.closeSubpath()
        painter.fillPath(speaker, color)

        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self._muted:
            painter.drawLine(16, 9, 21, 15)
            painter.drawLine(21, 9, 16, 15)
        else:
            wave = QPainterPath()
            wave.moveTo(16, 9)
            wave.cubicTo(19, 10, 19, 14, 16, 15)
            painter.drawPath(wave)

            outer_wave = QPainterPath()
            outer_wave.moveTo(18, 6)
            outer_wave.cubicTo(23, 9, 23, 15, 18, 18)
            painter.drawPath(outer_wave)

        painter.end()
        self.setPixmap(pixmap)
        state_text = "静音" if self._muted else "音量"
        self.setToolTip(state_text)
        self.setAccessibleName(state_text)


class ElidedLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.full_text = ""
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:
        self.full_text = text or ""
        self.setToolTip(self.full_text)
        self.update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_elided_text()

    def update_elided_text(self) -> None:
        if not self.full_text:
            QLabel.setText(self, "")
            return

        available_width = max(20, self.width() - 4)
        metrics = QFontMetrics(self.font())
        elided_text = metrics.elidedText(
            self.full_text,
            Qt.TextElideMode.ElideRight,
            available_width,
        )
        QLabel.setText(self, elided_text)


class MultiLineElidedLabel(QLabel):
    def __init__(self, text: str = "", max_lines: int = 2) -> None:
        super().__init__()
        self.full_text = ""
        self.max_lines = max(1, int(max_lines))
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setText(text)

    def setText(self, text: str) -> None:
        self.full_text = text or ""
        self.setToolTip(self.full_text)
        self.update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_elided_text()

    def update_elided_text(self) -> None:
        if not self.full_text:
            QLabel.setText(self, "")
            return

        available_width = max(40, self.width() - 4)
        metrics = QFontMetrics(self.font())
        remaining = self.full_text.strip()
        lines = []

        for line_index in range(self.max_lines):
            if not remaining:
                break

            if line_index == self.max_lines - 1:
                lines.append(metrics.elidedText(remaining, Qt.TextElideMode.ElideRight, available_width))
                break

            low = 1
            high = len(remaining)
            best = 1

            while low <= high:
                mid = (low + high) // 2
                candidate = remaining[:mid]

                if metrics.horizontalAdvance(candidate) <= available_width:
                    best = mid
                    low = mid + 1
                else:
                    high = mid - 1

            line = remaining[:best].rstrip()
            lines.append(line)
            remaining = remaining[best:].lstrip()

        QLabel.setText(self, "\n".join(lines))

        line_height = metrics.lineSpacing()
        self.setMinimumHeight(line_height * min(self.max_lines, max(1, len(lines))) + 4)
        self.setMaximumHeight(line_height * self.max_lines + 6)


SONG_TABLE_MARKER_WIDTH = 18
SONG_TABLE_DURATION_WIDTH = 58
SONG_TABLE_COLUMN_GAP = 14


def configure_song_table_columns(layout: QGridLayout) -> None:
    layout.setColumnMinimumWidth(0, SONG_TABLE_MARKER_WIDTH)
    layout.setColumnStretch(1, 4)
    layout.setColumnStretch(2, 2)
    layout.setColumnStretch(3, 2)
    layout.setColumnMinimumWidth(4, SONG_TABLE_DURATION_WIDTH)


class SongLibraryDelegate(QStyledItemDelegate):
    def __init__(self, main_window, parent=None) -> None:
        super().__init__(parent)
        self.main_window = main_window

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, 58)

    @staticmethod
    def column_rects(rect) -> dict[str, QRectF]:
        row_rect = QRectF(rect.adjusted(2, 2, -2, -2))
        content = row_rect.adjusted(12, 0, -12, 0)
        available_width = max(0, int(content.width()))
        fixed_width = SONG_TABLE_MARKER_WIDTH + SONG_TABLE_DURATION_WIDTH
        gap = min(
            SONG_TABLE_COLUMN_GAP,
            max(0, (available_width - fixed_width) // 4),
        )
        flexible_width = max(0, available_width - fixed_width - gap * 4)
        title_width = int(flexible_width * 0.5)
        artist_width = int(flexible_width * 0.25)
        album_width = max(0, flexible_width - title_width - artist_width)
        x = content.left()

        result: dict[str, QRectF] = {}
        result["marker"] = QRectF(x, content.top(), SONG_TABLE_MARKER_WIDTH, content.height())
        x += SONG_TABLE_MARKER_WIDTH + gap
        result["title"] = QRectF(x, content.top(), title_width, content.height())
        x += title_width + gap
        result["artist"] = QRectF(x, content.top(), artist_width, content.height())
        x += artist_width + gap
        result["album"] = QRectF(x, content.top(), album_width, content.height())
        x += album_width + gap
        result["duration"] = QRectF(x, content.top(), SONG_TABLE_DURATION_WIDTH, content.height())
        return result

    def paint(self, painter: QPainter, option, index) -> None:
        song_data = index.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        row_rect = QRectF(option.rect.adjusted(2, 2, -2, -2))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        track_identity = self.main_window.track_identity_for_song_data(song_data)
        is_playing = bool(
            track_identity
            and track_identity == self.main_window.current_track_identity()
        )

        if selected:
            background = QColor(76, 141, 255, 48)
            border = QColor(76, 141, 255, 118)
        elif is_playing:
            background = QColor(76, 141, 255, 27)
            border = QColor(76, 141, 255, 70)
        elif hovered:
            background = QColor(255, 255, 255, 14)
            border = QColor(255, 255, 255, 10)
        else:
            background = QColor(0, 0, 0, 0)
            border = QColor(0, 0, 0, 0)

        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(row_rect, 10, 10)

        if is_playing:
            accent_rect = QRectF(row_rect.left(), row_rect.top() + 8, 3, row_rect.height() - 16)
            painter.fillRect(accent_rect, QColor("#4c8dff"))

        rects = self.column_rects(option.rect)

        duration_seconds = self.main_window.get_library_duration_seconds(song_data)
        duration_text = (
            self.main_window.format_duration_text(duration_seconds)
            if duration_seconds > 0
            else "—"
        )
        self._draw_text(painter, option, rects["marker"], "▶" if is_playing else "", "#4c8dff", True)
        self._draw_text(
            painter,
            option,
            rects["title"],
            str(song_data.get("title") or "未知歌曲"),
            "#ffffff" if is_playing else "#f3f4f6",
            is_playing,
        )
        self._draw_text(painter, option, rects["artist"], str(song_data.get("artist") or "未知艺术家"), "#b5bbc7")
        self._draw_text(painter, option, rects["album"], str(song_data.get("album") or "未知专辑"), "#b5bbc7")
        self._draw_text(painter, option, rects["duration"], duration_text, "#8a92a3", align_right=True)
        painter.restore()

    def helpEvent(self, event, view, option, index) -> bool:
        if event.type() != QEvent.Type.ToolTip:
            return super().helpEvent(event, view, option, index)

        song_data = index.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return False

        rects = self.column_rects(option.rect)
        field_values = {
            "title": str(song_data.get("title") or "未知歌曲"),
            "artist": str(song_data.get("artist") or "未知艺术家"),
            "album": str(song_data.get("album") or "未知专辑"),
        }

        for field, text in field_values.items():
            field_rect = rects[field]

            if not field_rect.contains(event.pos()):
                continue

            font = QFont(option.font)
            metrics = QFontMetrics(font)

            if metrics.horizontalAdvance(text) > max(0, int(field_rect.width())):
                QToolTip.showText(event.globalPos(), text, view, field_rect.toRect())
                return True

            break

        QToolTip.hideText()
        return False

    @staticmethod
    def _draw_text(
        painter: QPainter,
        option,
        rect: QRectF,
        text: str,
        color: str,
        bold: bool = False,
        align_right: bool = False,
    ) -> None:
        font = QFont(option.font)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        metrics = QFontMetrics(font)
        elided_text = metrics.elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            max(1, int(rect.width())),
        )
        alignment = Qt.AlignmentFlag.AlignVCenter
        alignment |= Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        painter.drawText(rect, alignment, elided_text)


class RoundedCoverLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.cover_pixmap = QPixmap()
        self.cached_source_key = None
        self.cached_size = None
        self.cached_scaled_pixmap = QPixmap()
        self.radius = 22
        self.padding = 10
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(248, 248)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def invalidate_pixmap_cache(self) -> None:
        self.cached_source_key = None
        self.cached_size = None
        self.cached_scaled_pixmap = QPixmap()

    def setPixmap(self, pixmap: QPixmap) -> None:
        self.cover_pixmap = QPixmap(pixmap) if pixmap is not None and not pixmap.isNull() else QPixmap()
        self.invalidate_pixmap_cache()
        self.update()

    def pixmap(self) -> QPixmap:
        return QPixmap(self.cover_pixmap)

    def clear(self) -> None:
        self.cover_pixmap = QPixmap()
        self.invalidate_pixmap_cache()
        super().clear()
        self.update()

    def resizeEvent(self, event) -> None:
        self.invalidate_pixmap_cache()
        super().resizeEvent(event)

    def get_scaled_cover_pixmap(self, target_size) -> QPixmap:
        if self.cover_pixmap.isNull():
            return QPixmap()

        source_key = self.cover_pixmap.cacheKey()

        if (
            self.cached_source_key == source_key
            and self.cached_size == target_size
            and not self.cached_scaled_pixmap.isNull()
        ):
            return self.cached_scaled_pixmap

        self.cached_source_key = source_key
        self.cached_size = target_size
        self.cached_scaled_pixmap = self.cover_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return self.cached_scaled_pixmap

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        painter.fillPath(path, QColor("#151821"))

        inner_rect = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner_rect, max(10, self.radius - 8), max(10, self.radius - 8))

        if not self.cover_pixmap.isNull():
            scaled = self.get_scaled_cover_pixmap(inner_rect.size().toSize())
            x = inner_rect.x() + (inner_rect.width() - scaled.width()) / 2
            y = inner_rect.y() + (inner_rect.height() - scaled.height()) / 2

            painter.save()
            painter.setClipPath(inner_path)
            painter.fillPath(inner_path, QColor("#0f1117"))
            painter.drawPixmap(int(x), int(y), scaled)
            painter.restore()
        else:
            painter.save()
            painter.setClipPath(inner_path)
            painter.fillPath(inner_path, QColor("#11131a"))
            painter.setPen(QColor("#f5f7fb"))
            painter.drawText(inner_rect, Qt.AlignmentFlag.AlignCenter, self.text())
            painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
        painter.drawPath(path)


class LyricsView(QScrollArea):
    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("lyricsView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setObjectName("lyricsContent")

        self.lyrics_layout = QVBoxLayout(self.content)
        self.lyrics_layout.setContentsMargins(0, 120, 0, 120)
        self.lyrics_layout.setSpacing(14)

        self.setWidget(self.content)

        self.labels: list[QLabel] = []
        self.current_index = -1
        self.plain_text_mode = False

        self.scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.scroll_animation.setDuration(520)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.set_placeholder("这里会显示歌词", "支持本地 .lrc 歌词滚动")

    def clear_content(self) -> None:
        while self.lyrics_layout.count():
            item = self.lyrics_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        self.labels = []
        self.current_index = -1
        self.plain_text_mode = False

    def set_placeholder(self, title: str, subtitle: str = "") -> None:
        self.clear_content()

        self.lyrics_layout.setContentsMargins(0, 80, 0, 80)
        self.lyrics_layout.addStretch()

        title_label = QLabel(title)
        title_label.setObjectName("lyricPlaceholderTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)

        self.lyrics_layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("lyricPlaceholderSubtitle")
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setWordWrap(True)

            self.lyrics_layout.addWidget(subtitle_label)

        self.lyrics_layout.addStretch()
        self.verticalScrollBar().setValue(0)

    def set_lyrics(self, lyrics: list[tuple[int, str]]) -> None:
        self.clear_content()

        if not lyrics:
            self.set_placeholder("未找到歌词", "把同名 .lrc 文件放在歌曲旁边即可显示")
            return

        self.lyrics_layout.setContentsMargins(0, 135, 0, 135)
        self.lyrics_layout.setSpacing(12)

        for _, text in lyrics:
            label = QLabel(text)
            label.setObjectName("lyricLine")
            label.setProperty("lyricState", "normal")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )

            self.lyrics_layout.addWidget(label)
            self.labels.append(label)

        self.current_index = -1
        self.verticalScrollBar().setValue(0)

    def set_plain_text(self, text: str) -> None:
        self.clear_content()
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            self.set_placeholder("暂无歌词", "歌曲来源没有提供可显示的歌词")
            return
        self.plain_text_mode = True
        self.lyrics_layout.setContentsMargins(18, 60, 18, 80)
        self.lyrics_layout.setSpacing(16)
        for line in lines:
            label = QLabel(line)
            label.setObjectName("lyricLine")
            label.setProperty("lyricState", "normal")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            self.lyrics_layout.addWidget(label)
            self.labels.append(label)
        self.verticalScrollBar().setValue(0)

    def update_by_position(self, position: int, lyrics: list[tuple[int, str]]) -> None:
        if self.plain_text_mode or not lyrics or not self.labels:
            return

        new_index = -1

        for index, (timestamp, _) in enumerate(lyrics):
            if position >= timestamp:
                new_index = index
            else:
                break

        if new_index == self.current_index:
            return

        self.set_current_index(new_index)

    def set_current_index(self, index: int) -> None:
        if index == self.current_index:
            return

        previous_index = self.current_index
        self.current_index = index
        affected_indexes = set()

        for center_index in (previous_index, index):
            for offset in (-1, 0, 1):
                label_index = center_index + offset

                if 0 <= label_index < len(self.labels):
                    affected_indexes.add(label_index)

        for label_index in affected_indexes:
            label = self.labels[label_index]

            if label_index == index:
                state = "current"
            elif abs(label_index - index) == 1:
                state = "near"
            else:
                state = "normal"

            if label.property("lyricState") == state:
                continue

            label.setProperty("lyricState", state)
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()

        if index < 0 or index >= len(self.labels):
            return
        self.content.layout().activate()

        current_label = self.labels[index]
        label_center_y = current_label.y() + current_label.height() // 2
        target_value = label_center_y - self.viewport().height() // 2

        target_value = max(0, min(target_value, self.verticalScrollBar().maximum()))

        self.scroll_animation.stop()
        self.scroll_animation.setStartValue(self.verticalScrollBar().value())
        self.scroll_animation.setEndValue(target_value)
        self.scroll_animation.start()


class CoverSearchWorker(QObject):
    status_changed = Signal(str, str)
    finished = Signal(str, object)

    MISSING_CACHE_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        request_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: str,
        cover_cache_dir: str,
        http_headers: dict,
    ) -> None:
        super().__init__()

        self.request_id = request_id
        self.file_path = file_path
        self.title = title
        self.artist = artist
        self.album = album
        self.cover_cache_dir = Path(cover_cache_dir)
        self.http_headers = dict(http_headers)
        self.last_musicbrainz_request_time = 0.0
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def is_cancelled(self) -> bool:
        return self._cancel_requested or QThread.currentThread().isInterruptionRequested()

    def cancelled_result(self) -> dict:
        return {
            "ok": False,
            "source": "cancelled",
            "message": "封面请求已取消",
            "song_path": self.file_path,
        }

    def emit_status(self, message: str) -> None:
        if self.is_cancelled():
            return
        self.status_changed.emit(self.request_id, message)

    def run(self) -> None:
        try:
            result = self.cancelled_result() if self.is_cancelled() else self.search_cover()
            if self.is_cancelled() and result.get("source") != "cancelled":
                result = self.cancelled_result()
            self.finished.emit(self.request_id, result)
        except Exception as error:
            if self.is_cancelled():
                self.finished.emit(self.request_id, self.cancelled_result())
                return
            self.finished.emit(
                self.request_id,
                {
                    "ok": False,
                    "source": "error",
                    "message": str(error),
                    "song_path": self.file_path,
                },
            )

    def search_cover(self) -> dict:
        if self.is_cancelled():
            return self.cancelled_result()

        if not self.file_path:
            return {
                "ok": False,
                "source": "empty",
                "message": "没有歌曲路径",
                "song_path": self.file_path,
            }

        music_path = Path(self.file_path)
        cache_path = self.get_cover_cache_path(music_path)
        missing_path = cache_path.with_suffix(".missing")

        if cache_path.exists():
            self.emit_status("已加载缓存封面")
            return {
                "ok": True,
                "source": "cache",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        if self.is_missing_cache_valid(missing_path):
            self.emit_status("封面缓存记录：上次未找到")
            return {
                "ok": False,
                "source": "missing_cache",
                "message": "近期已经搜索过，未找到封面",
                "song_path": self.file_path,
            }

        self.emit_status("正在读取内嵌封面")
        cover_data = self.extract_album_cover(music_path)

        if self.is_cancelled():
            return self.cancelled_result()

        if cover_data:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(cover_data)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "embedded",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.emit_status("正在查找文件夹封面")
        folder_cover = self.find_folder_cover(music_path)

        if self.is_cancelled():
            return self.cancelled_result()

        if folder_cover:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder_cover, cache_path)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "folder",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.emit_status("正在联网搜索封面")
        online_cover = self.fetch_online_cover(self.title, self.artist, self.album)

        if self.is_cancelled():
            return self.cancelled_result()

        if online_cover:
            self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(online_cover)
            self.remove_missing_cache(missing_path)

            return {
                "ok": True,
                "source": "online",
                "cover_path": str(cache_path),
                "song_path": self.file_path,
            }

        self.write_missing_cache(missing_path, "cover not found")
        self.emit_status("未找到封面，已记录缓存")
        return {
            "ok": False,
            "source": "not_found",
            "message": "未找到封面",
            "song_path": self.file_path,
        }

    def get_cover_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.cover_cache_dir / f"{digest}.jpg"

    def is_missing_cache_valid(self, missing_path: Path) -> bool:
        if not missing_path.exists():
            return False

        try:
            age = time.time() - missing_path.stat().st_mtime
            return age < self.MISSING_CACHE_SECONDS
        except Exception:
            return False

    def write_missing_cache(self, missing_path: Path, message: str) -> None:
        try:
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.write_text(message, encoding="utf-8")
        except Exception:
            pass

    def remove_missing_cache(self, missing_path: Path) -> None:
        try:
            if missing_path.exists():
                missing_path.unlink()
        except Exception:
            pass

    def extract_album_cover(self, path: Path) -> bytes | None:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return None

            if hasattr(audio, "pictures") and audio.pictures:
                return audio.pictures[0].data

            if audio.tags is None:
                return None

            for key in audio.tags.keys():
                if str(key).startswith("APIC"):
                    tag = audio.tags[key]

                    if hasattr(tag, "data"):
                        return tag.data

            mp4_cover = audio.tags.get("covr")

            if mp4_cover:
                return bytes(mp4_cover[0])

        except Exception as error:
            print("后台读取内嵌封面失败：", path)
            print(error)

        return None

    def find_folder_cover(self, music_path: Path) -> Path | None:
        folder = music_path.parent

        possible_names = [
            "cover.jpg",
            "cover.jpeg",
            "cover.png",
            "folder.jpg",
            "folder.jpeg",
            "folder.png",
            "front.jpg",
            "front.jpeg",
            "front.png",
            "album.jpg",
            "album.jpeg",
            "album.png",
        ]

        for name in possible_names:
            candidate = folder / name

            if candidate.exists():
                return candidate

        return None

    def clean_search_text(self, text: str) -> str:
        text = str(text).strip()

        if text in {"未知歌曲", "未知艺术家", "未知专辑"}:
            return ""

        return text

    def wait_for_musicbrainz_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self.last_musicbrainz_request_time

        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        self.last_musicbrainz_request_time = time.time()

    def fetch_online_cover(self, title: str, artist: str, album: str) -> bytes | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_artist:
            return None

        if cleaned_album and cleaned_album not in {"未知专辑", "unknown album"}:
            queries = [
                f'release:"{cleaned_album}" AND artist:"{cleaned_artist}"',
                f'{cleaned_album} {cleaned_artist}',
            ]
        else:
            queries = [
                f'recording:"{cleaned_title}" AND artist:"{cleaned_artist}"',
                f'{cleaned_title} {cleaned_artist}',
            ]

        for query in queries:
            if self.is_cancelled():
                return None

            release_ids = self.search_musicbrainz_release_ids(query)

            for release_id in release_ids:
                if self.is_cancelled():
                    return None

                cover_data = self.fetch_cover_art_archive(release_id)

                if cover_data:
                    return cover_data

        return None

    def search_musicbrainz_release_ids(self, query: str) -> list[str]:
        try:
            self.wait_for_musicbrainz_rate_limit()

            if self.is_cancelled():
                return []

            response = requests.get(
                "https://musicbrainz.org/ws/2/release/",
                params={
                    "query": query,
                    "fmt": "json",
                    "limit": 5,
                },
                headers=self.http_headers,
                timeout=10,
            )

            response.raise_for_status()

            if self.is_cancelled():
                return []

            data = response.json()

        except Exception as error:
            print("后台 MusicBrainz 搜索失败：", error)
            return []

        releases = data.get("releases", [])
        release_ids = []

        for release in releases:
            release_id = release.get("id")

            if release_id:
                release_ids.append(release_id)

        return release_ids

    def fetch_cover_art_archive(self, release_id: str) -> bytes | None:
        url = f"https://coverartarchive.org/release/{release_id}/front-500"

        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": self.http_headers.get("User-Agent", "HushPlayer"),
                    "Accept": "image/*",
                },
                timeout=15,
                allow_redirects=True,
            )

            if self.is_cancelled():
                return None

            if response.status_code != 200:
                return None

            content_type = response.headers.get("Content-Type", "")

            if "image" not in content_type.lower():
                return None

            return response.content

        except Exception as error:
            print("后台 Cover Art Archive 获取失败：", error)
            return None


class LyricsSearchWorker(QObject):
    status_changed = Signal(str, str)
    finished = Signal(str, object)

    MISSING_CACHE_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        request_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: str,
        lyrics_cache_dir: str,
        http_headers: dict,
    ) -> None:
        super().__init__()

        self.request_id = request_id
        self.file_path = file_path
        self.title = title
        self.artist = artist
        self.album = album
        self.lyrics_cache_dir = Path(lyrics_cache_dir)
        self.http_headers = dict(http_headers)
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def is_cancelled(self) -> bool:
        return self._cancel_requested or QThread.currentThread().isInterruptionRequested()

    def cancelled_result(self) -> dict:
        return {
            "ok": False,
            "source": "cancelled",
            "message": "歌词请求已取消",
            "song_path": self.file_path,
        }

    def emit_status(self, message: str) -> None:
        if self.is_cancelled():
            return
        self.status_changed.emit(self.request_id, message)

    def run(self) -> None:
        try:
            result = self.cancelled_result() if self.is_cancelled() else self.search_lyrics()
            if self.is_cancelled() and result.get("source") != "cancelled":
                result = self.cancelled_result()
            self.finished.emit(self.request_id, result)
        except Exception as error:
            if self.is_cancelled():
                self.finished.emit(self.request_id, self.cancelled_result())
                return
            self.finished.emit(
                self.request_id,
                {
                    "ok": False,
                    "source": "error",
                    "message": str(error),
                    "song_path": self.file_path,
                },
            )

    def search_lyrics(self) -> dict:
        if self.is_cancelled():
            return self.cancelled_result()

        if not self.file_path:
            return {
                "ok": False,
                "source": "empty",
                "message": "没有歌曲路径",
                "song_path": self.file_path,
            }

        music_path = Path(self.file_path)
        cache_path = self.get_lyrics_cache_path(music_path)
        missing_path = cache_path.with_suffix(".missing")

        self.emit_status("正在查找本地歌词")
        local_lrc = self.find_lrc_file(music_path, self.title, self.artist)

        if self.is_cancelled():
            return self.cancelled_result()

        if local_lrc:
            self.remove_missing_cache(missing_path)
            return {
                "ok": True,
                "source": "local",
                "lyrics_path": str(local_lrc),
                "song_path": self.file_path,
            }

        self.emit_status("正在读取歌词缓存")

        if cache_path.exists():
            return {
                "ok": True,
                "source": "cache",
                "lyrics_path": str(cache_path),
                "song_path": self.file_path,
            }

        if self.is_missing_cache_valid(missing_path):
            self.emit_status("歌词缓存记录：上次未找到")
            return {
                "ok": False,
                "source": "missing_cache",
                "message": "近期已经搜索过，未找到同步歌词",
                "song_path": self.file_path,
            }

        self.emit_status("正在联网搜索歌词")
        duration_seconds = self.get_audio_duration_seconds(music_path)
        search_title = self.title

        if not self.clean_search_text(search_title):
            search_title = music_path.stem

        synced_lyrics = self.search_lrclib_synced_lyrics(
            title=search_title,
            artist=self.artist,
            album=self.album,
            duration_seconds=duration_seconds,
        )

        if self.is_cancelled():
            return self.cancelled_result()

        if not synced_lyrics:
            self.write_missing_cache(missing_path, "lyrics not found")
            self.emit_status("未找到歌词，已记录缓存")
            return {
                "ok": False,
                "source": "not_found",
                "message": "未找到同步歌词",
                "song_path": self.file_path,
            }

        self.lyrics_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(synced_lyrics, encoding="utf-8")
        self.remove_missing_cache(missing_path)

        return {
            "ok": True,
            "source": "online",
            "lyrics_path": str(cache_path),
            "song_path": self.file_path,
        }

    def get_lyrics_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.lyrics_cache_dir / f"{digest}.lrc"

    def is_missing_cache_valid(self, missing_path: Path) -> bool:
        if not missing_path.exists():
            return False

        try:
            age = time.time() - missing_path.stat().st_mtime
            return age < self.MISSING_CACHE_SECONDS
        except Exception:
            return False

    def write_missing_cache(self, missing_path: Path, message: str) -> None:
        try:
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            missing_path.write_text(message, encoding="utf-8")
        except Exception:
            pass

    def remove_missing_cache(self, missing_path: Path) -> None:
        try:
            if missing_path.exists():
                missing_path.unlink()
        except Exception:
            pass

    def find_lrc_file(self, music_path: Path, title: str, artist: str) -> Path | None:
        folder = music_path.parent

        candidates = [
            music_path.with_suffix(".lrc"),
            folder / f"{music_path.stem}.lrc",
            folder / f"{title}.lrc",
            folder / f"{artist} - {title}.lrc",
            folder / f"{title} - {artist}.lrc",
        ]

        seen = set()

        for candidate in candidates:
            normalized = str(candidate).lower()

            if normalized in seen:
                continue

            seen.add(normalized)

            if candidate.exists():
                return candidate

        for candidate in folder.glob("*.lrc"):
            if candidate.stem.lower() == music_path.stem.lower():
                return candidate

        return None

    def get_audio_duration_seconds(self, path: Path) -> int:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return 0

            info = getattr(audio, "info", None)

            if info is None:
                return 0

            length = getattr(info, "length", 0)

            if not length:
                return 0

            return int(round(float(length)))

        except Exception as error:
            print("后台读取歌曲时长失败：", path)
            print(error)
            return 0

    def clean_search_text(self, text: str) -> str:
        text = str(text).strip()

        if text in {"未知歌曲", "未知艺术家", "未知专辑"}:
            return ""

        return text

    def normalize_match_text(self, text: str) -> str:
        text = self.clean_search_text(text).lower()
        text = re.sub(r"[\s\-_.,，。:：;；!！?？'\"“”‘’()\[\]{}【】<>《》/\\\\]+", "", text)
        return text

    def calculate_lyrics_result_score(
        self,
        result: dict,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> int:
        score = 0

        synced_lyrics = result.get("syncedLyrics")

        if not synced_lyrics:
            return -9999

        result_title = str(result.get("trackName", ""))
        result_artist = str(result.get("artistName", ""))
        result_album = str(result.get("albumName", ""))

        target_title = self.normalize_match_text(title)
        target_artist = self.normalize_match_text(artist)
        target_album = self.normalize_match_text(album)

        matched_title = self.normalize_match_text(result_title)
        matched_artist = self.normalize_match_text(result_artist)
        matched_album = self.normalize_match_text(result_album)

        if target_title and matched_title:
            if target_title == matched_title:
                score += 80
            elif target_title in matched_title or matched_title in target_title:
                score += 45

        if target_artist and matched_artist:
            if target_artist == matched_artist:
                score += 60
            elif target_artist in matched_artist or matched_artist in target_artist:
                score += 30

        if target_album and matched_album:
            if target_album == matched_album:
                score += 20
            elif target_album in matched_album or matched_album in target_album:
                score += 8

        result_duration = int(result.get("duration", 0) or 0)

        if duration_seconds > 0 and result_duration > 0:
            diff = abs(duration_seconds - result_duration)

            if diff <= 2:
                score += 30
            elif diff <= 5:
                score += 18
            elif diff <= 10:
                score += 8

        score += 40
        return score

    def search_lrclib_synced_lyrics(
        self,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> str | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_title:
            return None

        search_requests = []

        first_params = {
            "track_name": cleaned_title,
        }

        if cleaned_artist:
            first_params["artist_name"] = cleaned_artist

        if cleaned_album:
            first_params["album_name"] = cleaned_album

        search_requests.append(first_params)

        if cleaned_artist:
            search_requests.append(
                {
                    "q": f"{cleaned_title} {cleaned_artist}",
                }
            )

        search_requests.append(
            {
                "q": cleaned_title,
            }
        )

        best_result = None
        best_score = -9999

        for params in search_requests:
            if self.is_cancelled():
                return None

            try:
                response = requests.get(
                    "https://lrclib.net/api/search",
                    params=params,
                    headers=self.http_headers,
                    timeout=12,
                )

                response.raise_for_status()

                if self.is_cancelled():
                    return None

                results = response.json()

                if not isinstance(results, list):
                    continue

            except Exception as error:
                print("后台 LRCLIB 搜索失败：", error)
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue

                score = self.calculate_lyrics_result_score(
                    result=result,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_seconds=duration_seconds,
                )

                if score > best_score:
                    best_score = score
                    best_result = result

            if best_result and best_score >= 110:
                break

        if not best_result:
            return None

        synced_lyrics = best_result.get("syncedLyrics")

        if not synced_lyrics:
            return None

        if best_score < 80:
            return None

        return str(synced_lyrics).strip()


class LibraryDurationSignals(QObject):
    finished = Signal(str, int, float)


class LibraryDurationTask(QRunnable):
    def __init__(self, song_path: str) -> None:
        super().__init__()
        self.song_path = str(song_path)
        self.signals = LibraryDurationSignals()

    def run(self) -> None:
        started_at = time.perf_counter()
        duration_seconds = 0

        try:
            audio = MutagenFile(Path(self.song_path))
            info = getattr(audio, "info", None) if audio is not None else None
            length = getattr(info, "length", 0) if info is not None else 0
            duration_seconds = max(0, int(round(float(length or 0))))
        except Exception:
            duration_seconds = 0

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        self.signals.finished.emit(self.song_path, duration_seconds, elapsed_ms)


class MusicFolderScanWorker(QObject):
    finished = Signal(object)

    def __init__(
        self,
        folders: list[str],
        existing_paths: list[str],
        pending_paths: list[str] | None = None,
        ignored_paths: list[str] | None = None,
    ) -> None:
        super().__init__()

        self.folders = list(folders)
        self.existing_paths = set(existing_paths)
        self.pending_paths = set(pending_paths or [])
        self.ignored_paths = set(ignored_paths or [])

    def run(self) -> None:
        result = {
            "ok": True,
            "scanned": 0,
            "new_songs": [],
            "duplicates": 0,
            "failed": 0,
            "errors": [],
        }

        try:
            self.scan_folders(result)
        except Exception as error:
            result["ok"] = False
            result["errors"].append(str(error))

        self.finished.emit(result)

    def scan_folders(self, result: dict) -> None:
        seen_paths = set(self.existing_paths) | set(self.pending_paths) | set(self.ignored_paths)

        for folder_text in self.folders:
            folder_text = str(folder_text).strip()

            if not folder_text:
                continue

            folder = Path(folder_text).expanduser()

            try:
                folder = folder.resolve()
            except Exception:
                pass

            source_folder = str(folder)

            if not folder.exists() or not folder.is_dir():
                result["failed"] += 1
                result["errors"].append(f"文件夹不可用：{folder_text}")
                continue

            def on_walk_error(error) -> None:
                result["failed"] += 1
                result["errors"].append(str(error))

            for root, _, file_names in os.walk(folder, onerror=on_walk_error):
                for file_name in file_names:
                    path = Path(root) / file_name

                    if path.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue

                    result["scanned"] += 1

                    try:
                        normalized_path = str(path.resolve())
                    except Exception as error:
                        result["failed"] += 1
                        result["errors"].append(f"{path}: {error}")
                        continue

                    normalized_key = normalized_path.lower()

                    if normalized_key in seen_paths:
                        result["duplicates"] += 1
                        continue

                    if not path.exists() or not path.is_file():
                        result["failed"] += 1
                        continue

                    title, artist, album = self.read_audio_metadata(path)
                    result["new_songs"].append(
                        {
                            "title": title,
                            "artist": artist,
                            "album": album,
                            "duration": self.read_audio_duration(path),
                            "format": path.suffix.lower().lstrip("."),
                            "path": normalized_path,
                            "source_folder": source_folder,
                            "found_at": int(time.time()),
                            "added_at": int(time.time()) + len(result["new_songs"]),
                            "demo": False,
                        }
                    )
                    seen_paths.add(normalized_key)

    def read_audio_metadata(self, path: Path) -> tuple[str, str, str]:
        title = path.stem
        artist = "未知艺术家"
        album = "未知专辑"

        try:
            audio = MutagenFile(path, easy=True)

            if audio is None or audio.tags is None:
                return title, artist, album

            title = audio.tags.get("title", [title])[0]
            artist = audio.tags.get("artist", [artist])[0]
            album = audio.tags.get("album", [album])[0]

        except Exception as error:
            print(f"后台读取歌曲信息失败：{path}")
            print(error)

        return str(title or path.stem), str(artist or "未知艺术家"), str(album or "未知专辑")

    def read_audio_duration(self, path: Path) -> int:
        try:
            audio = MutagenFile(path)
            info = getattr(audio, "info", None)
            length = getattr(info, "length", 0) if info is not None else 0
            return int(round(float(length or 0)))
        except Exception:
            return 0
class FloatingLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.locked = False
        self.drag_offset = None

        self.font_size = int(main_window.get_user_setting("floating_lyrics_font_size", 42))
        self.text_alpha = int(main_window.get_user_setting("floating_lyrics_opacity", 100))
        self.text_color_name = str(main_window.get_user_setting("floating_lyrics_color", "white"))
        self.window_width = int(main_window.get_user_setting("floating_lyrics_width", 980))
        self.window_height = int(main_window.get_user_setting("floating_lyrics_height", 135))

        self.color_map = {
            "white": ("白色", 255, 255, 255),
            "black": ("黑色", 0, 0, 0),
            "yellow": ("黄色", 255, 226, 96),
            "blue": ("蓝色", 105, 173, 255),
            "green": ("绿色", 120, 235, 166),
            "pink": ("粉色", 255, 130, 190),
            "purple": ("紫色", 190, 145, 255),
        }

        self.setWindowTitle("HushPlayer 桌面歌词")
        self.setObjectName("floatingLyricsWindow")
        self.setMinimumSize(420, 80)
        self.resize(self.window_width, self.window_height)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(0)

        self.current_label = QLabel("桌面歌词已开启")
        self.current_label.setObjectName("floatingLyricCurrent")
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_label.setWordWrap(True)
        self.current_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout.addWidget(self.current_label, 1)

        self.apply_style()

    def get_rgba_color(self) -> str:
        color_key = self.text_color_name

        if color_key not in self.color_map:
            color_key = "white"

        _, red, green, blue = self.color_map[color_key]
        alpha = max(25, min(255, int(self.text_alpha / 100 * 255)))

        return f"rgba({red}, {green}, {blue}, {alpha})"

    def apply_style(self) -> None:
        self.setStyleSheet(
            "QWidget#floatingLyricsWindow { background: transparent; font-family: 'Microsoft YaHei UI'; }"
            f"QLabel#floatingLyricCurrent {{ color: {self.get_rgba_color()}; background: transparent; font-size: {self.font_size}px; font-weight: 950; padding: 0px; }}"
        )

    def save_preferences(self) -> None:
        self.main_window.save_hush_settings(
            {
                "floating_lyrics_font_size": int(self.font_size),
                "floating_lyrics_opacity": int(self.text_alpha),
                "floating_lyrics_color": self.text_color_name,
                "floating_lyrics_width": int(self.width()),
                "floating_lyrics_height": int(self.height()),
                "floating_lyrics_x": int(self.x()),
                "floating_lyrics_y": int(self.y()),
            }
        )

    def set_lines(self, previous_line: str, current_line: str, next_line: str) -> None:
        self.current_label.setText(current_line or "暂无歌词")

    def adjust_font_size(self, step: int) -> None:
        self.font_size = max(22, min(84, self.font_size + step))
        self.apply_style()
        self.save_preferences()

    def adjust_window_width(self, step: int) -> None:
        new_width = max(420, min(1600, self.width() + step))
        self.resize(new_width, self.height())
        self.save_preferences()

    def reset_size(self) -> None:
        self.font_size = 42
        self.resize(980, 135)
        self.apply_style()
        self.save_preferences()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        if self.locked:
            lock_action = menu.addAction("解锁位置")
        else:
            lock_action = menu.addAction("锁定位置")

        bigger_action = menu.addAction("放大歌词")
        smaller_action = menu.addAction("缩小歌词")
        wider_action = menu.addAction("加宽显示区域")
        narrower_action = menu.addAction("缩窄显示区域")
        reset_size_action = menu.addAction("重置大小")

        menu.addSeparator()

        opacity_up_action = menu.addAction("提高不透明度")
        opacity_down_action = menu.addAction("降低不透明度")

        menu.addSeparator()

        color_menu = menu.addMenu("歌词颜色")
        color_actions = {}

        for color_key, (color_label, _, _, _) in self.color_map.items():
            action = color_menu.addAction(color_label)
            action.setCheckable(True)
            action.setChecked(color_key == self.text_color_name)
            color_actions[action] = color_key

        menu.addSeparator()

        close_action = menu.addAction("关闭桌面歌词")

        action = menu.exec(event.globalPos())

        if action == lock_action:
            self.locked = not self.locked
        elif action == bigger_action:
            self.adjust_font_size(3)
        elif action == smaller_action:
            self.adjust_font_size(-3)
        elif action == wider_action:
            self.adjust_window_width(100)
        elif action == narrower_action:
            self.adjust_window_width(-100)
        elif action == reset_size_action:
            self.reset_size()
        elif action == opacity_up_action:
            self.text_alpha = min(100, self.text_alpha + 10)
            self.apply_style()
            self.save_preferences()
        elif action == opacity_down_action:
            self.text_alpha = max(20, self.text_alpha - 10)
            self.apply_style()
            self.save_preferences()
        elif action in color_actions:
            self.text_color_name = color_actions[action]
            self.apply_style()
            self.save_preferences()
        elif action == close_action:
            self.close()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()

        if delta == 0:
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if delta > 0:
                self.adjust_window_width(80)
            else:
                self.adjust_window_width(-80)
        else:
            if delta > 0:
                self.adjust_font_size(2)
            else:
                self.adjust_font_size(-2)

        event.accept()

    def mousePressEvent(self, event) -> None:
        if self.locked:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.locked:
            return

        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_offset = None
        self.save_preferences()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:
        self.save_preferences()

        if getattr(self.main_window, "floating_lyrics_window", None) is self:
            self.main_window.floating_lyrics_window = None

        try:
            self.main_window.update_floating_lyrics_button_state()
        except Exception:
            pass

        super().closeEvent(event)

class PlayQueueDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("播放队列")
        self.setObjectName("playQueueDialog")
        self.setMinimumSize(620, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("播放队列")
        title.setObjectName("playQueueDialogTitle")

        subtitle = QLabel("这里显示接下来会优先播放的歌曲。队列里的歌会先于列表循环 / 随机播放。")
        subtitle.setObjectName("playQueueDialogSubtitle")
        subtitle.setWordWrap(True)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("playQueueList")
        self.queue_list.itemDoubleClicked.connect(self.play_selected_song)

        main_buttons = QHBoxLayout()
        main_buttons.setContentsMargins(0, 0, 0, 0)
        main_buttons.setSpacing(10)

        self.play_btn = QPushButton("立即播放")
        self.play_btn.setObjectName("queuePrimaryButton")
        self.play_btn.clicked.connect(self.play_selected_song)

        self.remove_btn = QPushButton("移除")
        self.remove_btn.setObjectName("queueSecondaryButton")
        self.remove_btn.clicked.connect(self.remove_selected_song)

        self.move_up_btn = QPushButton("上移")
        self.move_up_btn.setObjectName("queueSecondaryButton")
        self.move_up_btn.clicked.connect(self.move_selected_song_up)

        self.move_down_btn = QPushButton("下移")
        self.move_down_btn.setObjectName("queueSecondaryButton")
        self.move_down_btn.clicked.connect(self.move_selected_song_down)

        self.clear_btn = QPushButton("清空队列")
        self.clear_btn.setObjectName("queueDangerButton")
        self.clear_btn.clicked.connect(self.clear_queue)

        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("queueSecondaryButton")
        self.close_btn.clicked.connect(self.accept)

        main_buttons.addWidget(self.play_btn)
        main_buttons.addWidget(self.remove_btn)
        main_buttons.addWidget(self.move_up_btn)
        main_buttons.addWidget(self.move_down_btn)
        main_buttons.addStretch(1)
        main_buttons.addWidget(self.clear_btn)
        main_buttons.addWidget(self.close_btn)

        self.hint_label = QLabel("双击队列里的歌曲可以立即播放。")
        self.hint_label.setObjectName("playQueueHint")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.queue_list, 1)
        layout.addLayout(main_buttons)
        layout.addWidget(self.hint_label)

        self.apply_style()
        if hasattr(self.main_window, "apply_windows_dark_title_bar"):
            QTimer.singleShot(0, lambda: self.main_window.apply_windows_dark_title_bar(self))
        self.refresh_queue_list()

    def apply_style(self) -> None:
        apply_dark_dialog_style(
            self,
            "QDialog#playQueueDialog { background: #0f1117; color: #e8ecf5; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'; }"
            "QLabel#playQueueDialogTitle { color: #ffffff; font-size: 26px; font-weight: 900; }"
            "QLabel#playQueueDialogSubtitle { color: #8f98aa; font-size: 13px; }"
            "QLabel#playQueueHint { color: #8f98aa; font-size: 12px; }"
            "QListWidget#playQueueList { background: #11131a; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 8px; outline: none; }"
            "QListWidget#playQueueList::item { padding: 12px 10px; border-radius: 12px; margin: 3px; }"
            "QListWidget#playQueueList::item:hover { background: rgba(255,255,255,0.07); }"
            "QListWidget#playQueueList::item:selected { background: rgba(59,130,246,0.18); color: #ffffff; border: 1px solid rgba(59,130,246,0.38); }"
            "QPushButton#queuePrimaryButton { background: #3b82f6; color: #ffffff; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; font-weight: 700; }"
            "QPushButton#queuePrimaryButton:hover { background: #5594ff; }"
            "QPushButton#queueSecondaryButton { background: rgba(255,255,255,0.07); color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#queueSecondaryButton:hover { background: rgba(255,255,255,0.11); color: #ffffff; }"
            "QPushButton#queuePrimaryButton:disabled, QPushButton#queueSecondaryButton:disabled, QPushButton#queueDangerButton:disabled { background: #151922; color: #7b8494; border: 1px solid #2a303b; }"
            "QPushButton#queueDangerButton { background: rgba(239,68,68,0.15); color: #ffd7dd; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#queueDangerButton:hover { background: rgba(239,68,68,0.26); color: #ffffff; }"
        )

    def refresh_queue_list(self) -> None:
        if not hasattr(self.main_window, "play_queue"):
            self.main_window.play_queue = []

        valid_queue = []
        for value in self.main_window.play_queue:
            queue_item = self.main_window.playback_queue_item_from_value(value)
            if queue_item is None:
                continue
            if queue_item.kind == "local" and not Path(queue_item.local_path).is_file():
                continue
            valid_queue.append(queue_item)

        if valid_queue != self.main_window.play_queue:
            self.main_window.play_queue = valid_queue
            self.main_window.save_play_queue()

        self.queue_list.clear()

        for index, queue_item in enumerate(self.main_window.play_queue, start=1):
            song_title = self.main_window.get_song_title_for_queue(queue_item)
            kind_text = "在线" if queue_item.kind == "remote" else "本地"
            item = QListWidgetItem(f"{index}. {song_title}  [{kind_text}]")
            item.setData(Qt.ItemDataRole.UserRole, queue_item.to_mapping())
            self.queue_list.addItem(item)

        if self.queue_list.count() > 0 and self.queue_list.currentRow() < 0:
            self.queue_list.setCurrentRow(0)

        self.update_hint()

    def update_hint(self) -> None:
        count = self.queue_list.count()

        if count == 0:
            self.hint_label.setText("播放队列是空的。可以在音乐库里右键歌曲，选择“下一首播放”或“加入播放队列”。")
        else:
            self.hint_label.setText(f"队列里有 {count} 首歌。双击歌曲可以立即播放。")

    def get_selected_index(self) -> int:
        row = self.queue_list.currentRow()

        if row < 0 or row >= len(self.main_window.play_queue):
            QMessageBox.information(self, "播放队列", "请先选择队列里的一首歌。")
            return -1

        return row

    def play_selected_song(self) -> None:
        row = self.get_selected_index()

        if row < 0:
            return

        queue_item = self.main_window.play_queue.pop(row)
        self.main_window.save_play_queue()
        self.main_window.remember_queue_return_state()
        if self.main_window.play_queue_item(queue_item, update_context=False):
            self.refresh_queue_list()
            self.accept()
        else:
            QMessageBox.information(self, "播放队列", "这首歌无法播放，可能文件已经不存在。")
            self.refresh_queue_list()

    def remove_selected_song(self) -> None:
        row = self.get_selected_index()

        if row < 0:
            return

        self.main_window.play_queue.pop(row)
        self.main_window.save_play_queue()
        self.refresh_queue_list()

        if self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(min(row, self.queue_list.count() - 1))

    def move_selected_song_up(self) -> None:
        row = self.get_selected_index()

        if row <= 0:
            return

        queue = self.main_window.play_queue
        queue[row - 1], queue[row] = queue[row], queue[row - 1]
        self.main_window.save_play_queue()
        self.refresh_queue_list()
        self.queue_list.setCurrentRow(row - 1)

    def move_selected_song_down(self) -> None:
        row = self.get_selected_index()

        if row < 0 or row >= len(self.main_window.play_queue) - 1:
            return

        queue = self.main_window.play_queue
        queue[row + 1], queue[row] = queue[row], queue[row + 1]
        self.main_window.save_play_queue()
        self.refresh_queue_list()
        self.queue_list.setCurrentRow(row + 1)

    def clear_queue(self) -> None:
        if not self.main_window.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列已经是空的。")
            return

        reply = QMessageBox.question(
            self,
            "清空播放队列",
            "确定要清空当前播放队列吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.main_window.play_queue.clear()
        self.main_window.save_play_queue()
        self.refresh_queue_list()

class SettingsDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        self.main_window = main_window
        self.setWindowTitle("HushPlayer 设置")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(520)

        settings = self.main_window.get_hush_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        title = QLabel("设置")
        title.setObjectName("settingsDialogTitle")

        subtitle = QLabel("管理播放恢复、歌词显示与本地音乐文件夹。")
        subtitle.setObjectName("settingsDialogSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        playback_card = QFrame()
        playback_card.setObjectName("settingsCard")
        playback_layout = QVBoxLayout(playback_card)
        playback_layout.setContentsMargins(18, 16, 18, 16)
        playback_layout.setSpacing(12)

        playback_title = QLabel("播放")
        playback_title.setObjectName("settingsCardTitle")

        self.restore_checkbox = QCheckBox("启动时恢复上次播放的歌曲和进度")
        self.restore_checkbox.setChecked(bool(settings.get("restore_last_playback", True)))

        playback_layout.addWidget(playback_title)
        playback_layout.addWidget(self.restore_checkbox)

        immersive_card = QFrame()
        immersive_card.setObjectName("settingsCard")
        immersive_layout = QVBoxLayout(immersive_card)
        immersive_layout.setContentsMargins(18, 16, 18, 16)
        immersive_layout.setSpacing(12)

        immersive_title = QLabel("沉浸歌词")
        immersive_title.setObjectName("settingsCardTitle")

        self.cover_background_checkbox = QCheckBox("默认使用封面模糊背景")
        self.cover_background_checkbox.setChecked(bool(settings.get("immersive_cover_background_enabled", True)))

        self.auto_hide_checkbox = QCheckBox("默认自动隐藏沉浸歌词 UI")
        self.auto_hide_checkbox.setChecked(bool(settings.get("immersive_auto_hide_ui", True)))

        alpha_row = QHBoxLayout()
        alpha_row.setContentsMargins(0, 0, 0, 0)
        alpha_row.setSpacing(12)

        self.alpha_label = QLabel()
        self.alpha_label.setObjectName("settingsValueLabel")

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(35, 100)
        self.alpha_slider.setValue(int(settings.get("immersive_background_alpha", 68)))
        self.alpha_slider.valueChanged.connect(self.update_alpha_label)

        alpha_row.addWidget(QLabel("遮罩不透明度"))
        alpha_row.addWidget(self.alpha_slider, 1)
        alpha_row.addWidget(self.alpha_label)

        self.update_alpha_label(self.alpha_slider.value())

        immersive_layout.addWidget(immersive_title)
        immersive_layout.addWidget(self.cover_background_checkbox)
        immersive_layout.addWidget(self.auto_hide_checkbox)
        immersive_layout.addLayout(alpha_row)

        floating_card = QFrame()
        floating_card.setObjectName("settingsCard")
        floating_layout = QVBoxLayout(floating_card)
        floating_layout.setContentsMargins(18, 16, 18, 16)
        floating_layout.setSpacing(12)

        floating_title = QLabel("桌面歌词")
        floating_title.setObjectName("settingsCardTitle")

        self.floating_color_combo = QComboBox()
        self.floating_color_combo.addItem("白色", "white")
        self.floating_color_combo.addItem("黑色", "black")
        self.floating_color_combo.addItem("黄色", "yellow")
        self.floating_color_combo.addItem("蓝色", "blue")
        self.floating_color_combo.addItem("绿色", "green")
        self.floating_color_combo.addItem("粉色", "pink")
        self.floating_color_combo.addItem("紫色", "purple")
        current_floating_color = str(settings.get("floating_lyrics_color", "white"))
        color_index = self.floating_color_combo.findData(current_floating_color)

        if color_index >= 0:
            self.floating_color_combo.setCurrentIndex(color_index)

        floating_color_row = QHBoxLayout()
        floating_color_row.setContentsMargins(0, 0, 0, 0)
        floating_color_row.setSpacing(12)
        floating_color_row.addWidget(QLabel("默认歌词颜色"))
        floating_color_row.addWidget(self.floating_color_combo, 1)

        floating_opacity_row = QHBoxLayout()
        floating_opacity_row.setContentsMargins(0, 0, 0, 0)
        floating_opacity_row.setSpacing(12)

        self.floating_opacity_label = QLabel()
        self.floating_opacity_label.setObjectName("settingsValueLabel")

        self.floating_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_opacity_slider.setRange(20, 100)
        self.floating_opacity_slider.setValue(int(settings.get("floating_lyrics_opacity", 100)))
        self.floating_opacity_slider.valueChanged.connect(self.update_floating_opacity_label)

        floating_opacity_row.addWidget(QLabel("默认不透明度"))
        floating_opacity_row.addWidget(self.floating_opacity_slider, 1)
        floating_opacity_row.addWidget(self.floating_opacity_label)

        floating_font_row = QHBoxLayout()
        floating_font_row.setContentsMargins(0, 0, 0, 0)
        floating_font_row.setSpacing(12)

        self.floating_font_label = QLabel()
        self.floating_font_label.setObjectName("settingsValueLabel")

        self.floating_font_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_font_slider.setRange(22, 84)
        self.floating_font_slider.setValue(int(settings.get("floating_lyrics_font_size", 42)))
        self.floating_font_slider.valueChanged.connect(self.update_floating_font_label)

        floating_font_row.addWidget(QLabel("默认字号"))
        floating_font_row.addWidget(self.floating_font_slider, 1)
        floating_font_row.addWidget(self.floating_font_label)

        floating_width_row = QHBoxLayout()
        floating_width_row.setContentsMargins(0, 0, 0, 0)
        floating_width_row.setSpacing(12)

        self.floating_width_label = QLabel()
        self.floating_width_label.setObjectName("settingsValueLabel")

        self.floating_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.floating_width_slider.setRange(420, 1600)
        self.floating_width_slider.setValue(int(settings.get("floating_lyrics_width", 980)))
        self.floating_width_slider.valueChanged.connect(self.update_floating_width_label)

        floating_width_row.addWidget(QLabel("默认宽度"))
        floating_width_row.addWidget(self.floating_width_slider, 1)
        floating_width_row.addWidget(self.floating_width_label)

        self.floating_auto_open_checkbox = QCheckBox("启动时自动打开桌面歌词")
        self.floating_auto_open_checkbox.setChecked(bool(settings.get("floating_lyrics_auto_open", False)))

        reset_floating_position_btn = QPushButton("重置桌面歌词位置")
        reset_floating_position_btn.setObjectName("settingsSecondaryButton")
        reset_floating_position_btn.clicked.connect(self.reset_floating_lyrics_position)

        floating_layout.addWidget(floating_title)
        floating_layout.addLayout(floating_color_row)
        floating_layout.addLayout(floating_opacity_row)
        floating_layout.addLayout(floating_font_row)
        floating_layout.addLayout(floating_width_row)
        floating_layout.addWidget(self.floating_auto_open_checkbox)
        floating_layout.addWidget(reset_floating_position_btn)

        self.update_floating_opacity_label(self.floating_opacity_slider.value())
        self.update_floating_font_label(self.floating_font_slider.value())
        self.update_floating_width_label(self.floating_width_slider.value())

        scan_card = QFrame()
        scan_card.setObjectName("settingsCard")
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(18, 16, 18, 16)
        scan_layout.setSpacing(12)

        scan_title = QLabel("音乐文件夹 / 网盘同步目录")
        scan_title.setObjectName("settingsCardTitle")

        scan_hint = QLabel("可以添加百度网盘同步空间、夸克网盘下载目录、OneDrive、NAS 或本地音乐文件夹。如果播放卡顿，建议在网盘客户端中把音乐文件设为本地可用。")
        scan_hint.setObjectName("settingsHint")
        scan_hint.setWordWrap(True)

        self.music_scan_folder_list = QListWidget()
        self.music_scan_folder_list.setObjectName("settingsFolderList")
        self.music_scan_folder_list.setMinimumHeight(110)

        for folder in settings.get("music_scan_folders", []):
            if isinstance(folder, str) and folder.strip():
                self.music_scan_folder_list.addItem(folder.strip())

        scan_button_row = QHBoxLayout()
        scan_button_row.setContentsMargins(0, 0, 0, 0)
        scan_button_row.setSpacing(10)

        add_scan_folder_btn = QPushButton("添加文件夹")
        add_scan_folder_btn.setObjectName("settingsSecondaryButton")
        add_scan_folder_btn.clicked.connect(self.add_music_scan_folder)

        remove_scan_folder_btn = QPushButton("移除选中文件夹")
        remove_scan_folder_btn.setObjectName("settingsSecondaryButton")
        remove_scan_folder_btn.clicked.connect(self.remove_music_scan_folder)

        scan_now_btn = QPushButton("手动重新扫描")
        scan_now_btn.setObjectName("settingsSecondaryButton")
        scan_now_btn.clicked.connect(self.scan_music_folders_now)

        scan_button_row.addWidget(add_scan_folder_btn)
        scan_button_row.addWidget(remove_scan_folder_btn)
        scan_button_row.addWidget(scan_now_btn)
        scan_button_row.addStretch(1)

        self.auto_scan_checkbox = QCheckBox("启动时自动扫描这些文件夹")
        self.auto_scan_checkbox.setChecked(bool(settings.get("auto_scan_music_folders_on_startup", True)))

        import_mode_row = QHBoxLayout()
        import_mode_row.setContentsMargins(0, 0, 0, 0)
        import_mode_row.setSpacing(12)

        self.music_scan_import_mode_combo = QComboBox()
        self.music_scan_import_mode_combo.addItem("进入待导入列表，手动确认", "pending")
        self.music_scan_import_mode_combo.addItem("自动加入音乐库", "auto")
        current_import_mode = str(settings.get("music_scan_import_mode", "pending"))
        import_mode_index = self.music_scan_import_mode_combo.findData(current_import_mode)

        if import_mode_index >= 0:
            self.music_scan_import_mode_combo.setCurrentIndex(import_mode_index)

        import_mode_row.addWidget(QLabel("扫描新音乐后的处理方式"))
        import_mode_row.addWidget(self.music_scan_import_mode_combo, 1)
        scan_cloud_hint = QLabel("推荐用百度网盘客户端的同步空间，或夸克网盘的下载目录，把音乐文件同步/下载到本地后由 HushPlayer 自动扫描。这样最稳定，也不需要登录网盘 API。")
        scan_cloud_hint.setObjectName("settingsHint")
        scan_cloud_hint.setWordWrap(True)

        scan_layout.addWidget(scan_title)
        scan_layout.addWidget(scan_hint)
        scan_layout.addWidget(self.music_scan_folder_list)
        scan_layout.addLayout(scan_button_row)
        scan_layout.addWidget(self.auto_scan_checkbox)
        scan_layout.addLayout(import_mode_row)
        scan_layout.addWidget(scan_cloud_hint)
        cache_card = QFrame()
        cache_card.setObjectName("settingsCard")
        cache_layout = QVBoxLayout(cache_card)
        cache_layout.setContentsMargins(18, 16, 18, 16)
        cache_layout.setSpacing(12)

        cache_title = QLabel("缓存")
        cache_title.setObjectName("settingsCardTitle")

        cache_hint = QLabel("如果之前某些歌封面或歌词搜不到，清理失败缓存后可以右键歌曲重新搜索。")
        cache_hint.setObjectName("settingsHint")
        cache_hint.setWordWrap(True)

        clear_missing_btn = QPushButton("清理封面 / 歌词失败缓存")
        clear_missing_btn.setObjectName("settingsSecondaryButton")
        clear_missing_btn.clicked.connect(self.clear_missing_cache)

        cache_layout.addWidget(cache_title)
        cache_layout.addWidget(cache_hint)
        cache_layout.addWidget(clear_missing_btn)

        layout.addWidget(playback_card)
        layout.addWidget(immersive_card)
        layout.addWidget(floating_card)
        layout.addWidget(scan_card)
        layout.addWidget(cache_card)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.setSpacing(12)

        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("settingsPrimaryButton")
        save_btn.clicked.connect(self.save_settings)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("settingsSecondaryButton")
        cancel_btn.clicked.connect(self.reject)

        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)

        layout.addLayout(button_row)

        self.apply_style()

    def apply_style(self) -> None:
        apply_dark_dialog_style(
            self,
            "QDialog#settingsDialog { background: #0f1117; color: #e8ecf5; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'; }"
            "QDialog#settingsDialog QLabel { color: #b5bbc7; }"
            "QLabel#settingsDialogTitle { color: #ffffff; font-size: 26px; font-weight: 900; }"
            "QLabel#settingsDialogSubtitle { color: #8f98aa; font-size: 13px; }"
            "QFrame#settingsCard { background: #151922; border: 1px solid rgba(255,255,255,0.07); border-radius: 18px; }"
            "QLabel#settingsCardTitle { color: #ffffff; font-size: 16px; font-weight: 800; }"
            "QLabel#settingsHint { color: #8f98aa; font-size: 12px; }"
            "QLabel#settingsValueLabel { color: #d9deea; font-size: 12px; min-width: 42px; }"
            "QCheckBox { color: #dfe4ee; font-size: 13px; spacing: 9px; }"
            "QCheckBox:disabled { color: #7b8494; }"
            "QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid rgba(255,255,255,0.14); background: #11131a; }"
            "QCheckBox::indicator:checked { background: #3b82f6; border: 1px solid #3b82f6; }"
            "QComboBox { background: #11131a; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 7px 10px; }"
            "QComboBox:hover, QComboBox:focus { border-color: #4c8dff; }"
            "QComboBox:disabled { background: #0d0f14; color: #7b8494; border-color: #2a303b; }"
            "QComboBox QAbstractItemView { background: #1a1f2b; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.11); selection-background-color: rgba(59,130,246,0.18); selection-color: #ffffff; outline: none; }"
            "QListWidget#settingsFolderList { background: #11131a; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 7px; outline: none; }"
            "QListWidget#settingsFolderList::item { padding: 8px 10px; border-radius: 9px; margin: 2px 0; }"
            "QListWidget#settingsFolderList::item:hover { background: rgba(255,255,255,0.07); }"
            "QListWidget#settingsFolderList::item:selected { background: rgba(59,130,246,0.18); color: #ffffff; border: 1px solid rgba(59,130,246,0.38); }"
            "QListWidget#settingsFolderList:disabled { background: #0d0f14; color: #7b8494; border-color: #2a303b; }"
            "QPushButton#settingsPrimaryButton { background: #3b82f6; color: #ffffff; border: none; border-radius: 12px; padding: 10px 18px; font-size: 13px; font-weight: 700; }"
            "QPushButton#settingsPrimaryButton:hover { background: #5594ff; }"
            "QPushButton#settingsSecondaryButton { background: rgba(255,255,255,0.07); color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#settingsSecondaryButton:hover { background: rgba(255,255,255,0.11); color: #ffffff; }"
            "QPushButton#settingsPrimaryButton:disabled, QPushButton#settingsSecondaryButton:disabled { background: #151922; color: #7b8494; border: 1px solid #2a303b; }"
            "QSlider::groove:horizontal { height: 5px; background: rgba(255,255,255,0.14); border-radius: 3px; }"
            "QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; background: #ffffff; border-radius: 8px; }"
            "QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 3px; }"
            "QSlider:disabled::groove:horizontal { background: #2a303b; }"
            "QSlider:disabled::handle:horizontal { background: #7b8494; }"
            "QSlider:disabled::sub-page:horizontal { background: #3a4352; }"
        )

    def get_music_scan_folders_from_list(self) -> list[str]:
        folders = []
        seen = set()

        if not hasattr(self, "music_scan_folder_list"):
            return folders

        for index in range(self.music_scan_folder_list.count()):
            item = self.music_scan_folder_list.item(index)
            folder = item.text().strip() if item is not None else ""

            if not folder:
                continue

            key = folder.lower()

            if key in seen:
                continue

            seen.add(key)
            folders.append(folder)

        return folders

    def add_music_scan_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "添加音乐文件夹 / 网盘同步目录",
            str(Path.home()),
        )

        if not folder_path:
            return

        try:
            folder_path = str(Path(folder_path).resolve())
        except Exception:
            folder_path = str(folder_path)

        existing_folders = {folder.lower() for folder in self.get_music_scan_folders_from_list()}

        if folder_path.lower() in existing_folders:
            QMessageBox.information(self, "音乐文件夹", "这个文件夹已经在列表里。")
            return

        self.music_scan_folder_list.addItem(folder_path)

    def remove_music_scan_folder(self) -> None:
        row = self.music_scan_folder_list.currentRow()

        if row < 0:
            QMessageBox.information(self, "音乐文件夹", "请先选择要移除的文件夹。")
            return

        self.music_scan_folder_list.takeItem(row)

    def collect_settings_updates(self) -> dict:
        return {
            "restore_last_playback": self.restore_checkbox.isChecked(),
            "immersive_cover_background_enabled": self.cover_background_checkbox.isChecked(),
            "immersive_auto_hide_ui": self.auto_hide_checkbox.isChecked(),
            "immersive_background_alpha": int(self.alpha_slider.value()),
            "floating_lyrics_color": self.floating_color_combo.currentData(),
            "floating_lyrics_opacity": int(self.floating_opacity_slider.value()),
            "floating_lyrics_font_size": int(self.floating_font_slider.value()),
            "floating_lyrics_width": int(self.floating_width_slider.value()),
            "floating_lyrics_auto_open": self.floating_auto_open_checkbox.isChecked(),
            "music_scan_folders": self.get_music_scan_folders_from_list(),
            "auto_scan_music_folders_on_startup": self.auto_scan_checkbox.isChecked(),
            "music_scan_import_mode": self.music_scan_import_mode_combo.currentData(),
        }

    def scan_music_folders_now(self) -> None:
        self.main_window.save_hush_settings(
            self.collect_settings_updates(),
            immediate=True,
        )
        self.main_window.scan_music_folders(manual=True)

    def update_alpha_label(self, value: int) -> None:
        self.alpha_label.setText(f"{int(value)}%")

    def update_floating_opacity_label(self, value: int) -> None:
        self.floating_opacity_label.setText(f"{int(value)}%")

    def update_floating_font_label(self, value: int) -> None:
        self.floating_font_label.setText(f"{int(value)}px")

    def update_floating_width_label(self, value: int) -> None:
        self.floating_width_label.setText(f"{int(value)}px")

    def reset_floating_lyrics_position(self) -> None:
        self.main_window.reset_floating_lyrics_position_settings()
        QMessageBox.information(self, "桌面歌词", "桌面歌词位置已重置。")

    def save_settings(self) -> None:
        self.main_window.save_hush_settings(
            self.collect_settings_updates(),
            immediate=True,
        )
        self.main_window.apply_runtime_settings()
        QMessageBox.information(self, "设置", "设置已保存。")
        self.accept()

    def clear_missing_cache(self) -> None:
        removed_count = self.main_window.clear_missing_cache_files()
        QMessageBox.information(self, "缓存", f"已清理 {removed_count} 个失败缓存文件。")


class MetadataMatchDialog(QDialog):
    def __init__(self, song_data: dict, candidates: list[dict], parent=None) -> None:
        super().__init__(parent)

        self.candidates = candidates
        self.selected_candidate = None

        self.setWindowTitle("联网匹配歌曲信息")
        self.setObjectName("metadataMatchDialog")
        self.setMinimumSize(720, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("选择匹配结果")
        title.setObjectName("metadataDialogTitle")

        subtitle = QLabel(
            f"当前歌曲：{song_data.get('title', '未知歌曲')} · {song_data.get('artist', '未知艺术家')}"
        )
        subtitle.setObjectName("metadataDialogSubtitle")
        subtitle.setWordWrap(True)

        self.candidate_list = QListWidget()
        self.candidate_list.setObjectName("metadataCandidateList")
        self.candidate_list.itemDoubleClicked.connect(self.accept_selected_candidate)

        for candidate in candidates:
            display_text = (
                f"{candidate.get('title', '未知歌曲')}\n"
                f"{candidate.get('artist', '未知艺术家')} · "
                f"{candidate.get('album', '未知专辑')} · "
                f"{candidate.get('release_date', '') or '未知日期'} · "
                f"匹配分数 {candidate.get('score', '')}"
            )
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.candidate_list.addItem(item)

        if self.candidate_list.count() > 0:
            self.candidate_list.setCurrentRow(0)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(12)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("metadataSecondaryButton")
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton("应用")
        apply_btn.setObjectName("metadataPrimaryButton")
        apply_btn.clicked.connect(self.accept_selected_candidate)

        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(apply_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.candidate_list, 1)
        layout.addLayout(button_row)

        apply_dark_dialog_style(
            self,
            "QDialog#metadataMatchDialog { background: #0f1117; color: #e8ecf5; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'; }"
            "QLabel#metadataDialogTitle { color: #ffffff; font-size: 24px; font-weight: 900; }"
            "QLabel#metadataDialogSubtitle { color: #8f98aa; font-size: 13px; }"
            "QListWidget#metadataCandidateList { background: #11131a; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 8px; outline: none; }"
            "QListWidget#metadataCandidateList::item { padding: 11px 12px; border-radius: 12px; margin: 3px 0; }"
            "QListWidget#metadataCandidateList::item:hover { background: rgba(255,255,255,0.07); }"
            "QListWidget#metadataCandidateList::item:selected { background: rgba(59,130,246,0.18); color: #ffffff; border: 1px solid rgba(59,130,246,0.38); }"
            "QPushButton#metadataPrimaryButton { background: #3b82f6; color: #ffffff; border: none; border-radius: 12px; padding: 10px 18px; font-size: 13px; font-weight: 700; }"
            "QPushButton#metadataPrimaryButton:hover { background: #5594ff; }"
            "QPushButton#metadataSecondaryButton { background: rgba(255,255,255,0.07); color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#metadataSecondaryButton:hover { background: rgba(255,255,255,0.11); color: #ffffff; }"
            "QPushButton#metadataPrimaryButton:disabled, QPushButton#metadataSecondaryButton:disabled { background: #151922; color: #7b8494; border: 1px solid #2a303b; }"
        )

    def accept_selected_candidate(self) -> None:
        item = self.candidate_list.currentItem()

        if item is None:
            QMessageBox.information(self, "联网匹配歌曲信息", "请先选择一个候选结果。")
            return

        candidate = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(candidate, dict):
            QMessageBox.information(self, "联网匹配歌曲信息", "这个候选结果不可用。")
            return

        self.selected_candidate = candidate
        self.accept()


class TransparentOpacitySlider(QSlider):
    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("immersiveOpacitySlider")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMinimumHeight(28)
        self.setFixedHeight(28)
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        left = 9
        right = self.width() - 9
        width = max(1, right - left)
        center_y = self.height() / 2
        track_rect = QRectF(left, center_y - 2, width, 4)

        if self.isEnabled():
            base_color = QColor(255, 255, 255, 22)
            active_color = QColor(255, 255, 255, 95)
            handle_color = QColor(255, 255, 255, 230)
            border_color = QColor(255, 255, 255, 55)
        else:
            base_color = QColor(255, 255, 255, 12)
            active_color = QColor(255, 255, 255, 28)
            handle_color = QColor(255, 255, 255, 70)
            border_color = QColor(255, 255, 255, 24)

        base_path = QPainterPath()
        base_path.addRoundedRect(track_rect, 2, 2)
        painter.fillPath(base_path, base_color)

        value_range = max(1, self.maximum() - self.minimum())
        ratio = (self.value() - self.minimum()) / value_range
        ratio = max(0.0, min(1.0, ratio))

        active_rect = QRectF(left, center_y - 2, width * ratio, 4)
        active_path = QPainterPath()
        active_path.addRoundedRect(active_rect, 2, 2)
        painter.fillPath(active_path, active_color)

        handle_x = left + width * ratio
        handle_rect = QRectF(handle_x - 8, center_y - 8, 16, 16)

        painter.setPen(QPen(border_color, 1))
        painter.setBrush(handle_color)
        painter.drawEllipse(handle_rect)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_value_from_position(event.position().x())
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.set_value_from_position(event.position().x())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def set_value_from_position(self, x_position: float) -> None:
        left = 9
        right = max(left + 1, self.width() - 9)
        ratio = (float(x_position) - left) / max(1, right - left)
        ratio = max(0.0, min(1.0, ratio))
        value = self.minimum() + round(ratio * (self.maximum() - self.minimum()))
        self.setValue(int(value))


class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.transparent_mode = True
        self.cover_background_enabled = bool(
            main_window.get_user_setting("immersive_cover_background_enabled", True)
        )
        self.background_alpha = int(
            main_window.get_user_setting("immersive_background_alpha", 68)
        )
        self.cover_background_pixmap = None
        self.ui_visible = True
        self.auto_hide_enabled = bool(
            main_window.get_user_setting("immersive_auto_hide_ui", True)
        )

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(1000, 700)
        self.setMouseTracking(True)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(1.0)

        self.hide_ui_timer = QTimer(self)
        self.hide_ui_timer.setSingleShot(True)
        self.hide_ui_timer.timeout.connect(self.hide_controls_if_needed)

        self.cover_background_label = QLabel(self)
        self.cover_background_label.setObjectName("immersiveCoverBackground")
        self.cover_background_label.setScaledContents(True)
        self.cover_background_label.hide()

        self.cover_blur_effect = QGraphicsBlurEffect(self.cover_background_label)
        self.cover_blur_effect.setBlurRadius(42)
        self.cover_background_label.setGraphicsEffect(self.cover_blur_effect)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.background_panel = QFrame()
        self.background_panel.setObjectName("immersiveBackgroundPanel")
        self.background_panel.setMouseTracking(True)
        self.background_panel.installEventFilter(self)

        outer_layout.addWidget(self.background_panel)

        layout = QVBoxLayout(self.background_panel)
        layout.setContentsMargins(46, 34, 46, 34)
        layout.setSpacing(22)

        self.control_header = QFrame()
        self.control_header.setObjectName("immersiveControlHeader")
        self.control_header.setMouseTracking(True)
        self.control_header.installEventFilter(self)

        header = QHBoxLayout(self.control_header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(7)

        self.song_title = ElidedLabel("还没有播放音乐")
        self.song_title.setObjectName("immersiveSongTitle")
        self.song_title.setMinimumWidth(520)

        self.song_artist = ElidedLabel("双击歌曲或右键播放后打开沉浸歌词")
        self.song_artist.setObjectName("immersiveSongArtist")
        self.song_artist.setMinimumWidth(520)

        self.status_label = QLabel("等待播放歌曲")
        self.status_label.setObjectName("immersiveStatus")

        title_box.addWidget(self.song_title)
        title_box.addWidget(self.song_artist)
        title_box.addWidget(self.status_label)

        self.fullscreen_btn = QPushButton("副屏全屏")
        self.fullscreen_btn.setObjectName("immersiveButton")
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self.show_on_best_screen)

        self.window_btn = QPushButton("窗口模式")
        self.window_btn.setObjectName("immersiveButton")
        self.window_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.window_btn.clicked.connect(self.show_windowed)

        self.transparent_btn = QPushButton("切换纯黑")
        self.transparent_btn.setObjectName("immersiveButton")
        self.transparent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transparent_btn.clicked.connect(self.toggle_transparent_mode)

        self.cover_bg_btn = QPushButton("切换纯色")
        self.cover_bg_btn.setObjectName("immersiveButton")
        self.cover_bg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover_bg_btn.clicked.connect(self.toggle_cover_background)

        self.auto_hide_btn = QPushButton("常显 UI")
        self.auto_hide_btn.setObjectName("immersiveButton")
        self.auto_hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_hide_btn.clicked.connect(self.toggle_auto_hide)

        self.close_btn = QPushButton("退出沉浸")
        self.close_btn.setObjectName("immersiveButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        button_box = QHBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(self.fullscreen_btn)
        button_box.addWidget(self.window_btn)
        button_box.addWidget(self.transparent_btn)
        button_box.addWidget(self.cover_bg_btn)
        button_box.addWidget(self.auto_hide_btn)
        button_box.addWidget(self.close_btn)

        self.opacity_panel = QFrame()
        self.opacity_panel.setObjectName("immersiveOpacityPanel")
        self.opacity_panel.setMouseTracking(True)
        self.opacity_panel.installEventFilter(self)

        alpha_box = QHBoxLayout(self.opacity_panel)
        alpha_box.setContentsMargins(0, 0, 0, 0)
        alpha_box.setSpacing(10)

        self.alpha_label = QLabel("遮罩不透明度 68%")
        self.alpha_label.setObjectName("immersiveOpacityLabel")

        self.alpha_slider = TransparentOpacitySlider()
        self.alpha_slider.setRange(35, 100)
        self.alpha_slider.setValue(self.background_alpha)
        self.alpha_slider.setFixedWidth(240)
        self.alpha_slider.setAutoFillBackground(False)
        self.alpha_slider.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.alpha_slider.valueChanged.connect(self.change_background_alpha)

        alpha_box.addWidget(self.alpha_label)
        alpha_box.addWidget(self.alpha_slider)

        control_box = QVBoxLayout()
        control_box.setContentsMargins(0, 0, 0, 0)
        control_box.setSpacing(10)
        control_box.addLayout(button_box)
        control_box.addWidget(self.opacity_panel)

        header.addLayout(title_box, 1)
        header.addLayout(control_box)

        self.lyrics_view = LyricsView()
        self.lyrics_view.setObjectName("immersiveLyricsView")
        self.lyrics_view.setMouseTracking(True)
        self.lyrics_view.installEventFilter(self)

        if self.lyrics_view.viewport():
            self.lyrics_view.viewport().setMouseTracking(True)
            self.lyrics_view.viewport().installEventFilter(self)

        self.lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "播放一首歌后，这里会显示沉浸歌词",
        )

        self.footer = QLabel("移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：封面模糊背景")
        self.footer.setObjectName("immersiveFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setMouseTracking(True)
        self.footer.installEventFilter(self)

        layout.addWidget(self.control_header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.footer)

        self.apply_immersive_style()
        self.show_controls_temporarily()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.Enter,
            QEvent.Type.MouseButtonPress,
        ):
            self.show_controls_temporarily()

        return super().eventFilter(watched, event)

    def mouseMoveEvent(self, event) -> None:
        self.show_controls_temporarily()
        super().mouseMoveEvent(event)

    def show_controls_temporarily(self) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)

        if not self.ui_visible:
            self.control_header.show()
            self.footer.show()
            self.ui_visible = True

        if self.auto_hide_enabled:
            self.hide_ui_timer.start(2200)

    def hide_controls_if_needed(self) -> None:
        if not self.auto_hide_enabled:
            return

        if not self.isVisible():
            return

        self.control_header.hide()
        self.footer.hide()
        self.ui_visible = False
        self.setCursor(Qt.CursorShape.BlankCursor)

    def toggle_auto_hide(self) -> None:
        self.auto_hide_enabled = not self.auto_hide_enabled

        if self.auto_hide_enabled:
            self.auto_hide_btn.setText("常显 UI")
            self.show_controls_temporarily()
        else:
            self.hide_ui_timer.stop()
            self.control_header.show()
            self.footer.show()
            self.ui_visible = True
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.auto_hide_btn.setText("隐藏 UI")

        self.apply_immersive_style()

    def apply_immersive_style(self) -> None:
        self.setWindowOpacity(1.0)

        if self.transparent_mode:
            alpha = max(0, min(255, int(self.background_alpha / 100 * 255)))
            background = f"rgba(5, 6, 9, {alpha})"
            button_background = "rgba(31, 35, 44, 190)"
            mode_name = "封面模糊背景" if self.cover_background_enabled else "半透明纯色背景"
            footer_text = f"移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：{mode_name} · 遮罩不透明度 {self.background_alpha}%"
            button_text = "切换纯黑"
            slider_enabled = True
        else:
            background = "#050609"
            button_background = "#1f232c"
            footer_text = "移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：纯黑背景"
            button_text = "切换半透明"
            slider_enabled = False

        if self.cover_background_enabled:
            cover_button_text = "切换纯色"
        else:
            cover_button_text = "切换封面"

        if self.auto_hide_enabled:
            auto_hide_text = "常显 UI"
        else:
            auto_hide_text = "隐藏 UI"

        self.footer.setText(footer_text)
        self.transparent_btn.setText(button_text)
        self.cover_bg_btn.setText(cover_button_text)
        self.auto_hide_btn.setText(auto_hide_text)
        self.alpha_label.setText(f"遮罩不透明度 {self.background_alpha}%")
        self.alpha_slider.setEnabled(slider_enabled)

        self.setStyleSheet(
            "QWidget#immersiveLyricsWindow { background: transparent; color: #ffffff; font-family: 'Microsoft YaHei UI'; }"
            f"QFrame#immersiveBackgroundPanel {{ background: {background}; }}"
            "QFrame#immersiveControlHeader { background: rgba(0, 0, 0, 10); border: none; border-radius: 16px; }"
            "QLabel#immersiveSongTitle { color: #ffffff; font-size: 30px; font-weight: 900; }"
            "QLabel#immersiveSongArtist { color: #d0d5df; font-size: 15px; }"
            "QLabel#immersiveStatus { color: #9aa3b2; font-size: 12px; }"
            "QLabel#immersiveFooter { color: #8e96a5; font-size: 12px; }"
            "QFrame#immersiveOpacityPanel { background: transparent; border: none; }"
            "QLabel#immersiveOpacityLabel { background: transparent; color: #c7ceda; font-size: 12px; }"
            f"QPushButton#immersiveButton {{ background: {button_background}; color: #dfe3ec; border: none; border-radius: 12px; padding: 10px 14px; font-size: 13px; }}"
            "QPushButton#immersiveButton:hover { background: #2f68d8; color: #ffffff; }"
            "QSlider#immersiveOpacitySlider { background: transparent; border: none; }"
            "QScrollArea#immersiveLyricsView, QScrollArea#lyricsView { background: transparent; border: none; }"
            "QWidget#lyricsContent { background: transparent; }"
            "QLabel#lyricPlaceholderTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#lyricPlaceholderSubtitle { color: #c1c7d2; font-size: 15px; }"
            "QLabel#lyricLine { color: rgba(215,222,235,90); font-size: 24px; font-weight: 600; padding: 42px 10px; }"
            "QLabel#lyricLine[lyricState='near'] { color: rgba(236,240,248,155); font-size: 44px; font-weight: 800; padding: 70px 10px; }"
            "QLabel#lyricLine[lyricState='current'] { color: #ffffff; font-size: 118px; font-weight: 950; padding: 104px 10px; }"
        )

        self.refresh_cover_background()

    def change_background_alpha(self, value: int) -> None:
        self.background_alpha = int(value)
        self.apply_immersive_style()

    def toggle_transparent_mode(self) -> None:
        self.transparent_mode = not self.transparent_mode
        self.apply_immersive_style()
        self.show_controls_temporarily()

    def toggle_cover_background(self) -> None:
        self.cover_background_enabled = not self.cover_background_enabled
        self.apply_immersive_style()
        self.show_controls_temporarily()

    def update_background_cover(self, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            self.cover_background_pixmap = None
        else:
            self.cover_background_pixmap = pixmap.copy()

        self.refresh_cover_background()

    def refresh_cover_background(self) -> None:
        if not hasattr(self, "cover_background_label"):
            return

        if (
            not self.transparent_mode
            or not self.cover_background_enabled
            or self.cover_background_pixmap is None
            or self.cover_background_pixmap.isNull()
        ):
            self.cover_background_label.hide()
            return

        target_size = self.size()

        if target_size.width() <= 0 or target_size.height() <= 0:
            self.cover_background_label.hide()
            return

        scaled = self.cover_background_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        crop_x = max(0, (scaled.width() - target_size.width()) // 2)
        crop_y = max(0, (scaled.height() - target_size.height()) // 2)

        cropped = scaled.copy(
            crop_x,
            crop_y,
            target_size.width(),
            target_size.height(),
        )

        self.cover_background_label.setGeometry(self.rect())
        self.cover_background_label.setPixmap(cropped)
        self.cover_background_label.show()
        self.cover_background_label.lower()
        self.background_panel.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_cover_background()

    def show_on_best_screen(self) -> None:
        screens = QApplication.screens()
        target_screen = None

        if len(screens) >= 2:
            target_screen = screens[1]
        elif screens:
            target_screen = screens[0]

        if target_screen:
            self.setGeometry(target_screen.availableGeometry())

        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.show_controls_temporarily()

    def show_windowed(self) -> None:
        self.showNormal()
        self.resize(1100, 720)
        self.raise_()
        self.activateWindow()
        self.show_controls_temporarily()

    def update_song_info(self, title: str, artist_album: str, status: str) -> None:
        self.song_title.setText(title)
        self.song_artist.setText(artist_album)
        self.status_label.setText(status)

    def set_lyrics(self, lyrics: list[tuple[int, str]]) -> None:
        if lyrics:
            self.lyrics_view.set_lyrics(lyrics)
        else:
            self.lyrics_view.set_placeholder(
                "当前歌曲暂无歌词",
                "可以右键歌曲手动绑定歌词，或者重新搜索歌词",
            )

    def set_plain_text(self, text: str) -> None:
        self.lyrics_view.set_plain_text(text)

    def update_position(self, position: int, lyrics: list[tuple[int, str]]) -> None:
        self.lyrics_view.update_by_position(position, lyrics)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        if event.key() == Qt.Key.Key_Space:
            self.toggle_auto_hide()
            return

        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.show_controls_temporarily()

    def closeEvent(self, event) -> None:
        self.setWindowOpacity(1.0)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_ui_timer.stop()

        if getattr(self.main_window, "immersive_lyrics_window", None) is self:
            self.main_window.immersive_lyrics_window = None

        try:
            self.main_window.on_immersive_lyrics_closed()
        except Exception as error:
            print("恢复主窗口失败：", error)

        super().closeEvent(event)

class MainWindow(QMainWindow):
    media_worker_destroyed_notice = Signal(str)
    media_thread_finished_notice = Signal(str)
    media_thread_destroyed_notice = Signal(str)

    MEDIA_WORKER_SHUTDOWN_TIMEOUT_MS = 1500

    def create_hushplayer_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        background = QPainterPath()
        background.addRoundedRect(QRectF(6, 6, 52, 52), 14, 14)
        painter.fillPath(background, QColor("#151922"))
        painter.setPen(QPen(QColor(255, 255, 255, 32), 1))
        painter.drawPath(background)

        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPointSize(31)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "H")
        painter.end()

        return QIcon(pixmap)

    def install_window_icon(self) -> None:
        icon = self.create_hushplayer_icon()
        app = QApplication.instance()

        if app is not None:
            app.setWindowIcon(icon)

        self.setWindowIcon(icon)

    @staticmethod
    def measure_startup_step(label: str, callback):
        started_at = time.perf_counter()

        try:
            return callback()
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[startup] {label}：{elapsed_ms:.1f} ms")

    def __init__(self) -> None:
        super().__init__()
        startup_started_at = time.perf_counter()
        self.startup_started_at = startup_started_at
        self.startup_show_reported = False
        self.startup_first_paint_reported = False

        app = QApplication.instance()
        process_started_at = app.property("hushStartupStartedAt") if app is not None else None

        try:
            self.process_started_at = float(process_started_at)
        except (TypeError, ValueError):
            self.process_started_at = startup_started_at

        # 播放状态：只表示 QMediaPlayer 当前已加载、正在播放或暂停的歌曲。
        self.current_song_path: str | None = None
        # 浏览状态：只表示用户最近单击查看的歌曲，不驱动播放栏、封面或歌词。
        self.browsing_song_path: str | None = None
        # 播放上下文：保存开始播放时的来源与混合队列，不跟随之后的 UI 选择或筛选变化。
        self.playback_context: dict | None = None
        self.playback_queue = PlaybackQueue()
        # 队列返回状态：仅在内存中记录进入队列前的播放上下文位置。
        self.queue_return_state: dict | None = None
        self.library_category_filter_type: str | None = None
        self.library_category_filter_value = ""
        self.browsing_song_data: dict | None = None
        self.library_sort_field: str | None = None
        self.library_sort_descending = False
        self.library_duration_display_cache: dict[str, int] = {}
        self.library_duration_refresh_scheduled = False
        self.library_duration_pending_paths: set[str] = set()
        self.library_duration_tasks: dict[str, LibraryDurationTask] = {}
        self.library_duration_thread_pool = QThreadPool(self)
        self.library_duration_thread_pool.setMaxThreadCount(1)

        self.cover_request_id = 0
        self.lyrics_request_id = 0
        self.active_cover_request_id = ""
        self.active_lyrics_request_id = ""
        self.cover_threads: dict[str, QThread] = {}
        self.lyrics_threads: dict[str, QThread] = {}
        self.music_scan_threads: list[QThread] = []
        self.cover_workers: dict[str, CoverSearchWorker] = {}
        self.lyrics_workers: dict[str, LyricsSearchWorker] = {}
        self.retiring_cover_workers: dict[str, CoverSearchWorker] = {}
        self.retiring_lyrics_workers: dict[str, LyricsSearchWorker] = {}
        self.retiring_cover_threads: dict[str, QThread] = {}
        self.retiring_lyrics_threads: dict[str, QThread] = {}
        self.music_scan_workers: list[QObject] = []
        self._media_lifecycle_records: dict[str, dict] = {}
        self._running_cover_request: dict | None = None
        self._running_lyrics_request: dict | None = None
        self._pending_cover_request: dict | None = None
        self._pending_lyrics_request: dict | None = None
        self._media_workers_closing = False
        self._media_shutdown_retry_scheduled = False
        self.media_worker_destroyed_notice.connect(
            self._on_media_worker_destroyed_notice,
            Qt.ConnectionType.QueuedConnection,
        )
        self.media_thread_finished_notice.connect(
            self._on_media_thread_finished_notice,
            Qt.ConnectionType.QueuedConnection,
        )
        self.media_thread_destroyed_notice.connect(
            self._on_media_thread_destroyed_notice,
            Qt.ConnectionType.QueuedConnection,
        )
        self.music_scan_in_progress = False
        self.displayed_lyrics_song_path: str | None = None
        self.immersive_lyrics_window: ImmersiveLyricsWindow | None = None
        self.restore_main_after_immersive = False
        self.main_was_minimized_before_immersive = False
        self.main_was_maximized_before_immersive = False
        self.last_playing_indicator_path = ""
        self.last_playing_indicator_identity = ""
        self.song_identity_to_item: dict[str, QListWidgetItem] = {}
        self.playlist_membership_snapshots: dict[str, dict] = {}
        self.last_song_list_order_key = None

        self.search_debounce_timer = QTimer(self)
        self.search_debounce_timer.setSingleShot(True)
        self.search_debounce_timer.setInterval(220)
        self.search_debounce_timer.timeout.connect(self.apply_search_filter)
        self.local_search_generation = 0
        self.pending_local_search_generation = 0
        self.pending_local_search_keyword = ""
        self.pending_local_search_key = ""
        self.pending_local_search_revision = -1
        self.last_applied_local_search_key: str | None = None
        self.last_applied_local_search_revision = -1

        self.playback_save_timer = QTimer(self)
        self.playback_save_timer.setSingleShot(True)
        self.playback_save_timer.setInterval(800)
        self.playback_save_timer.timeout.connect(self.save_playback_session)

        self.session_save_timer = QTimer(self)
        self.session_save_timer.timeout.connect(self.request_save_playback_session)
        self.session_save_timer.start(5000)
        self.current_duration = 0
        self.current_track_kind = "local"
        self.current_media_item: MediaItem | None = None
        self.current_online_track: dict | None = None
        self.pending_online_track: dict | None = None
        self.pending_online_media_item: MediaItem | None = None
        self.pending_online_playback_request = 0
        self.pending_online_playback_generation = 0
        self.pending_online_playback_identity = ""
        self.pending_online_keep_target_on_failure = False
        self.pending_online_metadata_request = 0
        self.pending_online_metadata_identity = ""
        self.pending_online_ui_snapshot: dict | None = None
        self.presented_online_identity = ""
        self.presented_online_cover_url = ""
        self.pending_online_download_track: dict | None = None
        self.pending_online_download_request = 0
        self.active_online_download_track: dict | None = None
        self.active_online_download_remote_id = ""
        self.current_queue_identity = ""
        self.playback_generation = 0
        self.media_loading_generation = 0
        self.handled_end_generation = -1
        self.last_advance_reason = ""
        self.last_advance_at = 0.0
        self.last_end_advance_at = 0.0
        self.online_loop_retry_identity = ""
        self.online_loop_retry_count = 0
        self.current_plain_lyrics = ""
        self.displayed_lyrics_track_key = ""
        self.current_online_lyrics_state = ""
        self.is_seeking = False
        self.pending_restore_position = 0
        self.pending_lazy_restore_song_data: dict | None = None
        self.restoring_playback_session = False
        self.last_musicbrainz_request_time = 0.0

        self.current_lyrics: list[tuple[int, str]] = []
        self.shortcuts: list[QShortcut] = []

        self.paths = AppPaths.resolve()
        self.paths.initialize_user_storage()
        self.project_root = self.paths.bundled_resource_dir
        data_dir = self.paths.data_dir
        self.library_file = data_dir / "library.json"
        self.settings_file = data_dir / "settings.json"
        self.playlists_file = data_dir / "playlists.json"
        self.remote_tracks_file = data_dir / "remote_tracks.json"
        self.stats_file = data_dir / "stats.json"
        self.cover_cache_dir = self.paths.cache_dir / "covers"
        self.lyrics_cache_dir = self.paths.cache_dir / "lyrics"
        self.lyrics_bindings_file = data_dir / "lyrics_bindings.json"
        self.playback_session_file = data_dir / "playback_session.json"
        self.play_queue_file = data_dir / "play_queue.json"
        self.metadata_cache_file = self.paths.metadata_cache_file
        self.pending_imports_file = data_dir / "pending_imports.json"
        self.ignored_imports_file = data_dir / "ignored_imports.json"
        self.source_registry_manager = self.measure_startup_step(
            "音源注册管理器对象",
            lambda: SourceRegistryManager(
                self.project_root,
                runtime_dir=self.paths.source_runtime_data_dir,
                user_sources_dir=self.paths.user_sources_dir,
                bundled_runtime_dir=self.paths.bundled_source_runtime_dir,
            ),
        )
        self.online_source_client = self.measure_startup_step(
            "在线音源客户端对象（未启动 Node）",
            lambda: OnlineSourceClient(
                self.project_root,
                self,
                runtime_dir=self.paths.bundled_source_runtime_dir,
                registry_path=self.paths.source_registry_file,
                user_sources_dir=self.paths.user_sources_dir,
                bundled_node_executable=self.paths.bundled_node_executable,
                frozen=self.paths.frozen,
            ),
        )
        self.online_download_manager = self.measure_startup_step(
            "下载管理器对象（无网络请求）",
            lambda: OnlineDownloadManager(self),
        )
        self.remote_track_store = RemoteTrackStore(self.remote_tracks_file)
        try:
            self.remote_tracks = self.measure_startup_step(
                "远程歌曲 JSON",
                self.remote_track_store.load_tracks,
            )
            self.remote_tracks_error = ""
        except RemoteTrackStoreError as error:
            self.remote_tracks = {}
            self.remote_tracks_error = str(error)
            print(self.remote_tracks_error)

        settings = self.measure_startup_step("设置 JSON", self.load_settings)
        self.settings = deepcopy(settings)
        self._saved_settings = deepcopy(settings)
        self._settings_dirty = False
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.setInterval(350)
        self.settings_save_timer.timeout.connect(self.flush_settings)
        self.current_volume = int(settings.get("volume", 65))
        self.play_mode = settings.get("play_mode", "list_loop")
        self.unified_search_local_only = bool(
            settings.get("online_search_local_only", False)
        )
        self.initial_library_content_view = str(
            settings.get("library_content_view", "tracks") or "tracks"
        )
        if self.initial_library_content_view not in {"tracks", "artists", "albums"}:
            self.initial_library_content_view = "tracks"
        self.unified_search_results: list[dict] = []
        self.unified_search_results_by_source: dict[str, list[dict]] = {}
        self.unified_search_summary: dict = {}
        self.unified_search_generation = 0
        self.unified_search_keyword = ""
        self._unified_search_source_order: list[str] = []
        self._unified_search_source_sizes: dict[str, int] = {}
        self._source_registry_snapshot: dict[str, dict] | None = None
        self._source_registry_snapshot_manager_id = 0
        self._local_song_match_index: set[tuple[str, str, str]] | None = None
        self._local_song_match_index_revision = -1
        self._local_song_match_index_build_count = 0
        self.unified_search_service = UnifiedSearchService(
            self.online_source_client,
            self,
            debounce_ms=settings.get("online_search_debounce_ms", 500),
            cache_ttl_seconds=180,
        )
        self.online_lyrics_cache = LyricsCache(
            self.lyrics_cache_dir / "online_lyrics.json"
        )
        self.online_lyrics_service = OnlineLyricsService(
            self.online_source_client,
            self.online_lyrics_cache,
            self,
        )
        self.online_artwork_service = OnlineArtworkService(
            self.cover_cache_dir / "online",
            self,
        )
        self.playlists = self.measure_startup_step("歌单与收藏 JSON", self.load_playlists)
        self.song_stats = self.measure_startup_step("播放统计 JSON", self.load_song_stats)
        self.lyrics_bindings = self.measure_startup_step("歌词绑定 JSON", self.load_lyrics_bindings)
        self.playback_session = self.measure_startup_step("上次播放会话 JSON", self.load_playback_session)
        self.play_queue = self.measure_startup_step("播放队列 JSON", self.load_play_queue)
        self.metadata_cache = self.measure_startup_step("元数据缓存 JSON", self.load_metadata_cache)
        self.pending_imports = self.measure_startup_step("待导入列表 JSON", self.load_pending_imports)
        self.ignored_imports = self.measure_startup_step("忽略导入列表 JSON", self.load_ignored_imports)
        self.restored_playback_session = False

        self.last_recorded_position = 0
        self.pending_listen_ms = 0
        self.current_session_listen_ms = 0
        self.play_count_marked = False

        self.current_library_view = "all"
        self.library_data_revision = 0
        self.library_list_dirty = True
        self.last_library_view_key = None
        self.search_entry_library_revision = None
        self.search_entry_library_view_key = None
        self._preserve_page_scroll_once = None
        self.view_buttons = {}
        self.custom_view_buttons = []
        self.media_interactions = MediaInteractionController(self)

        self.http_headers = {
            "User-Agent": "HushPlayer/0.5.4.3 (local music player prototype)",
            "Accept": "application/json, image/*",
        }

        print("项目根目录：", self.project_root)
        print("用户数据目录：", self.paths.application_data_dir)
        print("日志目录：", self.paths.log_dir)
        print("音乐库保存位置：", self.library_file)
        print("设置保存位置：", self.settings_file)
        print("歌单保存位置：", self.playlists_file)
        print("播放统计保存位置：", self.stats_file)
        print("封面缓存位置：", self.cover_cache_dir)
        print("歌词缓存位置：", self.lyrics_cache_dir)
        print("歌词绑定保存位置：", self.lyrics_bindings_file)

        audio_started_at = time.perf_counter()
        default_device = QMediaDevices.defaultAudioOutput()
        print("默认音频输出设备：", default_device.description())

        self.audio_output = QAudioOutput(default_device)
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.current_volume / 100)
        print(f"[perf] 音频初始化：{(time.perf_counter() - audio_started_at) * 1000:.1f} ms")

        self.setWindowTitle("HushPlayer")
        self.install_window_icon()
        self.resize(1400, 860)
        self.setMinimumSize(900, 640)
        self.setAcceptDrops(True)
        self._responsive_mode = ""
        self._screen_signal_connected = False
        self._responsive_screen = None

        layout_started_at = time.perf_counter()
        root = QWidget()
        root.setObjectName("root")
        root.setAcceptDrops(True)

        root_layout = QVBoxLayout(root)
        self.root_layout = root_layout
        root_layout.setContentsMargins(18, 18, 18, 18)

        shell = QFrame()
        shell.setObjectName("shell")
        shell.setAcceptDrops(True)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.setObjectName("bodySplitter")
        body_splitter.setChildrenCollapsible(False)
        body_splitter.setHandleWidth(2)
        self.body_splitter = body_splitter

        sidebar = self.measure_startup_step("侧边栏 UI", self._create_sidebar)
        self.sidebar_panel = sidebar
        library_panel = self.measure_startup_step("音乐库页面 UI", self._create_library_panel)
        self.library_panel = library_panel
        full_lyrics_page = self.measure_startup_step("歌词页面 UI", self._create_full_lyrics_page)
        self.full_lyrics_page = full_lyrics_page
        pending_imports_page = self.measure_startup_step("待导入页面 UI", self._create_pending_imports_page)
        self.pending_imports_page = pending_imports_page
        search_page = self.measure_startup_step(
            "独立搜索页面 UI（无网络请求）",
            lambda: SearchPage(self.unified_search_local_only, self),
        )
        self.search_page = search_page
        # Keep this alias for existing status helpers while the old standalone
        # online page remains available as a compatibility module.
        self.online_search_page = search_page
        self.unified_search_panel = search_page.online_results
        search_page.backRequested.connect(self.return_to_library_view)
        search_page.localOnlyChanged.connect(self.on_unified_local_only_toggled)
        search_page.localBrowseRequested.connect(self.browse_media_item)
        search_page.localPlayRequested.connect(self.play_media_item)
        search_page.localQueueNextRequested.connect(self.queue_media_item_next)
        search_page.localLikeRequested.connect(self.media_interactions.like_local)
        search_page.localUnlikeRequested.connect(self.media_interactions.unlike_local)
        search_page.localAddToPlaylistRequested.connect(
            self.media_interactions.add_local_to_playlist
        )
        search_page.localRemoveFromCurrentPlaylistRequested.connect(
            self.media_interactions.remove_local_from_current_playlist
        )
        search_page.localOpenFolderRequested.connect(self.media_interactions.open_local_folder)
        search_page.localRemoveRequested.connect(self.media_interactions.remove_local)
        search_page.localInfoRequested.connect(self.media_interactions.show_info)
        search_page.set_collection_providers(
            self.media_interactions.get_local_state,
            self.get_online_playlist_choices,
        )
        search_page.set_playing_key_provider(self.current_media_key)
        custom_source_manager_page = self.measure_startup_step(
            "自定义来源管理页面 UI（无网络请求）",
            lambda: CustomSourceManagerPage(
                self.source_registry_manager,
                self.online_source_client,
                self,
            ),
        )
        self.custom_source_manager_page = custom_source_manager_page
        custom_source_manager_page.sourcesChanged.connect(self.on_custom_sources_changed)
        custom_source_manager_page.backRequested.connect(self.return_to_library_view)
        self.unified_search_service.statusChanged.connect(
            search_page.set_online_status
        )
        self.unified_search_service.resultsChanged.connect(
            self.on_unified_search_results_changed
        )
        self.unified_search_service.sourceResultsChanged.connect(
            self.on_unified_search_source_results_changed
        )
        self.unified_search_panel.playRequested.connect(self.play_unified_search_track)
        self.unified_search_panel.queueNextRequested.connect(self.queue_media_item_next)
        self.unified_search_panel.browseRequested.connect(self.browse_media_item)
        self.unified_search_panel.downloadRequested.connect(self.request_online_download)
        self.unified_search_panel.likeRequested.connect(self.like_online_track)
        self.unified_search_panel.unlikeRequested.connect(self.unlike_online_track)
        self.unified_search_panel.addToPlaylistRequested.connect(
            self.add_online_track_to_playlist
        )
        self.unified_search_panel.removeFromCurrentPlaylistRequested.connect(
            self.remove_unified_track_from_current_playlist
        )
        self.unified_search_panel.infoRequested.connect(self.show_online_track_info)
        self.unified_search_panel.set_collection_providers(
            self.get_online_track_collection_state,
            self.get_online_playlist_choices,
        )
        self.online_lyrics_service.statusChanged.connect(
            self.on_online_lyrics_status_changed
        )
        self.online_lyrics_service.lyricsReady.connect(self.on_online_lyrics_ready)
        self.online_artwork_service.imageReady.connect(self.on_online_artwork_ready)
        self.online_artwork_service.failed.connect(self.on_online_artwork_failed)
        self.online_source_client.metadataFinished.connect(self.on_online_metadata_finished)
        self.online_source_client.playbackResolved.connect(self.on_online_playback_resolved)
        self.online_source_client.downloadResolved.connect(self.on_online_download_resolved)
        self.online_source_client.requestFailed.connect(self.on_online_source_request_failed)
        self.online_download_manager.started.connect(
            lambda _path: self.set_online_status_message("正在下载…")
        )
        self.online_download_manager.progress.connect(self.on_online_download_progress)
        self.online_download_manager.finished.connect(self.on_online_download_finished)
        self.online_download_manager.failed.connect(self.on_online_download_failed)
        now_playing_panel = self.measure_startup_step("正在播放侧栏 UI", self._create_now_playing_panel)
        self.now_playing_panel = now_playing_panel

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        self.content_stack.addWidget(library_panel)
        self.content_stack.addWidget(full_lyrics_page)
        self.content_stack.addWidget(pending_imports_page)
        self.content_stack.addWidget(search_page)
        self.content_stack.addWidget(custom_source_manager_page)
        self.content_stack.currentChanged.connect(self.on_content_page_changed)

        self.content_stack.setMinimumWidth(0)
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        body_splitter.addWidget(sidebar)
        body_splitter.addWidget(self.content_stack)
        body_splitter.addWidget(now_playing_panel)
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setStretchFactor(2, 0)

        player_bar = self.measure_startup_step("底部播放栏 UI", self._create_player_bar)
        self.player_bar = player_bar

        shell_layout.addWidget(body_splitter, 1)
        shell_layout.addWidget(player_bar)

        root_layout.addWidget(shell)
        self.setCentralWidget(root)
        self._update_responsive_layout(force=True)
        print(f"[startup] 主界面布局装配：{(time.perf_counter() - layout_started_at) * 1000:.1f} ms")

        self.measure_startup_step("播放器信号连接", self._connect_player_signals)
        self.measure_startup_step("快捷键创建", self._create_shortcuts)
        style_started_at = time.perf_counter()
        self.setStyleSheet(
            self._style_sheet()
            + self.build_visual_polish_qss()
            + self.build_player_product_qss()
        )
        print(f"[perf] 样式初始化：{(time.perf_counter() - style_started_at) * 1000:.1f} ms")
        library_started_at = time.perf_counter()
        valid_library_count, song_list_is_local_only = self.load_music_library(
            refresh_view=False
        )
        self.sync_remote_song_items(
            refresh_view=False,
            song_list_is_local_only=song_list_is_local_only,
        )
        self.finish_music_library_load(valid_library_count)
        self.library_page.show_mode(self.initial_library_content_view)
        print(f"[perf] 音乐库初始化：{(time.perf_counter() - library_started_at) * 1000:.1f} ms")
        initial_ui_started_at = time.perf_counter()
        self.update_play_mode_button()
        self.update_like_button()
        self.update_side_info_panel()
        self.update_view_buttons()
        print(f"[startup] 初始状态 UI 更新：{(time.perf_counter() - initial_ui_started_at) * 1000:.1f} ms")

        self.schedule_startup_task(350, "恢复上次播放信息", self.restore_playback_session)
        self.schedule_startup_task(0, "设置按钮挂钩", self.install_settings_button_hook)
        self.schedule_startup_task(0, "播放列表按钮挂钩", self.install_playlist_button_hook)
        self.schedule_startup_task(0, "桌面歌词功能初始化", self.install_floating_lyrics_feature)
        self.schedule_startup_task(0, "桌面歌词按钮初始化", self.install_floating_lyrics_button)
        self.schedule_startup_task(0, "Windows 深色标题栏", self.apply_windows_dark_title_bar)
        if self.playlists_migration_pending:
            self.schedule_startup_task(
                0,
                "旧歌单加入时间迁移持久化",
                self.persist_pending_playlist_migration,
            )
        self.schedule_startup_task(120, "桌面歌词自动打开检查", self.auto_open_floating_lyrics_if_enabled)
        self.schedule_startup_task(1800, "启动文件夹扫描派发", self.auto_scan_music_folders_on_startup)
        print(f"[perf] 主窗口启动调度：{(time.perf_counter() - startup_started_at) * 1000:.1f} ms")

    def schedule_startup_task(self, delay_ms: int, label: str, callback) -> None:
        QTimer.singleShot(
            max(0, int(delay_ms)),
            lambda: self.run_startup_task(label, callback),
        )

    @staticmethod
    def run_startup_task(label: str, callback) -> None:
        started_at = time.perf_counter()

        try:
            callback()
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[startup] 延迟任务/{label}：{elapsed_ms:.1f} ms")

    def apply_windows_dark_title_bar(self, widget=None, enabled: bool = True) -> None:
        if sys.platform != "win32":
            return

        target = widget or self

        try:
            import ctypes

            hwnd = int(target.winId())

            if not hwnd:
                return

            value = ctypes.c_int(1 if enabled else 0)

            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_int(attribute),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )

                if result == 0:
                    break

            if not enabled:
                return

            def colorref(red: int, green: int, blue: int):
                return ctypes.c_uint((blue << 16) | (green << 8) | red)

            color_attributes = {
                35: colorref(0x10, 0x13, 0x1A),
                34: colorref(0x20, 0x26, 0x36),
                36: colorref(0xF3, 0xF4, 0xF6),
            }

            for attribute, color_value in color_attributes.items():
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_int(attribute),
                    ctypes.byref(color_value),
                    ctypes.sizeof(color_value),
                )

        except Exception:
            pass

    def prepare_dark_dialog(self, dialog: QDialog, extra_qss: str = "") -> None:
        apply_dark_dialog_style(dialog, extra_qss)
        self.apply_windows_dark_title_bar(dialog)
        QTimer.singleShot(0, lambda dialog=dialog: self.apply_windows_dark_title_bar(dialog))

    def get_dark_text_input(
        self,
        title: str,
        label: str,
        text: str = "",
        placeholder: str = "",
    ) -> tuple[str, bool]:
        dialog = QInputDialog(self)
        dialog.setObjectName("darkInputDialog")
        dialog.setWindowTitle(title)
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setLabelText(label)
        dialog.setTextValue(text)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")

        line_edit = dialog.findChild(QLineEdit)

        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)

        self.prepare_dark_dialog(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.textValue(), accepted

    def get_dark_item_input(
        self,
        title: str,
        label: str,
        items: list[str],
    ) -> tuple[str, bool]:
        dialog = QInputDialog(self)
        dialog.setObjectName("darkInputDialog")
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setComboBoxEditable(False)
        dialog.setComboBoxItems(items)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        self.prepare_dark_dialog(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.textValue(), accepted

    def ask_dark_confirmation(
        self,
        title: str,
        text: str,
        danger_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox.StandardButton:
        message_box = QMessageBox(self)
        message_box.setObjectName("darkMessageBox")
        message_box.setWindowTitle(title)
        message_box.setIcon(QMessageBox.Icon.Question)
        message_box.setText(text)
        message_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        self.prepare_dark_dialog(message_box)

        if danger_button is not None:
            button = message_box.button(danger_button)

            if button is not None:
                button.setObjectName("dangerDialogButton")
                button.style().unpolish(button)
                button.style().polish(button)

        return QMessageBox.StandardButton(message_box.exec())

    def showEvent(self, event) -> None:
        started_at = time.perf_counter()
        super().showEvent(event)
        self.apply_windows_dark_title_bar()
        self._connect_responsive_screen_signals()
        QTimer.singleShot(0, lambda: self._update_responsive_layout(force=True))

        if not self.startup_show_reported:
            self.startup_show_reported = True
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            process_elapsed_ms = (time.perf_counter() - self.process_started_at) * 1000
            print(f"[startup] MainWindow.showEvent：{elapsed_ms:.1f} ms")
            print(f"[startup] 进程启动到 showEvent：{process_elapsed_ms:.1f} ms")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "body_splitter"):
            self._update_responsive_layout()

    @staticmethod
    def responsive_mode_for_width(width: int) -> str:
        logical_width = max(0, int(width or 0))
        if logical_width >= 1450:
            return "full"
        if logical_width >= 1100:
            return "compact"
        return "narrow"

    def _connect_responsive_screen_signals(self) -> None:
        handle = self.windowHandle()
        if handle is None:
            return
        if not self._screen_signal_connected:
            handle.screenChanged.connect(self._on_responsive_screen_changed)
            self._screen_signal_connected = True
        self._on_responsive_screen_changed(handle.screen())

    def _on_responsive_screen_changed(self, screen) -> None:
        previous = getattr(self, "_responsive_screen", None)
        if previous is screen:
            self._update_responsive_layout(force=True)
            return
        if previous is not None:
            try:
                previous.logicalDotsPerInchChanged.disconnect(
                    self._on_responsive_dpi_changed
                )
            except (RuntimeError, TypeError):
                pass
        self._responsive_screen = screen
        if screen is not None:
            try:
                screen.logicalDotsPerInchChanged.connect(
                    self._on_responsive_dpi_changed
                )
            except (RuntimeError, TypeError):
                pass
        self._update_responsive_layout(force=True)

    def _on_responsive_dpi_changed(self, _dpi: float) -> None:
        self._update_responsive_layout(force=True)

    def _update_responsive_layout(self, force: bool = False) -> None:
        splitter = getattr(self, "body_splitter", None)
        sidebar = getattr(self, "sidebar_panel", None)
        content = getattr(self, "content_stack", None)
        now_panel = getattr(self, "now_playing_panel", None)
        if splitter is None or sidebar is None or content is None or now_panel is None:
            return

        mode = self.responsive_mode_for_width(self.width())
        if mode == self._responsive_mode and not force:
            return
        self._responsive_mode = mode

        if mode == "full":
            root_margin = 18
            sidebar_limits = (180, 230, 220)
            now_limits = (280, 340, 330)
            content_minimum = 600
            cover_size = 236
            player_margins = (24, 16, 24, 16)
            player_spacing = 20
            player_limits = ((200, 280), 340, (250, 320))
        elif mode == "compact":
            root_margin = 12
            sidebar_limits = (170, 205, 196)
            now_limits = (220, 270, 250)
            content_minimum = 480
            cover_size = 184
            player_margins = (18, 14, 18, 14)
            player_spacing = 14
            player_limits = ((170, 230), 300, (210, 260))
        else:
            root_margin = 8
            sidebar_limits = (160, 185, 178)
            now_limits = (0, 0, 0)
            content_minimum = 520
            cover_size = 0
            player_margins = (12, 12, 12, 12)
            player_spacing = 10
            player_limits = ((130, 190), 260, (190, 220))

        self.root_layout.setContentsMargins(
            root_margin, root_margin, root_margin, root_margin
        )
        sidebar.setMinimumWidth(sidebar_limits[0])
        sidebar.setMaximumWidth(sidebar_limits[1])
        content.setMinimumWidth(content_minimum)
        self.sidebar_subtitle.setVisible(mode != "narrow")
        self.sidebar_playlist_hint.setVisible(mode != "narrow")

        show_now_panel = mode != "narrow"
        now_panel.setVisible(show_now_panel)
        if show_now_panel:
            now_panel.setMinimumWidth(now_limits[0])
            now_panel.setMaximumWidth(now_limits[1])
            self.cover_label.setFixedSize(cover_size, cover_size)

        available = max(0, splitter.width() or self.width() - root_margin * 2)
        right_width = now_limits[2] if show_now_panel else 0
        center_width = max(
            360,
            available - sidebar_limits[2] - right_width - splitter.handleWidth() * 2,
        )
        splitter.setSizes([sidebar_limits[2], center_width, right_width])

        if hasattr(self, "library_page"):
            self.library_page.set_responsive_mode(mode)
        if hasattr(self, "search_page"):
            self.search_page.set_responsive_mode(mode)

        left_limits, center_minimum, right_limits = player_limits
        self.player_bar_layout.setContentsMargins(*player_margins)
        self.player_bar_layout.setSpacing(player_spacing)
        self.player_left_box.setMinimumWidth(left_limits[0])
        self.player_left_box.setMaximumWidth(left_limits[1])
        self.player_center_box.setMinimumWidth(center_minimum)
        self.player_right_box.setMinimumWidth(right_limits[0])
        self.player_right_box.setMaximumWidth(right_limits[1])
        self.floating_lyrics_button.setVisible(mode == "full")
        self.player_more_button.setVisible(mode != "full")
        current = getattr(self, "current_media_item", None)
        self.bottom_source_badge.setVisible(
            mode == "full"
            and isinstance(current, MediaItem)
            and current.media_type == "online"
            and bool(self.bottom_source_badge.text())
        )

        self.updateGeometry()
        content.updateGeometry()

    def paintEvent(self, event) -> None:
        started_at = time.perf_counter()
        super().paintEvent(event)

        if not self.startup_first_paint_reported:
            self.startup_first_paint_reported = True
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            process_elapsed_ms = (time.perf_counter() - self.process_started_at) * 1000
            print(f"[startup] MainWindow 首次 paintEvent：{elapsed_ms:.1f} ms")
            print(f"[startup] 进程启动到首次 paintEvent：{process_elapsed_ms:.1f} ms")
            QTimer.singleShot(0, self.report_startup_frame_ready)

    def report_startup_frame_ready(self) -> None:
        elapsed_ms = (time.perf_counter() - self.process_started_at) * 1000
        print(f"[startup] 主窗口首帧事件完成：{elapsed_ms:.1f} ms")

    def _connect_player_signals(self) -> None:
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.errorOccurred.connect(self.on_player_error)

    def _create_shortcuts(self) -> None:
        shortcut_configs = [
            ("Ctrl+O", self.import_music_files),
            ("Ctrl+Shift+O", self.import_music_folder),
            ("Ctrl+F", self.focus_search),
            ("Ctrl+L", self.clear_search),
            ("Ctrl+Space", self.toggle_play),
            ("Ctrl+Left", self.play_previous_song),
            ("Ctrl+Right", self.play_next_song),
            ("Ctrl+M", self.clean_missing_songs),
        ]

        for key_sequence, callback in shortcut_configs:
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

        delete_shortcut = QShortcut(QKeySequence("Delete"), self.song_list)
        delete_shortcut.activated.connect(self.remove_selected_song)
        self.shortcuts.append(delete_shortcut)

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _create_view_button(self, text: str, view_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("viewButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("active", view_name == self.current_library_view)
        button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))

        self.view_buttons[view_name] = button
        return button

    def set_library_view(self, view_name: str) -> None:
        if view_name not in {"all", "liked", "recent_played", "frequent", "recent_added"}:
            view_name = "all"

        self.current_library_view = view_name
        self.sort_song_list_for_current_view()
        self.filter_song_list(self.search_input.text())
        self.update_view_buttons()

        if self.current_library_view == "liked" or self.current_library_view.startswith("playlist:"):
            self.set_sidebar_active("playlists")
        else:
            self.set_sidebar_active("library")

        view_titles = {
            "all": "全部歌曲",
            "liked": "我喜欢",
            "recent_played": "最近播放",
            "frequent": "常听歌曲",
            "recent_added": "最近添加",
        }

        print("当前音乐库视图：", view_titles.get(view_name, "全部歌曲"))

    def update_view_buttons(self) -> None:
        if not hasattr(self, "view_buttons"):
            return

        for view_name, button in self.view_buttons.items():
            button.setProperty("active", view_name == self.current_library_view)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def song_matches_current_view(self, song_data: dict) -> bool:
        if not isinstance(song_data, dict):
            return True

        if song_data.get("demo"):
            return self.current_library_view == "all"

        if song_data.get("recordKind") == "remote":
            stable_id = str(song_data.get("remoteStableId") or "")
            if self.current_library_view == "liked":
                return stable_id in self.get_playlist_remote_ids("liked")
            if self.current_library_view.startswith("playlist:"):
                playlist_id = self.current_library_view.split("playlist:", 1)[1]
                return stable_id in self.get_playlist_remote_ids(playlist_id)
            return False

        path = song_data.get("path", "")
        normalized_path = self.normalize_song_path(path)

        if self.current_library_view == "all":
            return True

        if self.current_library_view == "liked":
            return self.is_song_liked(normalized_path)

        if self.current_library_view == "recent_played":
            stats = self.song_stats.get(normalized_path, {})
            return int(stats.get("last_played", 0)) > 0

        if self.current_library_view == "frequent":
            stats = self.song_stats.get(normalized_path, {})
            play_count = int(stats.get("play_count", 0))
            total_listen_time = int(stats.get("total_listen_time", 0))
            return play_count > 0 or total_listen_time > 0

        if self.current_library_view == "recent_added":
            return bool(normalized_path)

        return True

    def collect_song_data_from_list(self) -> list[dict]:
        songs = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                songs.append(dict(song_data))

        return songs

    def create_song_list_item(self, song_data: dict) -> QListWidgetItem:
        item = QListWidgetItem()
        self.refresh_song_item_display(item, song_data)
        return item

    def rebuild_song_list_from_data(self, songs: list[dict]) -> None:
        started_at = time.perf_counter()
        current_path = self.normalize_song_path(self.current_song_path)
        selected_row = -1
        previous_signal_state = self.song_list.blockSignals(True)
        self.song_list.setUpdatesEnabled(False)

        try:
            self.song_list.clear()

            for row, song_data in enumerate(songs):
                item = self.create_song_list_item(song_data)
                self.song_list.addItem(item)

                song_path = self.normalize_song_path(song_data.get("path", ""))

                if current_path and song_path == current_path:
                    selected_row = row

            self.filter_song_list(self.search_input.text())

            if selected_row >= 0:
                self.song_list.setCurrentRow(selected_row)
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] rebuild_song_list_from_data: {elapsed_ms:.1f} ms, songs={self.song_list.count()}")
    def sort_song_list_for_current_view(self) -> None:
        songs = self.collect_song_data_from_list()

        if not songs:
            return

        def normalized_path(song_data: dict) -> str:
            return self.normalize_song_path(song_data.get("path", ""))

        def stats_for(song_data: dict) -> dict:
            return self.song_stats.get(
                normalized_path(song_data),
                {
                    "play_count": 0,
                    "total_listen_time": 0,
                    "last_played": 0,
                },
            )

        if self.current_library_view == "recent_played":
            songs.sort(
                key=lambda song: int(stats_for(song).get("last_played", 0)),
                reverse=True,
            )

        elif self.current_library_view == "frequent":
            songs.sort(
                key=lambda song: (
                    int(stats_for(song).get("play_count", 0)),
                    int(stats_for(song).get("total_listen_time", 0)),
                    int(stats_for(song).get("last_played", 0)),
                ),
                reverse=True,
            )

        elif self.current_library_view == "recent_added":
            songs.sort(
                key=lambda song: int(song.get("added_at", 0) or 0),
                reverse=True,
            )

        else:
            songs.sort(
                key=lambda song: int(song.get("added_at", 0) or 0),
            )

        self.rebuild_song_list_from_data(songs)

    def _create_view_button(self, text: str, view_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("viewButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("active", view_name == self.current_library_view)
        button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))

        self.view_buttons[view_name] = button
        return button

    def get_playlist_name(self, playlist_id: str) -> str:
        playlist = self.playlists.get(playlist_id, {})

        if not isinstance(playlist, dict):
            return "未命名歌单"

        name = str(playlist.get("name", "")).strip()
        return name or "未命名歌单"

    def get_playlist_song_paths(self, playlist_id: str) -> list[str]:
        if playlist_id not in self.playlists or not isinstance(self.playlists.get(playlist_id), dict):
            self.playlists[playlist_id] = {
                "name": "未命名歌单",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": False,
            }
        playlist = self.playlists[playlist_id]
        return list(self.get_playlist_membership_snapshot(playlist_id)["local_ids"])

    def get_playlist_remote_ids(self, playlist_id: str) -> list[str]:
        if playlist_id not in self.playlists or not isinstance(self.playlists.get(playlist_id), dict):
            self.playlists[playlist_id] = {
                "name": "未命名歌单",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": False,
            }
        playlist = self.playlists[playlist_id]
        return list(self.get_playlist_membership_snapshot(playlist_id)["remote_ids"])

    def invalidate_playlist_membership_snapshot(self, playlist_id: str = "") -> None:
        if playlist_id:
            self.playlist_membership_snapshots.pop(playlist_id, None)
        else:
            self.playlist_membership_snapshots.clear()

    def get_playlist_membership_snapshot(self, playlist_id: str) -> dict:
        playlist = self.playlists.get(playlist_id)
        cached = self.playlist_membership_snapshots.get(playlist_id)
        if cached is not None and cached.get("playlist_object_id") == id(playlist):
            return cached
        if not isinstance(playlist, dict):
            return {
                "local_ids": (),
                "remote_ids": (),
                "member_index": {},
                "signature": (),
            }
        if (
            playlist.get("membershipVersion") != PlaylistMembership.VERSION
            or not isinstance(playlist.get("members"), list)
        ):
            PlaylistMembership.normalize_playlist(
                playlist,
                self.normalize_song_path,
            )
        members = [
            member
            for member in playlist.get("members", [])
            if isinstance(member, dict)
        ]
        member_index = {
            (
                str(member.get("kind") or ""),
                str(member.get("id") or ""),
            ): int(member.get("added_at") or 0)
            for member in members
        }
        snapshot = {
            "playlist_object_id": id(playlist),
            "local_ids": tuple(
                identifier
                for (kind, identifier) in member_index
                if kind == PlaylistMembership.LOCAL
            ),
            "remote_ids": tuple(
                identifier
                for (kind, identifier) in member_index
                if kind == PlaylistMembership.REMOTE
            ),
            "member_index": member_index,
            "signature": tuple(
                (kind, identifier, added_at)
                for (kind, identifier), added_at in member_index.items()
            ),
        }
        self.playlist_membership_snapshots[playlist_id] = snapshot
        return snapshot

    def set_playlist_member(
        self,
        playlist_id: str,
        kind: str,
        identifier: str,
        present: bool,
    ) -> bool:
        playlist = self.playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            return False
        previous = deepcopy(playlist)
        if present:
            changed = PlaylistMembership.add_member(
                playlist,
                kind,
                identifier,
                self.normalize_song_path,
            )
        else:
            changed = PlaylistMembership.remove_member(
                playlist,
                kind,
                identifier,
                self.normalize_song_path,
            )
        if not changed:
            return False
        self.invalidate_playlist_membership_snapshot(playlist_id)
        if not self.save_playlists():
            self.playlists[playlist_id] = previous
            self.invalidate_playlist_membership_snapshot(playlist_id)
            return False
        self.mark_library_list_dirty()
        return True

    def add_local_path_to_playlist(self, path: str, playlist_id: str) -> bool:
        return self.set_playlist_member(
            playlist_id,
            PlaylistMembership.LOCAL,
            self.normalize_song_path(path),
            True,
        )

    def add_local_paths_to_playlist(
        self,
        paths: list[str],
        playlist_id: str,
    ) -> int:
        playlist = self.playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            return 0
        previous = deepcopy(playlist)
        added_count = 0
        for path in paths:
            if PlaylistMembership.add_member(
                playlist,
                PlaylistMembership.LOCAL,
                self.normalize_song_path(path),
                self.normalize_song_path,
            ):
                added_count += 1
        if added_count <= 0:
            return 0
        self.invalidate_playlist_membership_snapshot(playlist_id)
        if not self.save_playlists():
            self.playlists[playlist_id] = previous
            self.invalidate_playlist_membership_snapshot(playlist_id)
            return 0
        self.mark_library_list_dirty()
        return added_count

    def remove_local_path_from_playlist(self, path: str, playlist_id: str) -> bool:
        return self.set_playlist_member(
            playlist_id,
            PlaylistMembership.LOCAL,
            self.normalize_song_path(path),
            False,
        )

    def add_remote_id_to_playlist(self, stable_id: str, playlist_id: str) -> bool:
        return self.set_playlist_member(
            playlist_id,
            PlaylistMembership.REMOTE,
            stable_id,
            True,
        )

    def remove_remote_id_from_playlist(self, stable_id: str, playlist_id: str) -> bool:
        return self.set_playlist_member(
            playlist_id,
            PlaylistMembership.REMOTE,
            stable_id,
            False,
        )

    def get_playlist_member_added_at(
        self,
        playlist_id: str,
        kind: str,
        identifier: str,
    ) -> int:
        playlist = self.playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            return 0
        normalized_identifier = (
            self.normalize_song_path(identifier)
            if kind == PlaylistMembership.LOCAL
            else str(identifier or "").strip()
        )
        return int(
            self.get_playlist_membership_snapshot(playlist_id)["member_index"].get(
                (kind, normalized_identifier),
                0,
            )
        )

    def get_playlist_membership_signature(
        self,
        playlist_id: str,
    ) -> tuple[tuple[str, str, int], ...]:
        playlist = self.playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            return ()
        return self.get_playlist_membership_snapshot(playlist_id)["signature"]

    def get_playlist_member_index(
        self,
        playlist_id: str,
    ) -> dict[tuple[str, str], int]:
        playlist = self.playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            return {}
        return self.get_playlist_membership_snapshot(playlist_id)[
            "member_index"
        ]

    def playlist_id_for_current_view(self) -> str:
        if self.current_library_view == "liked":
            return "liked"
        if self.current_library_view.startswith("playlist:"):
            return self.current_library_view.split("playlist:", 1)[1]
        return ""

    def playlist_member_added_at_for_song(
        self,
        playlist_id: str,
        song_data: dict,
        member_index: dict[tuple[str, str], int] | None = None,
    ) -> int:
        index = member_index
        if index is None:
            index = self.get_playlist_member_index(playlist_id)
        if song_data.get("recordKind") == "remote":
            return int(
                index.get(
                    (
                        PlaylistMembership.REMOTE,
                        str(song_data.get("remoteStableId") or ""),
                    ),
                    0,
                )
            )
        return int(
            index.get(
                (
                    PlaylistMembership.LOCAL,
                    self.normalize_song_path(song_data.get("path", "")),
                ),
                0,
            )
        )

    def get_online_playlist_choices(self) -> list[tuple[str, str]]:
        return [
            (playlist_id, self.get_playlist_name(playlist_id))
            for playlist_id in self.get_custom_playlist_ids()
        ]

    def get_registered_source_safely(self, source_id: str) -> dict | None:
        source_id = str(source_id or "").strip()
        if not source_id:
            return None
        source = self.get_registered_source_snapshot().get(source_id)
        return dict(source) if isinstance(source, dict) else None

    def get_registered_source_snapshot(self) -> dict[str, dict]:
        manager_id = id(self.source_registry_manager)
        if (
            self._source_registry_snapshot is not None
            and self._source_registry_snapshot_manager_id == manager_id
        ):
            return self._source_registry_snapshot
        try:
            sources = self.source_registry_manager.list_sources()
        except Exception as error:
            print(f"读取在线来源失败：{error}")
            sources = []
        self._source_registry_snapshot = {
            str(source.get("id") or "").strip(): dict(source)
            for source in sources
            if isinstance(source, dict) and str(source.get("id") or "").strip()
        }
        self._source_registry_snapshot_manager_id = manager_id
        return self._source_registry_snapshot

    def invalidate_registered_source_snapshot(self) -> None:
        self._source_registry_snapshot = None
        self._source_registry_snapshot_manager_id = 0

    def get_remote_track_source_url(self, track: dict) -> str:
        source_url = str(track.get("sourceUrl") or track.get("source_url") or "").strip()
        if source_url:
            return source_url
        source = self.get_registered_source_safely(str(track.get("sourceId") or ""))
        return str((source or {}).get("sourceUrl") or "").strip()

    def persist_remote_track(self, track: dict) -> tuple[str, dict]:
        if self.remote_tracks_error:
            raise RemoteTrackStoreError(self.remote_tracks_error)
        track = MediaItem.from_mapping(track).to_legacy_online()
        stable_id = RemoteTrackStore.stable_id_for_track(track)
        existing = self.remote_tracks.get(stable_id)
        stable_id, record = RemoteTrackStore.build_record(
            track,
            self.get_remote_track_source_url(track),
            existing,
        )
        if isinstance(existing, dict) and existing == record:
            return stable_id, existing
        updated = dict(self.remote_tracks)
        updated[stable_id] = record
        self.remote_track_store.save_tracks(updated)
        self.remote_tracks = updated
        self.invalidate_local_song_match_index()
        return stable_id, record

    def get_online_track_collection_state(self, track: dict) -> dict:
        track = MediaItem.from_mapping(track).to_legacy_online()
        stable_id = RemoteTrackStore.stable_id_for_track(track)
        current_playlist_id = ""
        if self.current_library_view == "liked":
            current_playlist_id = "liked"
        elif self.current_library_view.startswith("playlist:"):
            current_playlist_id = self.current_library_view.split("playlist:", 1)[1]
        return {
            "stableId": stable_id,
            "liked": stable_id in self.get_playlist_remote_ids("liked"),
            "inCurrentPlaylist": bool(
                current_playlist_id
                and stable_id in self.get_playlist_remote_ids(current_playlist_id)
            ),
        }

    def like_online_track(self, track: dict) -> None:
        self.add_online_track_to_playlist(track, "liked")

    def unlike_online_track(self, track: dict) -> None:
        track = MediaItem.from_mapping(track).to_legacy_online()
        stable_id = RemoteTrackStore.stable_id_for_track(track)
        if stable_id not in self.get_playlist_remote_ids("liked"):
            self.set_online_status_message("该在线歌曲尚未收藏。")
            return
        if not self.remove_remote_id_from_playlist(stable_id, "liked"):
            return
        self.refresh_playlist_membership_views()
        self.set_online_status_message("已取消收藏该在线歌曲。")

    def add_online_track_to_playlist(self, track: dict, playlist_id: str) -> None:
        track = MediaItem.from_mapping(track).to_legacy_online()
        if playlist_id not in self.playlists or not isinstance(self.playlists.get(playlist_id), dict):
            self.set_online_status_message("目标歌单不存在。")
            return
        stable_id = RemoteTrackStore.stable_id_for_track(track)
        if stable_id in self.get_playlist_remote_ids(playlist_id):
            self.set_online_status_message(
                f"该歌曲已经在“{self.get_playlist_name(playlist_id)}”中。"
            )
            return
        try:
            stable_id, _record = self.persist_remote_track(track)
        except RemoteTrackStoreError as error:
            QMessageBox.warning(self, "保存在线歌曲失败", str(error))
            return
        if not self.add_remote_id_to_playlist(stable_id, playlist_id):
            return
        self.refresh_remote_song_item(stable_id)
        self.refresh_playlist_membership_views()
        self.set_online_status_message(
            f"已加入“{self.get_playlist_name(playlist_id)}”。"
        )

    def show_online_track_info(self, track: dict) -> None:
        self.show_media_item_info(MediaItem.from_mapping(track).to_dict())

    def is_remote_source_available(self, record: dict) -> bool:
        source = self.get_registered_source_safely(str(record.get("source_id") or ""))
        return bool(source and source.get("enabled") and source.get("sourceUrl"))

    def collect_remote_song_items(self) -> dict[str, QListWidgetItem]:
        existing_items: dict[str, QListWidgetItem] = {}
        for row in range(self.song_list.count()):
            item = self.song_list.item(row)
            data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(data, dict) and data.get("recordKind") == "remote":
                stable_id = str(data.get("remoteStableId") or "")
                if stable_id and item is not None:
                    existing_items[stable_id] = item
        return existing_items

    def sync_remote_song_items(
        self,
        *,
        refresh_view: bool = True,
        song_list_is_local_only: bool = False,
    ) -> None:
        if not hasattr(self, "song_list"):
            return
        remote_store_ready = not getattr(self, "remote_tracks_error", "")
        if song_list_is_local_only and remote_store_ready:
            if not self.remote_tracks:
                return
            existing_items: dict[str, QListWidgetItem] = {}
        else:
            existing_items = self.collect_remote_song_items()

        previous_signal_state = self.song_list.blockSignals(True)
        self.song_list.setUpdatesEnabled(False)
        structure_changed = False
        data_changed = False
        try:
            pending_track = getattr(self, "pending_online_track", None)
            pending_id = (
                RemoteTrackStore.stable_id_for_track(pending_track)
                if isinstance(pending_track, dict)
                else ""
            )
            registered_sources = self.get_registered_source_snapshot().values()
            available_source_ids = {
                str(source.get("id") or "")
                for source in registered_sources
                if isinstance(source, dict)
                and source.get("enabled")
                and source.get("sourceUrl")
            }
            desired_ids = set(self.remote_tracks)
            for stable_id, item in tuple(existing_items.items()):
                if stable_id in desired_ids:
                    continue
                row = self.song_list.row(item)
                if row >= 0:
                    self.song_list.takeItem(row)
                    structure_changed = True
                existing_items.pop(stable_id, None)

            for stable_id, record in self.remote_tracks.items():
                song_data = RemoteTrackStore.to_song_data(
                    stable_id,
                    record,
                    str(record.get("source_id") or "") in available_source_ids,
                    resolving=stable_id == pending_id,
                )
                item = existing_items.get(stable_id)
                if item is None:
                    self.song_list.addItem(self.create_song_list_item(song_data))
                    structure_changed = True
                else:
                    previous_data = item.data(Qt.ItemDataRole.UserRole)
                    if previous_data != song_data:
                        data_changed = True
                    self.refresh_song_item_display(
                        item,
                        song_data,
                        update_viewport=False,
                    )
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

        if not song_list_is_local_only or not remote_store_ready:
            self.rebuild_song_identity_index()
        self.song_list.viewport().update()
        if structure_changed or data_changed:
            self.mark_library_list_dirty()
            if refresh_view:
                self.filter_song_list(self.search_input.text())

    def refresh_remote_song_item(
        self,
        stable_id: str,
        resolving: bool = False,
    ) -> bool:
        stable_id = str(stable_id or "").strip()
        record = self.remote_tracks.get(stable_id)
        if not stable_id or not isinstance(record, dict):
            return False
        track = RemoteTrackStore.to_online_track(stable_id, record)
        identity = self.track_identity_for_song_data(track)
        item = self.find_song_item_by_identity(identity)
        if item is None:
            for row in range(self.song_list.count()):
                candidate = self.song_list.item(row)
                data = (
                    candidate.data(Qt.ItemDataRole.UserRole)
                    if candidate is not None
                    else None
                )
                if (
                    isinstance(data, dict)
                    and str(data.get("remoteStableId") or "") == stable_id
                ):
                    item = candidate
                    break
        song_data = RemoteTrackStore.to_song_data(
            stable_id,
            record,
            self.is_remote_source_available(record),
            resolving=resolving,
        )
        if item is None:
            item = self.create_song_list_item(song_data)
            self.song_list.addItem(item)
            item.setHidden(not self.song_matches_current_view(song_data))
            if identity:
                self.song_identity_to_item[identity] = item
            self.mark_library_list_dirty()
            return True
        self.refresh_song_item_display(item, song_data)
        return True

    def refresh_remote_collection_views(self) -> None:
        self.sync_remote_song_items()
        self.refresh_playlist_view_buttons()
        self.refresh_playlist_membership_views()

    def refresh_playlist_membership_views(self) -> None:
        if self.current_library_view == "liked" or self.current_library_view.startswith("playlist:"):
            self.sort_song_list_for_current_view(force=True)
            self.filter_song_list(self.search_input.text())
        self.refresh_unified_search_result_states()
        self.update_like_button()
        self.update_side_info_panel()

    def get_custom_playlist_ids(self) -> list[str]:
        playlist_ids = []

        for playlist_id, playlist in self.playlists.items():
            if playlist_id == "liked":
                continue

            if not isinstance(playlist, dict):
                continue

            playlist_ids.append(playlist_id)

        playlist_ids.sort(
            key=lambda playlist_id: int(
                self.playlists.get(playlist_id, {}).get("created_at", 0) or 0
            )
        )

        return playlist_ids

    def create_playlist_id(self) -> str:
        base_id = f"playlist_{int(time.time() * 1000)}"
        playlist_id = base_id
        index = 1

        while playlist_id in self.playlists:
            playlist_id = f"{base_id}_{index}"
            index += 1

        return playlist_id

    def refresh_playlist_view_buttons(self) -> None:
        if not hasattr(self, "sidebar_playlist_layout"):
            return

        while self.sidebar_playlist_layout.count():
            item = self.sidebar_playlist_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self.custom_view_buttons = []

        for view_name in list(self.view_buttons.keys()):
            if view_name.startswith("playlist:"):
                self.view_buttons.pop(view_name, None)

        for playlist_id in self.get_custom_playlist_ids():
            playlist_id = str(playlist_id or "").strip()
            playlist = self.playlists.get(playlist_id, {})

            if not playlist_id or playlist_id == "liked" or not isinstance(playlist, dict):
                continue

            playlist_name = str(playlist.get("name", "") or "").strip()

            if not playlist_name:
                continue

            view_name = f"playlist:{playlist_id}"
            button = QPushButton(playlist_name)
            button.setObjectName("playlistSidebarButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(playlist_name)
            button.setMinimumHeight(button.fontMetrics().height() + 16)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            button.setProperty("active", view_name == self.current_library_view)
            button.clicked.connect(lambda checked=False, view=view_name: self.set_library_view(view))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda position, playlist_id=playlist_id, button=button: self.show_custom_playlist_context_menu(
                    playlist_id,
                    button,
                    position,
                )
            )

            self.sidebar_playlist_layout.addWidget(button)
            self.custom_view_buttons.append(button)
            self.view_buttons[view_name] = button

        if hasattr(self, "sidebar_playlist_box"):
            self.sidebar_playlist_box.setVisible(bool(self.custom_view_buttons))

        self.update_view_buttons()

    def show_playlist_sidebar_hint(self, message: str) -> None:
        label = getattr(self, "sidebar_playlist_hint", None)

        if label is None:
            print(message)
            return

        label.setText(str(message or ""))
        timer = getattr(self, "sidebar_playlist_hint_timer", None)

        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.reset_playlist_sidebar_hint)
            self.sidebar_playlist_hint_timer = timer

        timer.start(2600)

    def reset_playlist_sidebar_hint(self) -> None:
        label = getattr(self, "sidebar_playlist_hint", None)

        if label is not None:
            label.setText(getattr(self, "sidebar_playlist_hint_default", "右键歌单进行管理"))

    def get_selected_song_paths_for_playlist_menu(self) -> list[str]:
        if not hasattr(self, "song_list"):
            return []

        selected_paths = []

        for item in self.song_list.selectedItems():
            song_data = self.get_song_data_from_item(item)

            if not song_data:
                continue

            song_path = self.normalize_song_path(song_data.get("path", ""))

            if song_path and song_path not in selected_paths:
                selected_paths.append(song_path)

        return selected_paths

    def add_selected_songs_to_playlist(self, playlist_id: str, song_paths: list[str]) -> None:
        if playlist_id == "liked" or playlist_id not in self.playlists:
            return

        added_count = self.add_local_paths_to_playlist(song_paths, playlist_id)

        playlist_name = self.get_playlist_name(playlist_id)

        if added_count <= 0:
            self.show_playlist_sidebar_hint(f"所选歌曲已经在「{playlist_name}」中")
            return

        if self.current_library_view == f"playlist:{playlist_id}":
            self.sort_song_list_for_current_view(force=True)
            self.filter_song_list(self.search_input.text())

        skipped_count = max(0, len(song_paths) - added_count)

        if skipped_count > 0:
            message = f"已添加 {added_count} 首到「{playlist_name}」，跳过 {skipped_count} 首重复歌曲"
        else:
            message = f"已添加 {added_count} 首到「{playlist_name}」"

        self.show_playlist_sidebar_hint(message)
        print(message)

    def play_playlist_from_sidebar(self, playlist_id: str, shuffle: bool = False) -> None:
        if playlist_id == "liked" or playlist_id not in self.playlists:
            return

        if hasattr(self, "search_input"):
            self.search_input.clear()

        if getattr(self, "library_category_filter_type", None):
            self.clear_library_category_filter(refresh=False)

        self.set_library_view(f"playlist:{playlist_id}")
        playable_items = self.get_visible_song_items()

        if not playable_items:
            self.show_playlist_sidebar_hint(f"「{self.get_playlist_name(playlist_id)}」里还没有可播放的歌曲")
            return

        if shuffle:
            self.play_mode = "shuffle"
            self.update_play_mode_button()
            self.save_settings()
        target_item = random.choice(playable_items) if shuffle else playable_items[0]
        self.song_list.setCurrentItem(target_item)
        self.play_selected_song(target_item)

    def build_custom_playlist_context_menu(self, playlist_id: str) -> QMenu | None:
        if playlist_id == "liked" or playlist_id not in self.playlists:
            return None

        menu = QMenu(self)
        menu.setObjectName("songContextMenu")

        open_action = menu.addAction("打开歌单")
        open_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id: self.set_library_view(f"playlist:{playlist_id}")
        )

        play_all_action = menu.addAction("播放全部")
        play_all_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id: self.play_playlist_from_sidebar(playlist_id)
        )

        shuffle_action = menu.addAction("随机播放")
        shuffle_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id: self.play_playlist_from_sidebar(playlist_id, shuffle=True)
        )

        menu.addSeparator()

        selected_paths = self.get_selected_song_paths_for_playlist_menu()
        add_selected_action = menu.addAction("添加当前选中歌曲到此歌单")
        add_selected_action.setEnabled(bool(selected_paths))
        add_selected_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id, song_paths=selected_paths: self.add_selected_songs_to_playlist(
                playlist_id,
                song_paths,
            )
        )

        menu.addSeparator()

        rename_action = menu.addAction("重命名")
        rename_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id: self.rename_playlist(playlist_id)
        )

        delete_action = menu.addAction("删除歌单")
        delete_action.triggered.connect(
            lambda checked=False, playlist_id=playlist_id: self.delete_playlist(playlist_id)
        )

        return menu

    def show_custom_playlist_context_menu(self, playlist_id: str, button: QPushButton, position) -> None:
        menu = self.build_custom_playlist_context_menu(playlist_id)

        if menu is not None:
            menu.exec(button.mapToGlobal(position))

    def set_library_view(self, view_name: str) -> None:
        started_at = time.perf_counter()
        fixed_views = {"all", "liked", "recent_played", "frequent", "recent_added"}
        previous_view = getattr(self, "current_library_view", "all")
        if view_name in fixed_views:
            target_view = view_name
        elif view_name.startswith("playlist:"):
            playlist_id = view_name.split("playlist:", 1)[1]
            target_view = view_name if playlist_id in self.playlists else "all"
        else:
            target_view = "all"
        self.current_library_view = target_view
        if previous_view != target_view:
            self.library_sort_field = None
            self.library_sort_descending = False
            self.update_library_sort_headers()
        current_key = self.current_library_view_key() if hasattr(self, "song_list") else None
        if (
            previous_view == target_view
            and not getattr(self, "library_list_dirty", True)
            and current_key == getattr(self, "last_library_view_key", None)
        ):
            self.show_library_container()
            self.update_view_buttons()
            self.set_sidebar_active("library")
            return
        self.show_library_container()
        container_ready_at = time.perf_counter()
        self.sort_song_list_for_current_view()
        sorted_at = time.perf_counter()
        self.filter_song_list("")
        filtered_at = time.perf_counter()
        self.update_view_buttons()
        self.remember_library_view_key()
        self.set_sidebar_active("library")
        view_titles = {
            "all": "全部歌曲",
            "liked": "我喜欢",
            "recent_played": "最近播放",
            "frequent": "常听歌曲",
            "recent_added": "最近添加",
        }
        if self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            view_title = self.get_playlist_name(playlist_id)
        else:
            view_title = view_titles.get(self.current_library_view, "全部歌曲")
        if hasattr(self, "library_page"):
            self.library_page.page_title.setText(view_title)
        completed_at = time.perf_counter()
        elapsed_ms = (completed_at - started_at) * 1000
        if target_view == "liked" or target_view.startswith("playlist:"):
            print(
                "[perf] playlist_view phases: "
                f"prepare={(container_ready_at - started_at) * 1000:.1f} ms, "
                f"sort={(sorted_at - container_ready_at) * 1000:.1f} ms, "
                f"filter={(filtered_at - sorted_at) * 1000:.1f} ms, "
                f"selection/highlight/layout={(completed_at - filtered_at) * 1000:.1f} ms"
            )
        print(f"当前音乐库视图：{view_title}")
        print(f"[perf] set_library_view: {elapsed_ms:.1f} ms, view={self.current_library_view}, songs={self.song_list.count() if hasattr(self, 'song_list') else 0}")
    def update_view_buttons(self) -> None:
        if not hasattr(self, "view_buttons"):
            return

        for view_name, button in self.view_buttons.items():
            button.setProperty("active", view_name == self.current_library_view)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def song_matches_base_library_view(
        self,
        song_data: dict,
        liked_paths: set[str] | None = None,
        playlist_paths: set[str] | None = None,
        liked_remote_ids: set[str] | None = None,
        playlist_remote_ids: set[str] | None = None,
    ) -> bool:
        if not isinstance(song_data, dict):
            return True

        if song_data.get("demo"):
            return self.current_library_view == "all"

        if song_data.get("recordKind") == "remote":
            stable_id = str(song_data.get("remoteStableId") or "")
            if self.current_library_view == "liked":
                if liked_remote_ids is not None:
                    return stable_id in liked_remote_ids
                return stable_id in self.get_playlist_remote_ids("liked")
            if self.current_library_view.startswith("playlist:"):
                if playlist_remote_ids is not None:
                    return stable_id in playlist_remote_ids
                playlist_id = self.current_library_view.split("playlist:", 1)[1]
                return stable_id in self.get_playlist_remote_ids(playlist_id)
            return False

        path = song_data.get("path", "")
        normalized_path = self.normalize_song_path(path)

        if self.current_library_view == "all":
            return True

        if self.current_library_view == "liked":
            if liked_paths is not None:
                return normalized_path in liked_paths

            return self.is_song_liked(normalized_path)

        if self.current_library_view == "recent_played":
            stats = self.song_stats.get(normalized_path, {})
            return int(stats.get("last_played", 0)) > 0

        if self.current_library_view == "frequent":
            stats = self.song_stats.get(normalized_path, {})
            play_count = int(stats.get("play_count", 0))
            total_listen_time = int(stats.get("total_listen_time", 0))
            return play_count > 0 or total_listen_time > 0

        if self.current_library_view == "recent_added":
            return bool(normalized_path)

        if self.current_library_view.startswith("playlist:"):
            if playlist_paths is not None:
                return normalized_path in playlist_paths

            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            playlist_songs = self.get_playlist_song_paths(playlist_id)
            return normalized_path in playlist_songs

        return True

    def song_matches_category_filter(self, song_data: dict) -> bool:
        filter_type = getattr(self, "library_category_filter_type", None)
        filter_value = str(getattr(self, "library_category_filter_value", "") or "")

        if filter_type not in {"artist", "album"} or not filter_value:
            return True

        if filter_type == "artist":
            value = str(song_data.get("artist") or "未知艺术家")
        else:
            value = str(song_data.get("album") or "未知专辑")

        return value == filter_value

    def song_matches_current_view(
        self,
        song_data: dict,
        liked_paths: set[str] | None = None,
        playlist_paths: set[str] | None = None,
        liked_remote_ids: set[str] | None = None,
        playlist_remote_ids: set[str] | None = None,
    ) -> bool:
        return self.song_matches_base_library_view(
            song_data,
            liked_paths,
            playlist_paths,
            liked_remote_ids,
            playlist_remote_ids,
        ) and self.song_matches_category_filter(song_data)
    def collect_song_data_from_list(self) -> list[dict]:
        songs = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                songs.append(dict(song_data))

        return songs

    def track_identity_for_song_data(self, song_data: dict | MediaItem | None) -> str:
        if isinstance(song_data, MediaItem):
            item = song_data
        elif isinstance(song_data, dict):
            try:
                item = MediaItem.from_mapping(song_data)
            except (TypeError, ValueError):
                return ""
        else:
            return ""
        return item.stable_identity

    def current_track_identity(self) -> str:
        queue_identity = str(getattr(self, "current_queue_identity", "") or "")
        if queue_identity:
            return queue_identity
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem):
            return current.stable_identity
        playing_path = self.normalize_song_path(getattr(self, "current_song_path", ""))
        if not playing_path:
            return ""
        return MediaItem.from_local({"path": playing_path}).stable_identity

    def rebuild_song_identity_index(self) -> None:
        index: dict[str, QListWidgetItem] = {}
        if hasattr(self, "song_list"):
            for row in range(self.song_list.count()):
                item = self.song_list.item(row)
                data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
                identity = self.track_identity_for_song_data(data)
                if item is not None and identity:
                    index[identity] = item
        self.song_identity_to_item = index

    def find_song_item_by_identity(self, identity: str) -> QListWidgetItem | None:
        identity = str(identity or "")
        if not identity or not hasattr(self, "song_list"):
            return None
        item = getattr(self, "song_identity_to_item", {}).get(identity)
        if item is not None:
            try:
                if self.song_list.row(item) >= 0:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if self.track_identity_for_song_data(data) == identity:
                        return item
            except RuntimeError:
                pass
        self.rebuild_song_identity_index()
        return self.song_identity_to_item.get(identity)

    def format_song_list_item_text(self, song_data: dict, is_playing: bool = False) -> str:
        title = str(song_data.get("title") or "未知歌曲")
        artist = str(song_data.get("artist") or "未知艺术家")
        album = str(song_data.get("album") or "未知专辑")
        remote_prefix = ""
        if song_data.get("recordKind") == "remote":
            status = str(song_data.get("onlineStatus") or "在线")
            remote_prefix = f"☁ {status} · "
        prefix = "▶ " if is_playing else remote_prefix
        return f"{prefix}{title}\n{artist} · {album}"

    def get_song_item_display_text(self, song_data: dict) -> str:
        identity = self.track_identity_for_song_data(song_data)
        is_playing = bool(identity and identity == self.current_track_identity())
        return self.format_song_list_item_text(song_data, is_playing=is_playing)

    def refresh_song_item_display(
        self,
        item: QListWidgetItem,
        song_data: dict,
        update_viewport: bool = True,
    ) -> None:
        item.setText(self.get_song_item_display_text(song_data))
        title = str(song_data.get("title") or "未知歌曲")
        artist = str(song_data.get("artist") or "未知艺术家")
        album = str(song_data.get("album") or "未知专辑")
        item.setToolTip(
            f"歌曲：{title}\n"
            f"歌手：{artist}\n"
            f"专辑：{album}"
            + (
                f"\n状态：{song_data.get('onlineStatus') or '在线'}"
                if song_data.get("recordKind") == "remote"
                else ""
            )
        )
        item.setSizeHint(QSize(0, 58))
        item.setData(Qt.ItemDataRole.UserRole, song_data)
        identity = self.track_identity_for_song_data(song_data)
        if identity:
            self.song_identity_to_item[identity] = item

        if (
            update_viewport
            and hasattr(self, "song_list")
            and self.song_list.row(item) >= 0
        ):
            self.song_list.viewport().update(self.song_list.visualItemRect(item))

    def get_library_duration_seconds(self, song_data: dict) -> int:
        try:
            stored_duration = int(song_data.get("duration", 0) or 0)
        except (TypeError, ValueError):
            stored_duration = 0

        if stored_duration > 0:
            return stored_duration

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            return 0

        return int(self.library_duration_display_cache.get(song_path, 0) or 0)

    @staticmethod
    def format_library_added_date(value: object) -> str:
        try:
            timestamp = int(value or 0)
        except (TypeError, ValueError):
            timestamp = 0

        if timestamp <= 0:
            return "—"

        try:
            return time.strftime("%Y-%m-%d", time.localtime(timestamp))
        except Exception:
            return "—"

    def schedule_visible_library_durations(self, *_args) -> None:
        if not hasattr(self, "song_list") or self.library_duration_refresh_scheduled:
            return

        self.library_duration_refresh_scheduled = True
        QTimer.singleShot(0, self.refresh_visible_library_durations)

    def refresh_visible_library_durations(self) -> None:
        started_at = time.perf_counter()
        self.library_duration_refresh_scheduled = False

        if not hasattr(self, "song_list") or not self.song_list.isVisible():
            return

        viewport_rect = self.song_list.viewport().rect()
        dispatched_count = 0
        has_remaining_visible_rows = False

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is None or item.isHidden():
                continue

            if not self.song_list.visualItemRect(item).intersects(viewport_rect):
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            if song_data.get("recordKind") == "remote":
                continue

            try:
                stored_duration = int(song_data.get("duration", 0) or 0)
            except (TypeError, ValueError):
                stored_duration = 0

            song_path = self.normalize_song_path(song_data.get("path", ""))

            if (
                stored_duration > 0
                or not song_path
                or song_path in self.library_duration_display_cache
                or song_path in self.library_duration_pending_paths
            ):
                continue

            if dispatched_count >= 2:
                has_remaining_visible_rows = True
                continue

            task = LibraryDurationTask(song_path)
            task.signals.finished.connect(
                self.on_library_duration_loaded,
                Qt.ConnectionType.QueuedConnection,
            )
            self.library_duration_pending_paths.add(song_path)
            self.library_duration_tasks[song_path] = task
            self.library_duration_thread_pool.start(task)
            dispatched_count += 1

        if has_remaining_visible_rows:
            QTimer.singleShot(20, self.schedule_visible_library_durations)

        if dispatched_count > 0:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(
                f"[perf] 可见歌曲时长后台派发：{elapsed_ms:.1f} ms, "
                f"dispatched={dispatched_count}"
            )

    def on_library_duration_loaded(
        self,
        song_path: str,
        duration_seconds: int,
        worker_elapsed_ms: float,
    ) -> None:
        callback_started_at = time.perf_counter()
        self.library_duration_tasks.pop(song_path, None)
        self.library_duration_pending_paths.discard(song_path)
        self.library_duration_display_cache[song_path] = max(0, int(duration_seconds))

        if hasattr(self, "song_list"):
            self.song_list.viewport().update()

        callback_elapsed_ms = (time.perf_counter() - callback_started_at) * 1000
        print(
            f"[perf] 歌曲时长后台读取：{worker_elapsed_ms:.1f} ms, "
            f"ui={callback_elapsed_ms:.1f} ms"
        )

    def sort_library_by_column(self, field: str) -> None:
        if field not in {"title", "artist", "album", "added_at"}:
            return

        if self.library_sort_field != field:
            self.library_sort_field = field
            self.library_sort_descending = False
        elif not self.library_sort_descending:
            self.library_sort_descending = True
        else:
            self.library_sort_field = None
            self.library_sort_descending = False
            self.update_library_sort_headers()
            self.sort_song_list_for_current_view(force=True)
            self.filter_song_list(self.search_input.text())
            return

        self.apply_current_library_sort()

    def apply_current_library_sort(self, refresh_view: bool = True) -> bool:
        field = self.library_sort_field

        if field not in {"title", "artist", "album", "added_at"}:
            return False

        playlist_id = self.playlist_id_for_current_view()
        playlist_member_index = (
            self.get_playlist_member_index(playlist_id)
            if field == "added_at" and playlist_id
            else {}
        )

        items = [
            self.song_list.item(row)
            for row in range(self.song_list.count())
            if self.song_list.item(row) is not None
        ]

        def fallback_key(item: QListWidgetItem) -> tuple[str, str, str, str]:
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                return ("", "", "", "")

            return (
                str(song_data.get("title") or "").strip().casefold(),
                str(song_data.get("artist") or "").strip().casefold(),
                str(song_data.get("album") or "").strip().casefold(),
                self.normalize_song_path(song_data.get("path", "")).casefold(),
            )

        def primary_value(item: QListWidgetItem) -> tuple[bool, object]:
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                return False, 0 if field == "added_at" else ""

            if field == "added_at":
                if playlist_id:
                    value = self.playlist_member_added_at_for_song(
                        playlist_id,
                        song_data,
                        playlist_member_index,
                    )
                else:
                    try:
                        value = int(song_data.get("added_at", 0) or 0)
                    except (TypeError, ValueError):
                        value = 0

                return value > 0, value

            value = str(song_data.get(field) or "").strip().casefold()
            return bool(value), value

        # 先建立确定性的次级顺序，再利用 Python 稳定排序处理主字段。
        # 这样相同值不会随多次点击、搜索或视图切换而随机跳动。
        items.sort(key=fallback_key)
        known_items: list[tuple[object, QListWidgetItem]] = []
        unknown_items: list[QListWidgetItem] = []

        for item in items:
            is_known, value = primary_value(item)

            if is_known:
                known_items.append((value, item))
            else:
                unknown_items.append(item)

        known_items.sort(
            key=lambda pair: pair[0],
            reverse=self.library_sort_descending,
        )
        ordered_items = [item for _, item in known_items] + unknown_items
        self.reorder_song_list_items(ordered_items)

        if refresh_view:
            self.filter_song_list(self.search_input.text())

        self.update_library_sort_headers()
        self.remember_library_view_key()
        self.schedule_visible_library_durations()
        return bool(ordered_items)

    def reorder_song_list_items(self, ordered_items: list[QListWidgetItem]) -> None:
        if not ordered_items or len(ordered_items) != self.song_list.count():
            return

        selected_item_ids = {id(item) for item in self.song_list.selectedItems()}
        current_item = self.song_list.currentItem()
        previous_signal_state = self.song_list.blockSignals(True)
        if self.song_list.isSortingEnabled():
            self.song_list.setSortingEnabled(False)
        self.song_list.setUpdatesEnabled(False)

        try:
            while self.song_list.count() > 0:
                self.song_list.takeItem(0)

            for item in ordered_items:
                self.song_list.addItem(item)
                item.setSelected(id(item) in selected_item_ids)

            if current_item is not None:
                self.song_list.setCurrentItem(current_item)
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

    def update_library_sort_headers(self) -> None:
        headers = getattr(self, "library_sort_headers", {})
        labels = {
            "title": "歌曲标题",
            "artist": "歌手",
            "album": "专辑",
            "added_at": "添加时间",
        }

        for field, button in headers.items():
            active = field == self.library_sort_field
            indicator = ""

            if active:
                indicator = " ↓" if self.library_sort_descending else " ↑"

            button.setText(f"{labels.get(field, field)}{indicator}")
            button.setProperty("sortActive", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def refresh_playing_song_indicators(self) -> None:
        started_at = time.perf_counter()

        if not hasattr(self, "song_list"):
            return

        current_identity = self.current_track_identity()
        target_identities = {
            str(getattr(self, "last_playing_indicator_identity", "") or ""),
            current_identity,
        }
        target_identities.discard("")
        refreshed_count = 0

        for identity in target_identities:
            item = self.find_song_item_by_identity(identity)
            song_data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(song_data, dict):
                self.refresh_song_item_display(item, song_data)
                refreshed_count += 1

        if not getattr(self, "library_list_dirty", True):
            self.remember_library_view_key()

        self.last_playing_indicator_path = self.normalize_song_path(getattr(self, "current_song_path", ""))
        self.last_playing_indicator_identity = current_identity
        if hasattr(self, "library_page"):
            self.library_page.refresh_playing_indicator()
        if hasattr(self, "search_page"):
            self.search_page.refresh_playing_indicator()
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] refresh_playing_song_indicators: {elapsed_ms:.1f} ms, refreshed={refreshed_count}, songs={self.song_list.count()}")
    def create_song_list_item(self, song_data: dict) -> QListWidgetItem:
        item = QListWidgetItem()
        self.refresh_song_item_display(item, song_data)
        identity = self.track_identity_for_song_data(song_data)
        if identity:
            self.song_identity_to_item[identity] = item
        return item

    def rebuild_song_list_from_data(self, songs: list[dict]) -> None:
        started_at = time.perf_counter()
        selected_identities = {
            self.track_identity_for_song_data(self.get_song_data_from_item(item))
            for item in self.song_list.selectedItems()
            if self.get_song_data_from_item(item)
        }
        current_item_data = self.get_song_data_from_item(self.song_list.currentItem())
        current_item_identity = self.track_identity_for_song_data(current_item_data)
        browsing_identity = self.track_identity_for_song_data(
            getattr(self, "browsing_song_data", None)
        )
        target_current_identity = browsing_identity or current_item_identity
        restored_current_item = None
        restored_selected_items: list[QListWidgetItem] = []
        previous_signal_state = self.song_list.blockSignals(True)
        self.song_list.setUpdatesEnabled(False)

        try:
            self.song_identity_to_item = {}
            self.song_list.clear()

            for song_data in songs:
                item = self.create_song_list_item(song_data)
                self.song_list.addItem(item)

                identity = self.track_identity_for_song_data(song_data)

                if target_current_identity and identity == target_current_identity:
                    restored_current_item = item

                if identity and identity in selected_identities:
                    restored_selected_items.append(item)

            if restored_current_item is not None:
                self.song_list.setCurrentItem(
                    restored_current_item,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )

            for item in restored_selected_items:
                item.setSelected(True)
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

        self.apply_current_library_sort(refresh_view=False)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] rebuild_song_list_from_data: {elapsed_ms:.1f} ms, songs={self.song_list.count()}")

    def current_song_list_order_key(self) -> tuple:
        song_count = self.song_list.count() if hasattr(self, "song_list") else 0
        view_name = getattr(self, "current_library_view", "all")

        if view_name == "all":
            return ("library_default", song_count)

        if view_name == "liked":
            return (
                "playlist",
                "liked",
                song_count,
                self.get_playlist_membership_signature("liked"),
            )

        if view_name in {"recent_played", "frequent", "recent_added"}:
            return (view_name, song_count, len(getattr(self, "song_stats", {})))

        if view_name.startswith("playlist:"):
            playlist_id = view_name.split("playlist:", 1)[1]
            return (
                "playlist",
                playlist_id,
                song_count,
                self.get_playlist_membership_signature(playlist_id),
            )

        return ("library_default", song_count)

    def sort_song_list_for_current_view(self, force: bool = False) -> bool:
        started_at = time.perf_counter()
        order_key = self.current_song_list_order_key()
        signature_ready_at = time.perf_counter()

        if (
            not force
            and not getattr(self, "library_list_dirty", True)
            and order_key == getattr(self, "last_song_list_order_key", None)
        ):
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[perf] sort_song_list_for_current_view skip: {elapsed_ms:.1f} ms, key={order_key[0]}")
            return False

        items = [
            self.song_list.item(row)
            for row in range(self.song_list.count())
            if self.song_list.item(row) is not None
        ]

        if not items:
            self.last_song_list_order_key = order_key
            return False

        items_ready_at = time.perf_counter()

        def song_data(item: QListWidgetItem) -> dict:
            value = item.data(Qt.ItemDataRole.UserRole)
            return value if isinstance(value, dict) else {}

        def normalized_path(item: QListWidgetItem) -> str:
            return self.normalize_song_path(song_data(item).get("path", ""))

        def stats_for(item: QListWidgetItem) -> dict:
            return self.song_stats.get(
                normalized_path(item),
                {
                    "play_count": 0,
                    "total_listen_time": 0,
                    "last_played": 0,
                },
            )

        if self.current_library_view == "recent_played":
            items.sort(
                key=lambda item: int(stats_for(item).get("last_played", 0)),
                reverse=True,
            )

        elif self.current_library_view == "frequent":
            items.sort(
                key=lambda item: (
                    int(stats_for(item).get("play_count", 0)),
                    int(stats_for(item).get("total_listen_time", 0)),
                    int(stats_for(item).get("last_played", 0)),
                ),
                reverse=True,
            )

        elif self.current_library_view == "recent_added":
            items.sort(
                key=lambda item: int(song_data(item).get("added_at", 0) or 0),
                reverse=True,
            )

        elif (
            self.current_library_view == "liked"
            or self.current_library_view.startswith("playlist:")
        ):
            playlist_id = self.playlist_id_for_current_view()
            member_index = self.get_playlist_member_index(playlist_id)
            member_index_ready_at = time.perf_counter()
            items.sort(
                key=lambda item: (
                    self.playlist_member_added_at_for_song(
                        playlist_id,
                        song_data(item),
                        member_index,
                    ),
                    self.track_identity_for_song_data(song_data(item)),
                ),
                reverse=True,
            )

        else:
            items.sort(
                key=lambda item: int(song_data(item).get("added_at", 0) or 0),
            )

        sorted_at = time.perf_counter()
        self.reorder_song_list_items(items)
        if self.library_sort_field in {"title", "artist", "album", "added_at"}:
            self.apply_current_library_sort(refresh_view=False)
        reordered_at = time.perf_counter()
        self.last_song_list_order_key = order_key
        elapsed_ms = (reordered_at - started_at) * 1000
        if self.playlist_id_for_current_view():
            print(
                "[perf] playlist_view_sort phases: "
                f"signature={(signature_ready_at - started_at) * 1000:.1f} ms, "
                f"collect={(items_ready_at - signature_ready_at) * 1000:.1f} ms, "
                f"member_index={(member_index_ready_at - items_ready_at) * 1000:.1f} ms, "
                f"sort={(sorted_at - member_index_ready_at) * 1000:.1f} ms, "
                f"reorder={(reordered_at - sorted_at) * 1000:.1f} ms"
            )
        print(f"[perf] sort_song_list_for_current_view: {elapsed_ms:.1f} ms, key={order_key[0]}")
        return True
    def create_new_playlist(self) -> None:
        name, ok = self.get_dark_text_input(
            "新建歌单",
            "输入歌单名称：",
            placeholder="例如：通勤歌单",
        )

        if not ok:
            return

        name = name.strip()

        if not name:
            self.show_playlist_sidebar_hint("歌单名称不能为空")
            return

        playlist_id = self.create_playlist_id()

        self.playlists[playlist_id] = {
            "name": name,
            "songs": [],
            "remoteSongs": [],
            "members": [],
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": False,
            "created_at": int(time.time()),
        }

        self.save_playlists()
        self.refresh_playlist_view_buttons()
        self.set_library_view(f"playlist:{playlist_id}")

        print("已新建歌单：", name)

    def rename_current_playlist(self) -> None:
        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到一个自定义歌单。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]

        self.rename_playlist(playlist_id)

    def rename_playlist(self, playlist_id: str) -> None:
        if playlist_id == "liked" or playlist_id not in self.playlists:
            return

        old_name = self.get_playlist_name(playlist_id)

        new_name, ok = self.get_dark_text_input(
            "重命名歌单",
            "输入新的歌单名称：",
            text=old_name,
            placeholder=old_name,
        )

        if not ok:
            return

        new_name = new_name.strip()

        if not new_name:
            self.show_playlist_sidebar_hint("歌单名称不能为空")
            return

        if new_name == old_name:
            return

        self.playlists[playlist_id]["name"] = new_name
        self.save_playlists()
        self.refresh_playlist_view_buttons()
        self.update_view_buttons()

        self.show_playlist_sidebar_hint(f"已将「{old_name}」重命名为「{new_name}」")
        print(f"歌单已重命名：{old_name} -> {new_name}")

    def delete_current_playlist(self) -> None:
        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到一个自定义歌单。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]

        self.delete_playlist(playlist_id)

    def delete_playlist(self, playlist_id: str) -> None:
        if playlist_id == "liked" or playlist_id not in self.playlists:
            return

        playlist_name = self.get_playlist_name(playlist_id)

        result = self.ask_dark_confirmation(
            "删除歌单",
            f"确定删除歌单「{playlist_name}」吗？\n这不会删除真实音乐文件。",
            danger_button=QMessageBox.StandardButton.Yes,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        was_open = self.current_library_view == f"playlist:{playlist_id}"
        self.playlists.pop(playlist_id, None)

        self.save_playlists()
        self.refresh_playlist_view_buttons()

        if was_open:
            self.current_library_view = "all"
            self.set_library_view("all")
        else:
            self.update_view_buttons()

        self.show_playlist_sidebar_hint(f"已删除歌单「{playlist_name}」；歌曲文件未删除")
        print("已删除歌单：", playlist_name)

    def get_current_selected_song_path(self) -> str:
        item = self.song_list.currentItem()

        if not item:
            return self.normalize_song_path(self.current_song_path)

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return self.normalize_song_path(self.current_song_path)

        return self.normalize_song_path(song_data.get("path", ""))

    def add_current_song_to_playlist(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        custom_playlist_ids = self.get_custom_playlist_ids()

        if not custom_playlist_ids:
            result = QMessageBox.question(
                self,
                "还没有歌单",
                "你还没有自定义歌单，要现在新建一个吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if result == QMessageBox.StandardButton.Yes:
                self.create_new_playlist()

            return

        choices = []
        choice_to_id = {}

        for playlist_id in custom_playlist_ids:
            name = self.get_playlist_name(playlist_id)
            choices.append(name)
            choice_to_id[name] = playlist_id

        selected_name, ok = self.get_dark_item_input(
            "添加到歌单",
            "选择要加入的歌单：",
            choices,
        )

        if not ok:
            return

        playlist_id = choice_to_id.get(selected_name)

        if not playlist_id:
            return

        added = self.add_local_path_to_playlist(song_path, playlist_id)

        if added:
            self.refresh_playlist_membership_views()

        print(f"已添加到歌单「{selected_name}」：", song_path)

    def remove_current_song_from_current_playlist(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        if self.current_library_view == "liked":
            if self.remove_local_path_from_playlist(song_path, "liked"):
                self.update_like_button()
                self.update_side_info_panel()
                self.refresh_playlist_membership_views()

            return

        if not self.current_library_view.startswith("playlist:"):
            QMessageBox.information(self, "提示", "请先切换到某个歌单视图。")
            return

        playlist_id = self.current_library_view.split("playlist:", 1)[1]
        if self.remove_local_path_from_playlist(song_path, playlist_id):
            self.refresh_playlist_membership_views()

            print("已从当前歌单移除：", song_path)

    def _create_side_info_row(self, name: str, value_widget: QWidget) -> QFrame:
        row = QFrame()
        row.setObjectName("sideInfoRow")

        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        name_label = QLabel(name)
        name_label.setObjectName("sideInfoName")

        value_widget.setObjectName("sideInfoValue")

        layout.addWidget(name_label)
        layout.addWidget(value_widget)

        return row

    def set_right_panel_mode(self, mode: str) -> None:
        if not hasattr(self, "lyrics_view"):
            return

        if hasattr(self, "side_info_panel"):
            self.side_info_panel.hide()

        self.lyrics_view.show()

        lyrics_content = self.lyrics_view.widget()

        if mode == "info":
            if lyrics_content:
                lyrics_content.hide()

            self.lyrics_view.setEnabled(False)
            self.lyrics_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        else:
            if lyrics_content:
                lyrics_content.show()

            self.lyrics_view.setEnabled(True)
            self.lyrics_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def format_last_played_text(self, timestamp: int) -> str:
        timestamp = int(timestamp or 0)

        if timestamp <= 0:
            return "还没有播放记录"

        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
        except Exception:
            return "未知时间"

    def get_current_info_song_data(self) -> dict | None:
        current = self.get_displayed_online_media_item()
        if current is None:
            current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            return current.to_dict()
        playing_path = self.normalize_song_path(self.current_song_path)

        if not playing_path:
            return None

        return self.find_song_data_by_path(playing_path)

    def update_side_info_panel(self) -> None:
        if not hasattr(self, "side_info_panel"):
            return

        song_data = self.get_current_info_song_data()

        if not song_data:
            self.side_artist_detail.setText("未知艺术家")
            self.side_album_detail.setText("未知专辑")
            self.side_like_detail.setText("未收藏")
            self.side_play_count_detail.setText("0 次")
            self.side_listen_time_detail.setText("0:00")
            self.side_last_played_detail.setText("还没有播放记录")
            self.side_lyrics_status_value.setText("等待选择歌曲")
            self.side_file_detail.setText("")
            return

        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")
        song_path = self.normalize_song_path(song_data.get("path", ""))
        current = self.get_displayed_online_media_item()
        if current is None:
            current = getattr(self, "current_media_item", None)
        is_online = isinstance(current, MediaItem) and current.media_type == "online"

        stats = self.song_stats.get(
            song_path,
            {
                "play_count": 0,
                "total_listen_time": 0,
                "last_played": 0,
            },
        )

        play_count = int(stats.get("play_count", 0))
        total_listen_time = int(stats.get("total_listen_time", 0))
        last_played = int(stats.get("last_played", 0))

        if hasattr(self, "lyrics_status_label"):
            lyrics_status = self.lyrics_status_label.text().replace("歌词：", "").strip()
        else:
            lyrics_status = "未知"

        self.side_artist_detail.setText(str(artist))
        self.side_album_detail.setText(str(album))
        liked = (
            bool(self.get_online_track_collection_state(current.to_dict()).get("liked"))
            if is_online
            else self.is_song_liked(song_path)
        )
        self.side_like_detail.setText("已收藏" if liked else "未收藏")
        self.side_play_count_detail.setText(f"{play_count} 次")
        self.side_listen_time_detail.setText(self.format_listen_time(total_listen_time))
        self.side_last_played_detail.setText(self.format_last_played_text(last_played))
        self.side_lyrics_status_value.setText(lyrics_status or "未知")
        self.side_file_detail.setText(current.source_name if is_online else song_path)

    def open_immersive_lyrics_window(self) -> None:
        was_already_visible = (
            self.immersive_lyrics_window is not None
            and self.immersive_lyrics_window.isVisible()
        )

        if self.immersive_lyrics_window is None:
            self.immersive_lyrics_window = ImmersiveLyricsWindow(self)

        self.sync_immersive_lyrics()
        self.immersive_lyrics_window.show_on_best_screen()

        if not was_already_visible:
            self.minimize_main_for_immersive()

    def minimize_main_for_immersive(self) -> None:
        self.main_was_minimized_before_immersive = self.isMinimized()
        self.main_was_maximized_before_immersive = self.isMaximized()
        self.restore_main_after_immersive = not self.main_was_minimized_before_immersive

        if not self.main_was_minimized_before_immersive:
            QTimer.singleShot(100, self.showMinimized)

    def on_immersive_lyrics_closed(self) -> None:
        if not getattr(self, "restore_main_after_immersive", False):
            return

        self.restore_main_after_immersive = False

        if getattr(self, "main_was_maximized_before_immersive", False):
            self.showMaximized()
        else:
            self.showNormal()

        self.raise_()
        self.activateWindow()

    def get_playing_song_display_data(self) -> tuple[str, str, str]:
        media_item = getattr(self, "current_media_item", None)
        if isinstance(media_item, MediaItem):
            if hasattr(self, "lyrics_status_label"):
                status = self.lyrics_status_label.text().replace("歌词：", "").strip()
            else:
                status = "歌词状态未知"
            source_suffix = (
                f" · {media_item.source_name} · 在线"
                if media_item.media_type == "online"
                else ""
            )
            return (
                media_item.title,
                f"{media_item.artist} · {media_item.album}{source_suffix}",
                status or "歌词状态未知",
            )
        playing_path = self.normalize_song_path(self.current_song_path)

        if not playing_path:
            return "还没有播放音乐", "双击歌曲或右键播放后打开沉浸歌词", "等待播放歌曲"

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
        else:
            title = Path(playing_path).stem
            artist = "未知艺术家"
            album = "未知专辑"

        if hasattr(self, "lyrics_status_label"):
            status = self.lyrics_status_label.text().replace("歌词：", "").strip()
        else:
            status = "歌词状态未知"

        return str(title), f"{artist} · {album}", status or "歌词状态未知"

    def get_immersive_background_pixmap(self, playing_path: str | None):
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            try:
                pixmap = self.cover_label.pixmap()
                return pixmap if pixmap and not pixmap.isNull() else None
            except Exception:
                return None
        normalized_path = self.normalize_song_path(playing_path)

        if not normalized_path:
            return None

        try:
            if hasattr(self, "cover_label"):
                current_pixmap = self.cover_label.pixmap()

                if current_pixmap and not current_pixmap.isNull():
                    return current_pixmap
        except Exception:
            pass

        try:
            cache_path = self.get_song_cache_path(normalized_path, self.cover_cache_dir, ".jpg")

            if cache_path and cache_path.exists():
                cached_pixmap = QPixmap(str(cache_path))

                if not cached_pixmap.isNull():
                    return cached_pixmap
        except Exception as error:
            print("读取沉浸封面缓存失败：", error)

        try:
            song_dir = Path(normalized_path).parent
            cover_names = [
                "cover.jpg",
                "cover.png",
                "cover.jpeg",
                "folder.jpg",
                "folder.png",
                "folder.jpeg",
                "front.jpg",
                "front.png",
                "front.jpeg",
                "album.jpg",
                "album.png",
                "album.jpeg",
            ]

            for cover_name in cover_names:
                cover_path = song_dir / cover_name

                if not cover_path.exists():
                    continue

                folder_pixmap = QPixmap(str(cover_path))

                if not folder_pixmap.isNull():
                    return folder_pixmap
        except Exception as error:
            print("读取沉浸文件夹封面失败：", error)

        return None

    def sync_immersive_lyrics(self) -> None:
        if self.immersive_lyrics_window is None:
            return
        title, artist_album, status = self.get_playing_song_display_data()
        self.immersive_lyrics_window.update_song_info(title, artist_album, status)
        playing_path = self.normalize_song_path(self.current_song_path)
        self.immersive_lyrics_window.update_background_cover(
            self.get_immersive_background_pixmap(playing_path)
        )
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            if self.displayed_lyrics_track_key != current.stable_identity:
                self.immersive_lyrics_window.set_lyrics([])
            elif self.current_plain_lyrics:
                self.immersive_lyrics_window.set_plain_text(self.current_plain_lyrics)
            elif self.current_lyrics:
                self.immersive_lyrics_window.set_lyrics(self.current_lyrics)
                self.immersive_lyrics_window.update_position(
                    self.media_player.position(), self.current_lyrics
                )
            else:
                self.immersive_lyrics_window.set_lyrics([])
            return
        displayed_path = self.normalize_song_path(
            getattr(self, "displayed_lyrics_song_path", "")
        )
        if playing_path and displayed_path == playing_path and self.current_lyrics:
            self.immersive_lyrics_window.set_lyrics(self.current_lyrics)
            self.immersive_lyrics_window.update_position(
                self.media_player.position(), self.current_lyrics
            )
        else:
            self.immersive_lyrics_window.set_lyrics([])
    def _create_full_lyrics_page(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("fullLyricsPage")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(44, 34, 44, 34)
        layout.setSpacing(18)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(7)

        page_title = QLabel("歌词")
        page_title.setObjectName("fullLyricsPageTitle")

        page_subtitle = QLabel("这里显示正在播放歌曲的歌词。单击音乐库里的其他歌不会影响这个页面。")
        page_subtitle.setObjectName("fullLyricsPageSubtitle")

        self.full_lyrics_title = ElidedLabel("还没有播放音乐")
        self.full_lyrics_title.setObjectName("fullLyricsSongTitle")
        self.full_lyrics_title.setMinimumWidth(360)

        self.full_lyrics_artist = ElidedLabel("双击歌曲或右键播放后，这里会显示正在播放的歌词")
        self.full_lyrics_artist.setObjectName("fullLyricsArtist")
        self.full_lyrics_artist.setMinimumWidth(360)

        self.full_lyrics_status = QLabel("等待播放歌曲")
        self.full_lyrics_status.setObjectName("fullLyricsStatus")
        self.full_lyrics_status.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title_box.addWidget(page_title)
        title_box.addWidget(page_subtitle)
        title_box.addSpacing(8)
        title_box.addWidget(self.full_lyrics_title)
        title_box.addWidget(self.full_lyrics_artist)
        title_box.addWidget(self.full_lyrics_status)

        immersive_btn = QPushButton("打开沉浸歌词")
        immersive_btn.setObjectName("primaryButton")
        immersive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        immersive_btn.clicked.connect(self.open_immersive_lyrics_window)

        back_btn = QPushButton("返回音乐库")
        back_btn.setObjectName("secondaryButton")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.show_library_page)

        button_box = QVBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(immersive_btn)
        button_box.addWidget(back_btn)

        header_layout.addLayout(title_box, 1)
        header_layout.addLayout(button_box)

        self.full_lyrics_view = LyricsView()
        self.full_lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "双击一首歌播放，然后点击左侧“歌词”查看大歌词页面",
        )

        layout.addLayout(header_layout)
        layout.addWidget(self.full_lyrics_view, 1)

        return panel

    def show_library_container(self, preserve_scroll: bool = False) -> None:
        if hasattr(self, "content_stack"):
            library_panel = getattr(self, "library_panel", None)

            if library_panel is not None:
                if preserve_scroll and self.content_stack.currentWidget() is not library_panel:
                    self._preserve_page_scroll_once = library_panel
                self.content_stack.setCurrentWidget(library_panel)
            else:
                self.content_stack.setCurrentIndex(0)

            if getattr(self, "_preserve_page_scroll_once", None) is library_panel:
                self._preserve_page_scroll_once = None

            if not preserve_scroll:
                self.reset_page_scroll_to_top(library_panel)

        self.set_right_panel_mode("lyrics")

    def reset_page_scroll_to_top(self, page: QWidget | None) -> None:
        if page is None:
            return

        def reset() -> None:
            scroll_areas: list[QWidget] = []
            if isinstance(page, (QAbstractItemView, QScrollArea)):
                scroll_areas.append(page)
            scroll_areas.extend(page.findChildren(QAbstractItemView))
            scroll_areas.extend(page.findChildren(QScrollArea))
            seen: set[int] = set()
            for area in scroll_areas:
                if id(area) in seen or isinstance(area, LyricsView):
                    continue
                seen.add(id(area))
                vertical_bar = area.verticalScrollBar()
                vertical_bar.setValue(vertical_bar.minimum())
                if isinstance(area, QAbstractItemView):
                    area.scrollToTop()

        QTimer.singleShot(0, reset)

    def on_content_page_changed(self, _index: int) -> None:
        page = (
            self.content_stack.currentWidget()
            if hasattr(self, "content_stack")
            else None
        )
        if (
            hasattr(self, "search_page")
            and page is not self.search_page
            and getattr(self, "search_debounce_timer", None) is not None
        ):
            self.cancel_pending_local_search()
        if page is getattr(self, "_preserve_page_scroll_once", None):
            self._preserve_page_scroll_once = None
            return
        self.reset_page_scroll_to_top(page)

    def set_sidebar_active(self, active_key: str) -> None:
        nav_buttons = {
            "playlists": getattr(self, "playlist_nav_button", None),
            "lyrics": getattr(self, "lyrics_nav_button", None),
            "pending": getattr(self, "pending_nav_button", None),
            "search": getattr(self, "search_nav_button", None),
            "custom_sources": getattr(self, "custom_sources_nav_button", None),
            "settings": getattr(self, "settings_nav_button", None),
        }

        for key, button in nav_buttons.items():
            if button is None:
                continue

            button.setProperty("active", key == active_key)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        if active_key == "library":
            self.update_view_buttons()
        else:
            for button in getattr(self, "view_buttons", {}).values():
                button.setProperty("active", False)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

    def current_library_view_key(self) -> tuple:
        song_count = self.song_list.count() if hasattr(self, "song_list") else 0
        playing_identity = self.current_track_identity()
        category_type = getattr(self, "library_category_filter_type", None)
        category_value = getattr(self, "library_category_filter_value", "")
        return (
            self.current_library_view,
            song_count,
            playing_identity,
            category_type,
            category_value,
        )

    def mark_library_list_dirty(self) -> None:
        self.library_list_dirty = True
        self.library_data_revision = int(getattr(self, "library_data_revision", 0)) + 1
        self.invalidate_local_song_match_index()
        page = getattr(self, "library_page", None)
        if page is not None:
            page.invalidate_group_cache()

    def remember_library_view_key(self) -> None:
        self.last_library_view_key = self.current_library_view_key()
        self.library_list_dirty = False

    def reset_library_to_all_songs(self) -> None:
        if not hasattr(self, "set_library_view") or not hasattr(self, "song_list"):
            self.current_library_view = "all"

            if hasattr(self, "update_view_buttons"):
                self.update_view_buttons()

            return

        if self.current_library_view == "all":
            current_key = self.current_library_view_key()

            if not getattr(self, "library_list_dirty", True) and current_key == getattr(self, "last_library_view_key", None):
                self.update_view_buttons()
                return

        if getattr(self, "library_category_filter_type", None):
            self.clear_library_category_filter(refresh=False)

        self.set_library_view("all")

    def show_library_page(self) -> None:
        started_at = time.perf_counter()
        self.set_sidebar_active("library")
        self.show_library_container()
        self.reset_library_to_all_songs()
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] show_library_page: {elapsed_ms:.1f} ms, dirty={getattr(self, 'library_list_dirty', False)}, key={self.current_library_view_key() if hasattr(self, 'song_list') else None}")

    def show_library_category(self, view_name: str) -> None:
        self.set_sidebar_active("library")
        self.show_library_container()
        self.set_library_view(view_name)

    def return_to_library_view(self) -> None:
        reuse_cached_view = self.can_reuse_library_view_after_search()
        self.set_sidebar_active("library")
        self.show_library_container(preserve_scroll=reuse_cached_view)
        if not reuse_cached_view:
            self.filter_song_list("")
        self.update_view_buttons()
        self.search_entry_library_revision = None
        self.search_entry_library_view_key = None

    def can_reuse_library_view_after_search(self) -> bool:
        if (
            not hasattr(self, "content_stack")
            or not hasattr(self, "search_page")
            or self.content_stack.currentWidget() is not self.search_page
        ):
            return False
        if getattr(self, "library_list_dirty", True):
            return False
        current_key = self.current_library_view_key()
        return (
            current_key == getattr(self, "last_library_view_key", None)
            and current_key == getattr(self, "search_entry_library_view_key", None)
            and int(getattr(self, "library_data_revision", 0))
            == getattr(self, "search_entry_library_revision", None)
        )

    def show_search_page(self) -> None:
        self.set_sidebar_active("search")
        if hasattr(self, "content_stack") and hasattr(self, "search_page"):
            if self.content_stack.currentWidget() is not self.search_page:
                self.search_entry_library_revision = int(
                    getattr(self, "library_data_revision", 0)
                )
                self.search_entry_library_view_key = self.current_library_view_key()
            self.content_stack.setCurrentWidget(self.search_page)
            self.search_page.set_keyword(self.search_input.text())
            self.schedule_local_search_if_needed()
        self.set_right_panel_mode("info")

    def show_liked_playlist_page(self) -> None:
        started_at = time.perf_counter()
        self.set_sidebar_active("library")
        self.show_library_container()
        self.set_library_view("liked")
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] show_liked_playlist_page: {elapsed_ms:.1f} ms")

    def show_full_lyrics_page(self) -> None:
        self.set_sidebar_active("lyrics")
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentIndex(1)

        self.set_right_panel_mode("info")
        self.refresh_full_lyrics_page()

    def set_online_status_message(self, message: str) -> None:
        text = str(message or "")
        page = getattr(self, "online_search_page", None)
        if page is not None:
            page.set_online_status(text)
        panel = getattr(self, "unified_search_panel", None)
        if panel is not None:
            panel.set_status(text)

    def initialize_online_source_framework(self) -> None:
        client = getattr(self, "online_source_client", None)

        if client is None:
            return

        client.start()
        client.list_sources()

    def get_displayed_online_media_item(self) -> MediaItem | None:
        pending = getattr(self, "pending_online_media_item", None)
        if isinstance(pending, MediaItem) and pending.media_type == "online":
            return pending
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            return current
        return None

    def capture_online_playback_ui_snapshot(self) -> None:
        if self.pending_online_ui_snapshot is not None:
            return
        cover_pixmap = self.cover_label.pixmap()
        self.pending_online_ui_snapshot = {
            "bottom_title": self.bottom_song_title.text(),
            "bottom_artist": self.bottom_song_artist.text(),
            "bottom_title_tip": self.bottom_song_title.toolTip(),
            "bottom_artist_tip": self.bottom_song_artist.toolTip(),
            "now_title": self.now_song_title.text(),
            "now_artist": self.now_artist.text(),
            "now_stats": self.now_stats.text() if hasattr(self, "now_stats") else "",
            "now_stats_visible": not self.now_stats.isHidden() if hasattr(self, "now_stats") else False,
            "open_text": (
                self.now_open_folder_btn.text()
                if hasattr(self, "now_open_folder_btn")
                else ""
            ),
            "open_enabled": (
                self.now_open_folder_btn.isEnabled()
                if hasattr(self, "now_open_folder_btn")
                else False
            ),
            "source_text": (
                self.bottom_source_badge.text()
                if hasattr(self, "bottom_source_badge")
                else ""
            ),
            "source_visible": (
                not self.bottom_source_badge.isHidden()
                if hasattr(self, "bottom_source_badge")
                else False
            ),
            "cover_pixmap": QPixmap(cover_pixmap) if cover_pixmap is not None else QPixmap(),
            "cover_text": self.cover_label.text(),
        }

    def restore_online_playback_ui_snapshot(self) -> None:
        snapshot = self.pending_online_ui_snapshot
        self.pending_online_ui_snapshot = None
        self.pending_online_media_item = None
        self.presented_online_identity = ""
        self.presented_online_cover_url = ""
        self.online_artwork_service.cancel()
        if not isinstance(snapshot, dict):
            self.update_side_info_panel()
            return
        self.bottom_song_title.setText(str(snapshot.get("bottom_title") or ""))
        self.bottom_song_artist.setText(str(snapshot.get("bottom_artist") or ""))
        self.bottom_song_title.setToolTip(str(snapshot.get("bottom_title_tip") or ""))
        self.bottom_song_artist.setToolTip(str(snapshot.get("bottom_artist_tip") or ""))
        self.now_song_title.setText(str(snapshot.get("now_title") or ""))
        self.now_artist.setText(str(snapshot.get("now_artist") or ""))
        if hasattr(self, "now_stats"):
            self.now_stats.setText(str(snapshot.get("now_stats") or ""))
            self.now_stats.setVisible(bool(snapshot.get("now_stats_visible")))
        if hasattr(self, "now_open_folder_btn"):
            self.now_open_folder_btn.setText(str(snapshot.get("open_text") or ""))
            self.now_open_folder_btn.setEnabled(bool(snapshot.get("open_enabled")))
        if hasattr(self, "bottom_source_badge"):
            self.bottom_source_badge.setText(str(snapshot.get("source_text") or ""))
            self.bottom_source_badge.setVisible(bool(snapshot.get("source_visible")))
        cover_pixmap = snapshot.get("cover_pixmap")
        if isinstance(cover_pixmap, QPixmap) and not cover_pixmap.isNull():
            self.show_cover_pixmap(cover_pixmap)
        else:
            self.cover_label.clear()
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText(str(snapshot.get("cover_text") or "Hush"))
        self.update_like_button()
        self.update_side_info_panel()

    def cancel_pending_online_metadata(self) -> None:
        request_id = int(getattr(self, "pending_online_metadata_request", 0) or 0)
        self.pending_online_metadata_request = 0
        self.pending_online_metadata_identity = ""
        if request_id:
            self.online_source_client.cancel_request(request_id)

    def present_online_media_item(self, media_item: MediaItem, resolving: bool = False) -> None:
        title = media_item.title
        artist = media_item.artist
        album = media_item.album
        self.bottom_song_title.setText(title)
        self.bottom_song_artist.setText(artist)
        self.bottom_song_title.setToolTip(title)
        self.bottom_song_artist.setToolTip(artist)
        self.now_song_title.setText(title)
        self.now_artist.setText(f"{artist} · {album}")
        if hasattr(self, "now_stats"):
            details = [media_item.source_name or media_item.source_id or "在线", "在线"]
            if resolving:
                details.append("正在解析")
            if media_item.quality:
                details.append(media_item.quality)
            if media_item.format:
                details.append(media_item.format.upper())
            self.now_stats.setText(" · ".join(details))
            self.now_stats.show()
        if hasattr(self, "now_open_folder_btn"):
            self.now_open_folder_btn.setText("查看在线歌曲信息")
            self.now_open_folder_btn.setEnabled(True)
        if hasattr(self, "bottom_source_badge"):
            self.bottom_source_badge.setText(
                media_item.source_name or media_item.source_id or "在线"
            )
            self.bottom_source_badge.setVisible(
                getattr(self, "_responsive_mode", "full") == "full"
            )
        identity = media_item.stable_identity
        cover_url = media_item.cover_url
        artwork_changed = (
            identity != self.presented_online_identity
            or cover_url != self.presented_online_cover_url
        )
        self.presented_online_identity = identity
        self.presented_online_cover_url = cover_url
        if artwork_changed:
            self.reset_cover()
            self.online_artwork_service.request(identity, cover_url)
        if resolving and hasattr(self, "like_btn"):
            liked = bool(
                self.get_online_track_collection_state(media_item.to_dict()).get("liked")
            )
            self.like_btn.setText("♥ 已收藏" if liked else "♡ 收藏")
            self.like_btn.setProperty("liked", liked)
            self.like_btn.setEnabled(False)
            self.like_btn.style().unpolish(self.like_btn)
            self.like_btn.style().polish(self.like_btn)
            self.like_btn.update()
        else:
            self.update_like_button()
        self.update_side_info_panel()

    def on_online_metadata_finished(
        self,
        request_id: int,
        source_id: str,
        result: dict,
    ) -> None:
        if request_id != self.pending_online_metadata_request:
            return
        identity = self.pending_online_metadata_identity
        self.pending_online_metadata_request = 0
        self.pending_online_metadata_identity = ""
        target = getattr(self, "pending_online_media_item", None)
        is_pending = (
            isinstance(target, MediaItem)
            and target.stable_identity == identity
            and target.source_id == source_id
        )
        if not is_pending:
            target = getattr(self, "current_media_item", None)
        if (
            not isinstance(target, MediaItem)
            or target.media_type != "online"
            or target.stable_identity != identity
            or target.source_id != source_id
        ):
            return
        updated = target.with_metadata(result)
        if is_pending:
            self.pending_online_media_item = updated
            self.pending_online_track = updated.to_legacy_online()
        else:
            self.current_media_item = updated
            self.current_online_track = updated.to_legacy_online()
        self.present_online_media_item(
            updated,
            resolving=is_pending and bool(self.pending_online_playback_request),
        )

    def begin_playback_generation(self, identity: str) -> int:
        identity = str(identity or "")
        self.playback_generation = int(getattr(self, "playback_generation", 0) or 0) + 1
        self.current_queue_identity = identity
        self.media_loading_generation = self.playback_generation
        self.handled_end_generation = -1
        if identity != getattr(self, "online_loop_retry_identity", ""):
            self.online_loop_retry_identity = identity
            self.online_loop_retry_count = 0
        return self.playback_generation

    def request_online_playback(
        self,
        track: dict,
        *,
        playback_generation: int | None = None,
        queue_identity: str = "",
        keep_target_on_failure: bool = False,
    ) -> None:
        if not isinstance(track, dict):
            return
        media_item = MediaItem.from_mapping(track)
        track = media_item.to_legacy_online()
        source_id = media_item.source_id
        if not source_id:
            self.set_online_status_message("播放请求缺少音源标识。")
            return

        identity = str(queue_identity or media_item.stable_identity)
        if playback_generation is None:
            playback_generation = self.begin_playback_generation(identity)
        elif playback_generation != self.playback_generation:
            return
        else:
            self.current_queue_identity = identity
            self.media_loading_generation = playback_generation

        previous_request = int(getattr(self, "pending_online_playback_request", 0) or 0)
        if previous_request:
            self.online_source_client.cancel_request(previous_request)
        self.cancel_pending_online_metadata()
        self.capture_online_playback_ui_snapshot()
        self.pending_online_media_item = media_item
        self.pending_online_track = dict(track)
        self.pending_online_playback_generation = playback_generation
        self.pending_online_playback_identity = identity
        self.pending_online_keep_target_on_failure = bool(keep_target_on_failure)
        self.pending_online_playback_request = self.online_source_client.resolve_playback(
            source_id,
            track,
        )
        self.pending_online_metadata_identity = media_item.stable_identity
        self.pending_online_metadata_request = self.online_source_client.get_metadata(
            source_id,
            track,
            timeout_ms=10000,
        )
        self.present_online_media_item(media_item, resolving=True)
        stable_id = str(track.get("remoteStableId") or "")
        if stable_id:
            self.refresh_remote_song_item(stable_id, resolving=True)

    def finish_online_playback_failure(self) -> None:
        keep_target = bool(
            getattr(self, "pending_online_keep_target_on_failure", False)
        )
        self.pending_online_keep_target_on_failure = False
        if not keep_target:
            self.restore_online_playback_ui_snapshot()
            return
        target = getattr(self, "pending_online_media_item", None)
        self.pending_online_ui_snapshot = None
        self.pending_online_media_item = None
        if isinstance(target, MediaItem):
            self.current_track_kind = "online"
            self.current_media_item = target
            self.current_online_track = target.to_legacy_online()
            self.current_song_path = None
            self.invalidate_media_worker_request("cover")
            self.invalidate_media_worker_request("lyrics")
            self.current_queue_identity = target.stable_identity
            self.present_online_media_item(target)
            self.refresh_playing_song_indicators()

    def on_online_playback_resolved(
        self,
        request_id: int,
        source_id: str,
        resolution: dict,
    ) -> None:
        if request_id != self.pending_online_playback_request:
            return
        track = self.pending_online_track
        pending_media_item = self.pending_online_media_item
        pending_generation = int(
            getattr(self, "pending_online_playback_generation", 0) or 0
        )
        pending_identity = str(
            getattr(self, "pending_online_playback_identity", "") or ""
        )
        keep_target_on_failure = bool(
            getattr(self, "pending_online_keep_target_on_failure", False)
        )
        self.pending_online_playback_request = 0
        self.pending_online_playback_generation = 0
        self.pending_online_playback_identity = ""
        self.pending_online_keep_target_on_failure = False
        self.pending_online_track = None
        if (
            pending_generation != self.playback_generation
            or pending_identity != self.current_queue_identity
        ):
            self.cancel_pending_online_metadata()
            return
        if not isinstance(track, dict) or str(track.get("sourceId") or "") != source_id:
            self.cancel_pending_online_metadata()
            self.pending_online_keep_target_on_failure = keep_target_on_failure
            self.finish_online_playback_failure()
            return
        stable_id = str(track.get("remoteStableId") or "")
        if stable_id:
            self.refresh_remote_song_item(stable_id, resolving=False)
        if resolution.get("headers"):
            self.cancel_pending_online_metadata()
            self.pending_online_keep_target_on_failure = keep_target_on_failure
            self.finish_online_playback_failure()
            self.set_online_status_message(
                "该音源需要附加请求头，当前播放模式暂不支持。"
            )
            return

        url = QUrl(str(resolution.get("url") or ""))
        if not url.isValid() or url.scheme().lower() not in {"http", "https"}:
            self.cancel_pending_online_metadata()
            self.pending_online_keep_target_on_failure = keep_target_on_failure
            self.finish_online_playback_failure()
            self.set_online_status_message("音源返回了无效的播放地址。")
            return

        self.flush_current_listen_time()
        media_item = (
            pending_media_item
            if isinstance(pending_media_item, MediaItem)
            else MediaItem.from_online(track)
        ).with_resolution(resolution)
        self.pending_online_media_item = None
        self.pending_online_ui_snapshot = None
        self.pending_online_keep_target_on_failure = False
        self.current_track_kind = "online"
        self.current_media_item = media_item
        self.current_online_track = media_item.to_legacy_online()
        self.pending_lazy_restore_song_data = None
        self.current_song_path = None
        self.invalidate_media_worker_request("cover")
        self.invalidate_media_worker_request("lyrics")
        self.current_queue_identity = pending_identity or media_item.stable_identity
        self.current_duration = 0
        self.pending_restore_position = 0
        self.reset_playback_stats_session()
        self.current_lyrics = []
        self.current_plain_lyrics = ""
        self.current_online_lyrics_state = "loading"
        self.displayed_lyrics_track_key = ""
        self.displayed_lyrics_song_path = None
        self.refresh_playing_song_indicators()
        self.present_online_media_item(media_item)
        self.lyrics_view.set_placeholder("正在加载歌词", "优先使用歌曲来源，其次联网匹配")
        self.online_lyrics_service.request_lyrics(media_item)

        self.set_online_status_message("正在加载在线歌曲…")
        self.media_loading_generation = pending_generation
        self.media_player.stop()
        self.media_player.setSource(url)
        self.progress_slider.setValue(0)
        self.media_player.play()

    def request_online_download(self, track: dict) -> None:
        if not isinstance(track, dict):
            return
        media_item = MediaItem.from_mapping(track)
        track = media_item.to_legacy_online()
        if self.online_download_manager.is_active():
            self.set_online_status_message("已有在线下载正在进行，请等待完成。")
            return
        source_id = media_item.source_id
        if not source_id:
            self.set_online_status_message("下载请求缺少音源标识。")
            return
        previous_request = int(getattr(self, "pending_online_download_request", 0) or 0)
        if previous_request:
            previous_track = getattr(self, "pending_online_download_track", None)
            if (
                isinstance(previous_track, dict)
                and RemoteTrackStore.stable_id_for_track(previous_track)
                == RemoteTrackStore.stable_id_for_track(track)
            ):
                self.set_online_status_message("这首歌曲的下载地址正在解析，请勿重复操作。")
                return
            self.online_source_client.cancel_request(previous_request)
        self.pending_online_download_track = dict(track)
        self.pending_online_download_request = self.online_source_client.resolve_download(
            source_id,
            track,
        )

    def on_online_download_resolved(
        self,
        request_id: int,
        source_id: str,
        resolution: dict,
    ) -> None:
        if request_id != self.pending_online_download_request:
            return
        track = self.pending_online_download_track
        self.pending_online_download_request = 0
        self.pending_online_download_track = None
        if not isinstance(track, dict) or str(track.get("sourceId") or "") != source_id:
            return
        try:
            stable_id, _record = self.persist_remote_track(track)
        except RemoteTrackStoreError as error:
            QMessageBox.warning(self, "准备下载失败", str(error))
            return
        suggested = self.online_download_manager.suggest_filename(
            resolution,
            str(track.get("title") or "online_track"),
        )
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存在线音乐",
            suggested or "online_track",
            "音频文件 (*.mp3 *.flac *.wav *.m4a *.ogg *.opus *.aac);;所有文件 (*.*)",
        )
        if not target_path:
            self.set_online_status_message("已取消下载。")
            return
        if self.online_download_manager.start_download(resolution, target_path):
            self.active_online_download_track = dict(track)
            self.active_online_download_remote_id = stable_id

    def on_online_source_request_failed(self, request_id: int, action: str, message: str) -> None:
        if action == "resolvePlayback" and request_id == self.pending_online_playback_request:
            track = self.pending_online_track
            self.pending_online_playback_request = 0
            self.pending_online_playback_generation = 0
            self.pending_online_playback_identity = ""
            self.pending_online_track = None
            self.media_loading_generation = 0
            self.cancel_pending_online_metadata()
            self.finish_online_playback_failure()
            self.set_online_status_message(f"获取播放地址失败：{message}")
            stable_id = (
                str(track.get("remoteStableId") or "")
                if isinstance(track, dict)
                else ""
            )
            if stable_id:
                self.refresh_remote_song_item(stable_id, resolving=False)
        elif action == "getMetadata" and request_id == self.pending_online_metadata_request:
            self.pending_online_metadata_request = 0
            self.pending_online_metadata_identity = ""
        elif action == "resolveDownload" and request_id == self.pending_online_download_request:
            self.pending_online_download_request = 0
            self.pending_online_download_track = None
            self.set_online_status_message(f"获取下载地址失败：{message}")

    def on_online_download_progress(self, received: int, total: int) -> None:
        if total > 0:
            percent = min(100, max(0, int(received * 100 / total)))
            self.set_online_status_message(f"正在下载… {percent}%")
        else:
            self.set_online_status_message(
                f"正在下载… {received / (1024 * 1024):.1f} MB"
            )

    def on_online_download_finished(self, target_path: str) -> None:
        stable_id = self.active_online_download_remote_id
        self.active_online_download_remote_id = ""
        self.active_online_download_track = None
        record = self.remote_tracks.get(stable_id)
        if not isinstance(record, dict):
            self.set_online_status_message(f"下载完成：{target_path}")
            return
        updated_record = dict(record)
        updated_record["local_path"] = str(Path(target_path).resolve())
        updated_record["downloaded_at"] = int(time.time())
        updated_tracks = dict(self.remote_tracks)
        updated_tracks[stable_id] = updated_record
        try:
            self.remote_track_store.save_tracks(updated_tracks)
        except RemoteTrackStoreError as error:
            self.set_online_status_message(f"文件已下载，但保存关联失败：{error}")
            return
        self.remote_tracks = updated_tracks
        self.invalidate_local_song_match_index()
        self.add_music_paths([Path(target_path)])
        local_song = self.find_song_data_by_path(target_path)
        self.sync_remote_song_items()
        self.refresh_unified_search_result_states()
        if isinstance(local_song, dict) and local_song.get("recordKind") != "remote":
            self.set_online_status_message(
                f"下载完成并已关联本地音乐库：{target_path}"
            )
        else:
            self.set_online_status_message(
                f"下载完成，但文件扩展名未被本地音乐库识别：{target_path}"
            )

    def on_online_download_failed(self, message: str) -> None:
        self.active_online_download_remote_id = ""
        self.active_online_download_track = None
        self.set_online_status_message(message)

    def show_online_search_page(self) -> None:
        self.show_search_page()
        if hasattr(self, "search_page"):
            self.search_page.show_tab("online")

    def show_custom_source_manager_page(self) -> None:
        self.set_sidebar_active("custom_sources")
        page = getattr(self, "custom_source_manager_page", None)
        if hasattr(self, "content_stack") and page is not None:
            self.content_stack.setCurrentWidget(page)
            page.refresh_sources()
        self.set_right_panel_mode("info")

    def on_custom_sources_changed(self, source_id: str) -> None:
        self.invalidate_registered_source_snapshot()
        service = getattr(self, "unified_search_service", None)
        if service is not None:
            service.invalidate_source(str(source_id or ""))
        self.sync_remote_song_items()
        self.refresh_unified_search_result_states(str(source_id or ""))

    def find_song_data_by_path(self, song_path: str | None) -> dict | None:
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path:
            return None

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            item_path = self.normalize_song_path(song_data.get("path", ""))

            if item_path == normalized_path:
                return song_data

        return None

    def refresh_full_lyrics_page(self) -> None:
        if not hasattr(self, "full_lyrics_view"):
            return

        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            self.full_lyrics_title.setText(current.title)
            self.full_lyrics_artist.setText(
                f"{current.artist} · {current.album} · {current.source_name} · 在线"
            )
            if self.displayed_lyrics_track_key == current.stable_identity:
                self.sync_full_lyrics_from_current()
            else:
                self.full_lyrics_status.setText("正在加载在线歌词")
                self.full_lyrics_view.set_placeholder(
                    "正在加载歌词", "优先使用缓存，其次请求当前歌曲来源"
                )
            return

        playing_path = self.normalize_song_path(self.current_song_path)

        if not playing_path:
            self.full_lyrics_title.setText("还没有播放音乐")
            self.full_lyrics_artist.setText("双击歌曲或右键播放后，这里会显示正在播放的歌词")
            self.full_lyrics_status.setText("等待播放歌曲")
            self.full_lyrics_view.set_placeholder(
                "还没有正在播放的歌词",
                "双击一首歌播放，然后点击左侧“歌词”查看大歌词页面",
            )
            return

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
        else:
            title = Path(playing_path).stem
            artist = "未知艺术家"
            album = "未知专辑"

        self.full_lyrics_title.setText(title)
        self.full_lyrics_artist.setText(f"{artist} · {album}")

        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if displayed_path == playing_path and self.current_lyrics:
            self.sync_full_lyrics_from_current()
            return

        self.full_lyrics_status.setText("正在加载正在播放歌曲的歌词")
        self.full_lyrics_view.set_placeholder(
            "正在加载歌词",
            "优先手动绑定歌词、本地歌词，其次缓存和联网歌词",
        )

        self.load_lyrics_for_song(
            file_path=playing_path,
            title=title,
            artist=artist,
        )

    def sync_full_lyrics_from_current(self) -> None:
        if not hasattr(self, "full_lyrics_view"):
            return

        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            if self.displayed_lyrics_track_key != current.stable_identity:
                return
            self.full_lyrics_title.setText(current.title)
            self.full_lyrics_artist.setText(
                f"{current.artist} · {current.album} · {current.source_name} · 在线"
            )
            if self.current_plain_lyrics:
                self.full_lyrics_view.set_plain_text(self.current_plain_lyrics)
            elif self.current_lyrics:
                self.full_lyrics_view.set_lyrics(self.current_lyrics)
                self.full_lyrics_view.update_by_position(
                    self.media_player.position(), self.current_lyrics
                )
            else:
                state = getattr(self, "current_online_lyrics_state", "")
                if state == "error":
                    self.full_lyrics_view.set_placeholder(
                        "歌词获取失败", "播放不受影响，可以稍后重新播放重试"
                    )
                elif state == "loading":
                    self.full_lyrics_view.set_placeholder(
                        "正在获取歌词", "优先使用缓存，其次请求当前歌曲来源"
                    )
                else:
                    self.full_lyrics_view.set_placeholder("暂无歌词", "歌曲来源没有提供歌词")
            if hasattr(self, "lyrics_status_label"):
                self.full_lyrics_status.setText(
                    self.lyrics_status_label.text().replace("歌词：", "").strip()
                )
            return

        playing_path = self.normalize_song_path(self.current_song_path)
        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if not playing_path:
            return

        if displayed_path != playing_path:
            return

        song_data = self.find_song_data_by_path(playing_path)

        if song_data:
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
            self.full_lyrics_title.setText(title)
            self.full_lyrics_artist.setText(f"{artist} · {album}")

        if self.current_lyrics:
            self.full_lyrics_view.set_lyrics(self.current_lyrics)
            self.full_lyrics_view.update_by_position(
                self.media_player.position(),
                self.current_lyrics,
            )
            self.full_lyrics_status.setText("正在显示播放中的歌词")
            self.sync_immersive_lyrics()
        else:
            self.full_lyrics_view.set_placeholder(
                "当前歌曲暂无歌词",
                "可以右键歌曲手动绑定歌词，或者重新搜索歌词",
            )
            self.full_lyrics_status.setText("当前歌曲暂无歌词")
            self.sync_immersive_lyrics()

    def _create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        outer_layout = QVBoxLayout(sidebar)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        scroll = QScrollArea(sidebar)
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content = QWidget()
        content.setObjectName("sidebarContent")
        self.sidebar_scroll = scroll
        self.sidebar_content = content

        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)

        title = QLabel("HushPlayer")
        title.setObjectName("appTitle")
        self.sidebar_title = title

        subtitle = QLabel("安静地听本地音乐")
        subtitle.setObjectName("appSubtitle")
        self.sidebar_subtitle = subtitle

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.search_input = SearchEntryLineEdit()
        self.search_input.setObjectName("sidebarSearchInput")
        self.search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.search_input.setPlaceholderText("搜索音乐")
        self.search_input.setStyleSheet(
            "QLineEdit#sidebarSearchInput { background: #151922; color: #f3f4f6; border: 1px solid #2a303b; "
            "border-radius: 11px; padding: 9px 11px; selection-background-color: #4c8dff; }"
            "QLineEdit#sidebarSearchInput:focus { border-color: #4c8dff; background: #1a1f2b; }"
        )
        self.search_input.focused.connect(self.show_search_page)
        self.search_input.textChanged.connect(self.request_search_filter)
        layout.addWidget(self.search_input)

        layout.addSpacing(12)
        library_title = QLabel("音乐库")
        library_title.setObjectName("sidebarSectionTitle")
        layout.addWidget(library_title)

        self.library_nav_button = NavButton("全部歌曲", active=True)
        self.library_nav_button.clicked.connect(
            lambda checked=False: self.show_library_category("all")
        )
        self.recent_nav_button = NavButton("最近播放")
        self.recent_nav_button.clicked.connect(
            lambda checked=False: self.show_library_category("recent_played")
        )
        self.frequent_nav_button = NavButton("常听")
        self.frequent_nav_button.clicked.connect(
            lambda checked=False: self.show_library_category("frequent")
        )
        self.liked_playlist_button = NavButton("我喜欢")
        self.liked_playlist_button.clicked.connect(self.show_liked_playlist_page)
        self.recent_added_nav_button = NavButton("最近添加")
        self.recent_added_nav_button.clicked.connect(
            lambda checked=False: self.show_library_category("recent_added")
        )
        self.view_buttons.update(
            {
                "all": self.library_nav_button,
                "recent_played": self.recent_nav_button,
                "frequent": self.frequent_nav_button,
                "liked": self.liked_playlist_button,
                "recent_added": self.recent_added_nav_button,
            }
        )
        layout.addWidget(self.library_nav_button)
        layout.addWidget(self.recent_nav_button)
        layout.addWidget(self.frequent_nav_button)
        layout.addWidget(self.liked_playlist_button)
        layout.addWidget(self.recent_added_nav_button)

        layout.addSpacing(12)
        nav_title = QLabel("浏览")
        nav_title.setObjectName("sidebarSectionTitle")
        layout.addWidget(nav_title)

        self.search_nav_button = NavButton("搜索")
        self.search_nav_button.clicked.connect(self.show_search_page)

        self.playlist_nav_button = NavButton("播放列表")
        self.playlist_nav_button.clicked.connect(self.show_play_queue)

        self.lyrics_nav_button = NavButton("歌词")
        self.lyrics_nav_button.clicked.connect(self.show_full_lyrics_page)

        self.pending_nav_button = NavButton("待导入")
        self.pending_nav_button.clicked.connect(self.show_pending_imports_page)

        self.custom_sources_nav_button = NavButton("自定义来源")
        self.custom_sources_nav_button.clicked.connect(
            self.show_custom_source_manager_page
        )

        self.settings_nav_button = NavButton("设置")
        self.settings_nav_button.clicked.connect(self.open_settings_dialog)

        layout.addWidget(self.search_nav_button)
        layout.addWidget(self.playlist_nav_button)
        layout.addWidget(self.lyrics_nav_button)
        layout.addWidget(self.pending_nav_button)
        layout.addWidget(self.custom_sources_nav_button)

        layout.addSpacing(12)

        playlist_title = QLabel("歌单")
        playlist_title.setObjectName("sidebarSectionTitle")
        layout.addWidget(playlist_title)

        self.sidebar_playlist_box = QFrame()
        self.sidebar_playlist_box.setObjectName("sidebarPlaylistBox")

        self.sidebar_playlist_layout = QVBoxLayout(self.sidebar_playlist_box)
        self.sidebar_playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_playlist_layout.setSpacing(7)

        layout.addWidget(self.sidebar_playlist_box)

        self.refresh_playlist_view_buttons()

        layout.addSpacing(8)

        new_playlist_btn = QPushButton("+ 新建歌单")
        new_playlist_btn.setObjectName("sidebarWideButton")
        new_playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_playlist_btn.setMinimumHeight(new_playlist_btn.fontMetrics().height() + 16)
        new_playlist_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        new_playlist_btn.clicked.connect(self.create_new_playlist)
        self.new_playlist_button = new_playlist_btn

        layout.addWidget(new_playlist_btn)

        self.sidebar_playlist_hint_default = "右键歌单进行管理 · 右键歌曲可添加到歌单"
        help_text = QLabel(self.sidebar_playlist_hint_default)
        help_text.setObjectName("sidebarHint")
        help_text.setWordWrap(True)
        self.sidebar_playlist_hint = help_text
        layout.addWidget(help_text)

        layout.addStretch()
        layout.addWidget(self.settings_nav_button)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        return sidebar

    def _create_library_panel(self) -> QFrame:
        page = LibraryPage(self)
        self.library_page = page
        self.song_list = page.track_view.list_widget
        # Sorting is managed explicitly so batch inserts never trigger Qt's
        # per-row automatic sort or change the playlist relationship order.
        self.song_list.setSortingEnabled(False)
        self.song_list.setItemDelegate(SongLibraryDelegate(self, self.song_list))
        self.song_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.song_list.customContextMenuRequested.connect(self.show_song_context_menu)
        self.song_list.itemClicked.connect(self.select_song)
        self.song_list.itemDoubleClicked.connect(self.play_selected_song)
        self.song_list.verticalScrollBar().valueChanged.connect(
            self.schedule_visible_library_durations
        )
        self.song_table_header = page.track_view.header
        self.song_list_empty_hint = page.track_view.empty_label
        self.library_sort_headers = page.track_view.sort_buttons
        page.track_view.sortRequested.connect(self.sort_library_by_column)
        page.importFilesRequested.connect(self.import_music_files)
        page.importFolderRequested.connect(self.import_music_folder)
        page.randomPlayRequested.connect(self.play_random_library_song)
        page.removeSelectedRequested.connect(self.remove_selected_song)
        page.cleanMissingRequested.connect(self.clean_missing_songs)
        page.trackBrowsed.connect(self.browse_media_item)
        page.trackPlayRequested.connect(self.play_media_item)
        page.trackContextRequested.connect(self.media_interactions.show_context_menu)
        page.viewChanged.connect(self.on_library_content_view_changed)
        page.set_playing_key_provider(self.current_media_key)
        self.update_library_sort_headers()
        return page
    def _create_pending_imports_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("pendingImportsPage")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(6)

        title = QLabel("待导入音乐")
        title.setObjectName("pageTitle")

        self.pending_imports_hint = QLabel("扫描到的新音乐会先出现在这里，确认后再加入正式音乐库。")
        self.pending_imports_hint.setObjectName("pageSubtitle")
        self.pending_imports_hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(self.pending_imports_hint)

        back_btn = QPushButton("返回音乐库")
        back_btn.setObjectName("secondaryButton")
        back_btn.clicked.connect(self.show_library_page)

        header.addLayout(title_box, 1)
        header.addWidget(back_btn)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        select_all_btn = QPushButton("全选")
        select_all_btn.setObjectName("secondaryButton")
        select_all_btn.clicked.connect(lambda: self.set_all_pending_checked(True))

        invert_btn = QPushButton("反选")
        invert_btn.setObjectName("secondaryButton")
        invert_btn.clicked.connect(self.invert_pending_selection)

        select_artist_btn = QPushButton("只选当前歌手")
        select_artist_btn.setObjectName("secondaryButton")
        select_artist_btn.clicked.connect(lambda: self.select_pending_by_field("artist"))

        select_album_btn = QPushButton("只选当前专辑")
        select_album_btn.setObjectName("secondaryButton")
        select_album_btn.clicked.connect(lambda: self.select_pending_by_field("album"))

        preview_btn = QPushButton("试听")
        preview_btn.setObjectName("secondaryButton")
        preview_btn.clicked.connect(lambda: self.preview_pending_import())

        import_btn = QPushButton("加入选中")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(lambda: self.import_pending_songs())

        ignore_btn = QPushButton("忽略选中")
        ignore_btn.setObjectName("dangerButton")
        ignore_btn.clicked.connect(lambda: self.ignore_pending_imports())

        open_folder_btn = QPushButton("打开文件夹")
        open_folder_btn.setObjectName("secondaryButton")
        open_folder_btn.clicked.connect(self.open_pending_import_folder)

        for button in (
            select_all_btn,
            invert_btn,
            select_artist_btn,
            select_album_btn,
            preview_btn,
            import_btn,
            ignore_btn,
            open_folder_btn,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            action_row.addWidget(button)

        action_row.addStretch(1)

        self.pending_empty_hint = QLabel("还没有待导入音乐。可以在设置页添加音乐文件夹，然后点击重新扫描。")
        self.pending_empty_hint.setObjectName("pendingEmptyHint")
        self.pending_empty_hint.setWordWrap(True)
        self.pending_empty_hint.setVisible(False)
        self.pending_imports_list = QListWidget()
        self.pending_imports_list.setObjectName("pendingImportsList")
        self.pending_imports_list.setWordWrap(True)
        self.pending_imports_list.setUniformItemSizes(False)
        self.pending_imports_list.itemDoubleClicked.connect(self.preview_pending_import)

        layout.addLayout(header)
        layout.addLayout(action_row)
        layout.addWidget(self.pending_empty_hint)
        layout.addWidget(self.pending_imports_list, 1)
        return page
    def _create_now_playing_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("nowPlayingPanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(340)
        panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 24, 22, 22)
        layout.setSpacing(14)

        title = QLabel("正在播放")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.now_playing_title = title

        self.cover_label = RoundedCoverLabel("Hush")
        self.cover_label.setObjectName("coverLabel")
        self.cover_label.setFixedSize(236, 236)

        now_info_box = QFrame()
        now_info_box.setObjectName("nowInfoBox")
        now_info_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.now_info_box = now_info_box

        now_info_layout = QVBoxLayout(now_info_box)
        now_info_layout.setContentsMargins(16, 14, 16, 14)
        now_info_layout.setSpacing(8)

        self.now_song_title = MultiLineElidedLabel("还没有播放音乐", max_lines=2)
        self.now_song_title.setObjectName("nowSongTitle")
        self.now_song_title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.now_artist = MultiLineElidedLabel("导入歌曲后开始播放", max_lines=2)
        self.now_artist.setObjectName("nowArtist")
        self.now_artist.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.now_stats = QLabel("播放 0 次 · 累计 0:00")
        self.now_stats.setObjectName("nowStats")
        self.now_stats.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.now_stats.setWordWrap(True)
        self.now_stats.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.now_stats.hide()

        self.lyrics_status_label = QLabel("歌词：等待选择歌曲")
        self.lyrics_status_label.setObjectName("lyricsStatus")
        self.lyrics_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lyrics_status_label.setWordWrap(True)
        self.lyrics_status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lyrics_status_label.hide()

        self.now_open_folder_btn = QPushButton("打开文件位置")
        self.now_open_folder_btn.setObjectName("nowPlayingActionButton")
        self.now_open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.now_open_folder_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.now_open_folder_btn.setIconSize(QSize(16, 16))
        self.now_open_folder_btn.setEnabled(False)
        self.now_open_folder_btn.clicked.connect(self.open_current_song_folder)
        now_info_layout.addWidget(self.now_song_title)
        now_info_layout.addWidget(self.now_artist)
        now_info_layout.addWidget(self.now_stats)
        now_info_layout.addWidget(self.lyrics_status_label)
        now_info_layout.addWidget(self.now_open_folder_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.lyrics_view = LyricsView()

        self.side_info_panel = QFrame()
        self.side_info_panel.setObjectName("sideInfoPanel")
        self.side_info_panel.hide()

        side_info_layout = QVBoxLayout(self.side_info_panel)
        side_info_layout.setContentsMargins(4, 8, 4, 8)
        side_info_layout.setSpacing(10)

        side_info_title = QLabel("歌曲信息")
        side_info_title.setObjectName("sideInfoTitle")

        side_info_hint = QLabel("当前播放歌曲的详细信息")
        side_info_hint.setObjectName("sideInfoHint")
        side_info_hint.setWordWrap(True)

        self.side_artist_detail = MultiLineElidedLabel("未知艺术家", max_lines=2)
        self.side_album_detail = MultiLineElidedLabel("未知专辑", max_lines=2)
        self.side_like_detail = QLabel("未收藏")
        self.side_play_count_detail = QLabel("0 次")
        self.side_listen_time_detail = QLabel("0:00")
        self.side_last_played_detail = QLabel("还没有播放记录")
        self.side_lyrics_status_value = QLabel("等待选择歌曲")
        self.side_file_detail = QLabel("")
        self.side_file_detail.setWordWrap(True)

        side_info_layout.addWidget(side_info_title)
        side_info_layout.addWidget(side_info_hint)
        side_info_layout.addSpacing(4)
        side_info_layout.addWidget(self._create_side_info_row("歌手", self.side_artist_detail))
        side_info_layout.addWidget(self._create_side_info_row("专辑", self.side_album_detail))
        side_info_layout.addWidget(self._create_side_info_row("收藏", self.side_like_detail))
        side_info_layout.addWidget(self._create_side_info_row("播放次数", self.side_play_count_detail))
        side_info_layout.addWidget(self._create_side_info_row("累计时长", self.side_listen_time_detail))
        side_info_layout.addWidget(self._create_side_info_row("最近播放", self.side_last_played_detail))
        side_info_layout.addWidget(self._create_side_info_row("歌词状态", self.side_lyrics_status_value))

        file_box = QFrame()
        file_box.setObjectName("sideInfoRow")
        file_layout = QVBoxLayout(file_box)
        file_layout.setContentsMargins(12, 10, 12, 10)
        file_layout.setSpacing(6)

        file_label = QLabel("文件路径")
        file_label.setObjectName("sideInfoName")

        self.side_file_detail.setObjectName("sideInfoFileValue")

        file_layout.addWidget(file_label)
        file_layout.addWidget(self.side_file_detail)

        side_info_layout.addWidget(file_box)
        file_box.hide()
        side_info_layout.addStretch()

        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(now_info_box)
        layout.addSpacing(6)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.side_info_panel, 1)

        return panel

    def _create_player_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("playerBar")
        bar.setMinimumHeight(124)

        layout = QHBoxLayout(bar)
        self.player_bar_layout = layout
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(20)

        left_box = QFrame()
        left_box.setObjectName("playerLeft")
        left_box.setMinimumWidth(0)
        left_box.setMaximumWidth(280)
        left_box.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self.player_left_box = left_box

        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        self.bottom_song_title = ElidedLabel("未播放")
        self.bottom_song_title.setObjectName("bottomSongTitle")
        self.bottom_song_title.setMinimumWidth(0)
        self.bottom_song_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.bottom_song_artist = ElidedLabel("请选择一首音乐")
        self.bottom_song_artist.setObjectName("bottomSongArtist")
        self.bottom_song_artist.setMinimumWidth(0)
        self.bottom_song_artist.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.bottom_source_badge = QLabel("")
        self.bottom_source_badge.setObjectName("bottomSourceBadge")
        self.bottom_source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bottom_source_badge.setMaximumWidth(128)
        self.bottom_source_badge.setStyleSheet(
            "QLabel#bottomSourceBadge { background: rgba(76,141,255,0.18); color: #9fc1ff; "
            "border: 1px solid rgba(76,141,255,0.38); border-radius: 8px; padding: 2px 7px; "
            "font-size: 11px; font-weight: 700; }"
        )
        self.bottom_source_badge.hide()

        left_layout.addStretch()
        left_layout.addWidget(self.bottom_song_title)
        left_layout.addWidget(self.bottom_song_artist)
        left_layout.addWidget(self.bottom_source_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        left_layout.addStretch()

        center_box = QFrame()
        center_box.setObjectName("playerCenter")
        center_box.setMinimumWidth(260)
        center_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.player_center_box = center_box

        center_layout = QVBoxLayout(center_box)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        self.prev_btn = PlayerIconButton("previous")
        self.play_btn = PlayerIconButton("play")
        self.next_btn = PlayerIconButton("next")

        self.prev_btn.setFixedSize(42, 42)
        self.play_btn.setFixedSize(50, 50)
        self.next_btn.setFixedSize(42, 42)

        self.prev_btn.setObjectName("transportButton")
        self.play_btn.setObjectName("transportPlayButton")
        self.next_btn.setObjectName("transportButton")

        self.prev_btn.setToolTip("上一首  Ctrl+←")
        self.play_btn.setToolTip("播放  Ctrl+Space")
        self.next_btn.setToolTip("下一首  Ctrl+→")

        self.prev_btn.clicked.connect(self.play_previous_song)
        self.play_btn.clicked.connect(self.toggle_play)
        self.next_btn.clicked.connect(self.play_next_song)

        controls_layout.addStretch()
        controls_layout.addWidget(self.prev_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addStretch()

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("progressSlider")
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(0)
        self.progress_slider.setMinimumWidth(120)
        self.progress_slider.setMinimumHeight(32)
        self.progress_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.progress_slider.sliderPressed.connect(self.on_seek_start)
        self.progress_slider.sliderReleased.connect(self.on_seek_end)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)

        self.current_time_label = QLabel("0:00")
        self.current_time_label.setObjectName("playerTimeLabel")
        self.current_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.current_time_label.setFixedWidth(42)

        self.total_time_label = QLabel("0:00")
        self.total_time_label.setObjectName("playerTimeLabel")
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.total_time_label.setFixedWidth(42)

        progress_row.addWidget(self.current_time_label)
        progress_row.addWidget(self.progress_slider, 1)
        progress_row.addWidget(self.total_time_label)

        center_layout.addStretch()
        center_layout.addLayout(controls_layout)
        center_layout.addLayout(progress_row)
        center_layout.addStretch()

        right_box = QFrame()
        right_box.setObjectName("playerRight")
        right_box.setMinimumWidth(190)
        right_box.setMaximumWidth(320)
        right_box.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self.player_right_box = right_box

        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(9)

        self.like_btn = QPushButton("♡ 收藏")
        self.like_btn.setObjectName("likeButton")
        self.like_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.like_btn.setMinimumWidth(72)
        self.like_btn.setMaximumWidth(96)
        self.like_btn.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.like_btn.clicked.connect(self.toggle_like_current_song)

        self.play_mode_btn = QPushButton("列表循环")
        self.play_mode_btn.setObjectName("controlButton")
        self.play_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_mode_btn.setMinimumWidth(76)
        self.play_mode_btn.setMaximumWidth(96)
        self.play_mode_btn.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.play_mode_btn.clicked.connect(self.toggle_play_mode)

        self.floating_lyrics_button = QPushButton("桌面歌词")
        self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
        self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.floating_lyrics_button.setMinimumHeight(34)
        self.floating_lyrics_button.setMinimumWidth(80)
        self.floating_lyrics_button.setMaximumWidth(96)
        self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)

        self.player_more_button = QPushButton("⋯")
        self.player_more_button.setObjectName("controlButton")
        self.player_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.player_more_button.setFixedSize(36, 34)
        self.player_more_button.setToolTip("更多播放操作")
        player_more_menu = QMenu(self.player_more_button)
        current_info_action = player_more_menu.addAction("查看当前歌曲信息")
        current_info_action.triggered.connect(
            lambda checked=False: self.show_current_playing_info()
        )
        floating_action = player_more_menu.addAction("打开或关闭桌面歌词")
        floating_action.triggered.connect(
            lambda checked=False: self.toggle_floating_lyrics()
        )
        self.player_more_button.setMenu(player_more_menu)
        self.player_more_button.hide()

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addWidget(self.like_btn)
        top_row.addWidget(self.play_mode_btn)
        top_row.addWidget(self.floating_lyrics_button)
        top_row.addWidget(self.player_more_button)
        top_row.addStretch()

        volume_row = QHBoxLayout()
        volume_row.setContentsMargins(0, 0, 0, 0)
        volume_row.setSpacing(8)

        self.volume_icon_label = VolumeStatusIcon()
        self.volume_icon_label.setObjectName("volumeIconLabel")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.current_volume)
        self.volume_slider.setMinimumWidth(70)
        self.volume_slider.setMaximumWidth(178)
        self.volume_slider.setMinimumHeight(32)
        self.volume_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.valueChanged.connect(self.update_volume_status)

        self.volume_value_label = QLabel()
        self.volume_value_label.setObjectName("volumeStateLabel")
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_value_label.setFixedWidth(38)

        volume_row.addWidget(self.volume_icon_label)
        volume_row.addWidget(self.volume_slider)
        volume_row.addWidget(self.volume_value_label)
        volume_row.addStretch()

        right_layout.addStretch()
        right_layout.addLayout(top_row)
        right_layout.addLayout(volume_row)
        right_layout.addStretch()

        layout.addWidget(left_box, 1)
        layout.addWidget(center_box, 3)
        layout.addWidget(right_box, 1)

        self.media_player.positionChanged.connect(self.update_current_time_display)
        self.media_player.durationChanged.connect(self.update_total_time_display)
        self.update_volume_status(self.current_volume)

        return bar

    @staticmethod
    def format_player_time(milliseconds: int) -> str:
        total_seconds = max(0, int(milliseconds or 0) // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return f"{minutes}:{seconds:02d}"

    def update_current_time_display(self, position: int) -> None:
        if hasattr(self, "current_time_label"):
            self.current_time_label.setText(self.format_player_time(position))

    def update_total_time_display(self, duration: int) -> None:
        if hasattr(self, "total_time_label"):
            self.total_time_label.setText(self.format_player_time(duration))

    def update_volume_status(self, value: int) -> None:
        volume = max(0, min(100, int(value)))

        if hasattr(self, "volume_value_label"):
            self.volume_value_label.setText(f"{volume}%")

        if hasattr(self, "volume_icon_label"):
            self.volume_icon_label.set_muted(volume == 0)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        paths_to_import: list[Path] = []

        for url in event.mimeData().urls():
            local_path = url.toLocalFile()

            if not local_path:
                continue

            path = Path(local_path)

            if path.is_dir():
                scanned_paths = self.scan_music_folder(path)
                paths_to_import.extend(scanned_paths)
                print(f"拖拽导入文件夹：{path}")
                print(f"扫描到音乐文件数量：{len(scanned_paths)}")
            elif path.is_file():
                paths_to_import.append(path)
                print(f"拖拽导入文件：{path}")

        if paths_to_import:
            self.add_music_paths(paths_to_import)

        event.acceptProposedAction()

    def request_search_filter(self, *_args) -> None:
        keyword = self.search_input.text().strip()
        local_only = bool(
            getattr(self, "search_page", None)
            and self.search_page.local_only_checkbox.isChecked()
        )
        service = getattr(self, "unified_search_service", None)
        if service is not None:
            service.schedule_search(keyword, local_only=local_only)
        if keyword:
            self.show_search_page()
        else:
            self.cancel_pending_local_search()
            if hasattr(self, "search_page"):
                self.search_page.set_local_results("", [])
            self.last_applied_local_search_key = ""
            self.last_applied_local_search_revision = int(
                getattr(self, "library_data_revision", 0)
            )
            self.unified_search_results = []
            self.unified_search_results_by_source = {}
            self.unified_search_summary = {}
            self.unified_search_generation = 0
            self.unified_search_keyword = ""
            self._unified_search_source_order = []
            self._unified_search_source_sizes = {}
            if hasattr(self, "search_page"):
                self.search_page.clear_online_results()
            if (
                hasattr(self, "content_stack")
                and hasattr(self, "search_page")
                and self.content_stack.currentWidget() is self.search_page
            ):
                self.return_to_library_view()

    def apply_search_filter(self) -> None:
        generation = int(getattr(self, "pending_local_search_generation", 0))
        keyword = str(getattr(self, "pending_local_search_keyword", "") or "")
        search_key = str(getattr(self, "pending_local_search_key", "") or "")
        revision = int(getattr(self, "pending_local_search_revision", -1))
        current_key = self.normalize_local_search_keyword(self.search_input.text())
        current_revision = int(getattr(self, "library_data_revision", 0))
        on_search_page = bool(
            hasattr(self, "content_stack")
            and hasattr(self, "search_page")
            and self.content_stack.currentWidget() is self.search_page
        )
        if (
            generation <= 0
            or generation != int(getattr(self, "local_search_generation", 0))
            or search_key != current_key
            or revision != current_revision
            or not on_search_page
        ):
            if generation == getattr(self, "pending_local_search_generation", 0):
                self.clear_pending_local_search()
            if on_search_page and current_key:
                self.schedule_local_search_if_needed()
            return

        local_results = self.collect_local_search_results(keyword)
        if (
            generation != int(getattr(self, "local_search_generation", 0))
            or search_key != self.normalize_local_search_keyword(self.search_input.text())
            or revision != int(getattr(self, "library_data_revision", 0))
        ):
            return
        if hasattr(self, "search_page"):
            self.search_page.set_local_results(keyword, local_results)
        self.last_applied_local_search_key = search_key
        self.last_applied_local_search_revision = revision
        self.clear_pending_local_search()

    @staticmethod
    def normalize_local_search_keyword(keyword: str) -> str:
        return " ".join(str(keyword or "").casefold().split())

    def schedule_local_search_if_needed(self) -> bool:
        keyword = self.search_input.text().strip()
        search_key = self.normalize_local_search_keyword(keyword)
        revision = int(getattr(self, "library_data_revision", 0))
        if (
            not search_key
            or not hasattr(self, "content_stack")
            or not hasattr(self, "search_page")
            or self.content_stack.currentWidget() is not self.search_page
        ):
            return False
        if (
            search_key == getattr(self, "last_applied_local_search_key", None)
            and revision
            == int(getattr(self, "last_applied_local_search_revision", -1))
        ):
            return False
        if (
            self.search_debounce_timer.isActive()
            and search_key == getattr(self, "pending_local_search_key", "")
            and revision == int(getattr(self, "pending_local_search_revision", -1))
        ):
            return False
        self.local_search_generation = int(
            getattr(self, "local_search_generation", 0)
        ) + 1
        self.pending_local_search_generation = self.local_search_generation
        self.pending_local_search_keyword = keyword
        self.pending_local_search_key = search_key
        self.pending_local_search_revision = revision
        self.search_debounce_timer.start()
        return True

    def clear_pending_local_search(self) -> None:
        self.pending_local_search_generation = 0
        self.pending_local_search_keyword = ""
        self.pending_local_search_key = ""
        self.pending_local_search_revision = -1

    def cancel_pending_local_search(self) -> None:
        self.search_debounce_timer.stop()
        self.local_search_generation = int(
            getattr(self, "local_search_generation", 0)
        ) + 1
        self.clear_pending_local_search()

    def collect_local_search_results(self, keyword: str) -> list[dict]:
        normalized = self.normalize_local_search_keyword(keyword)
        if not normalized or not hasattr(self, "song_list"):
            return []
        results: list[dict] = []
        seen_paths: set[str] = set()
        for row in range(self.song_list.count()):
            item = self.song_list.item(row)
            song_data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if not isinstance(song_data, dict) or song_data.get("recordKind") == "remote":
                continue
            search_text = " ".join(
                str(song_data.get(field) or "").casefold()
                for field in ("title", "artist", "album")
            )
            if normalized not in " ".join(search_text.split()):
                continue
            media_item = MediaItem.from_local(song_data)
            if media_item.local_file_path in seen_paths:
                continue
            seen_paths.add(media_item.local_file_path)
            results.append(media_item.to_dict())
        return results

    def on_unified_local_only_toggled(self, checked: bool) -> None:
        self.unified_search_local_only = bool(checked)
        self.save_hush_settings({"online_search_local_only": bool(checked)})
        self.request_search_filter()

    def on_unified_search_results_changed(
        self,
        generation: int,
        keyword: str,
        _results: list,
        summary: dict,
    ) -> None:
        current_keyword = self.search_input.text().strip()
        keyword = str(keyword or "").strip()
        service = getattr(self, "unified_search_service", None)
        if (
            current_keyword != keyword
            or (service is not None and int(generation) != service.generation)
        ):
            return
        if not current_keyword:
            self.unified_search_results = []
            self.unified_search_results_by_source = {}
            self.unified_search_summary = {}
            self.unified_search_generation = 0
            self.unified_search_keyword = ""
            self._unified_search_source_order = []
            self._unified_search_source_sizes = {}
            self.search_page.clear_online_results()
            return
        new_request = (
            int(generation) != self.unified_search_generation
            or keyword != self.unified_search_keyword
        )
        if new_request:
            self.unified_search_generation = int(generation)
            self.unified_search_keyword = keyword
            self.unified_search_results = []
            self.unified_search_results_by_source = {}
            self._unified_search_source_order = []
            self._unified_search_source_sizes = {}
        self.unified_search_summary = dict(summary or {})
        self._sync_unified_search_source_order(self.unified_search_summary)
        if new_request:
            self.search_page.begin_online_results(
                current_keyword,
                self.unified_search_summary,
            )
        else:
            self.search_page.update_online_summary(
                current_keyword,
                self.unified_search_summary,
            )

    def on_unified_search_source_results_changed(
        self,
        generation: int,
        keyword: str,
        source_id: str,
        results: list,
        state: dict,
        summary: dict,
    ) -> None:
        keyword = str(keyword or "").strip()
        source_id = str(source_id or "").strip()
        current_keyword = self.search_input.text().strip()
        service = getattr(self, "unified_search_service", None)
        if (
            not source_id
            or current_keyword != keyword
            or int(generation) != self.unified_search_generation
            or keyword != self.unified_search_keyword
            or (service is not None and int(generation) != service.generation)
        ):
            return
        state_source_id = str(
            (state or {}).get("sourceId")
            or (state or {}).get("source_id")
            or source_id
        ).strip()
        if state_source_id != source_id:
            return
        self.unified_search_summary = dict(summary or {})
        self._sync_unified_search_source_order(self.unified_search_summary)
        decorated = [
            self.decorate_unified_search_result(result)
            for result in results
            if isinstance(result, dict)
        ]
        self._replace_unified_search_source_results(source_id, decorated)
        source_name = str(
            (state or {}).get("sourceName")
            or (state or {}).get("source_name")
            or source_id
        )
        self.search_page.update_online_source_results(
            current_keyword,
            source_id,
            source_name,
            decorated,
            dict(state or {}),
            self.unified_search_summary,
        )

    def _sync_unified_search_source_order(self, summary: dict) -> None:
        states = summary.get("sources") if isinstance(summary, dict) else None
        if not isinstance(states, list):
            return
        next_order = [
            str(state.get("sourceId") or state.get("source_id") or "").strip()
            for state in states
            if isinstance(state, dict)
            and str(state.get("sourceId") or state.get("source_id") or "").strip()
        ]
        if next_order == self._unified_search_source_order:
            return
        self._unified_search_source_order = next_order
        if self.unified_search_results_by_source:
            self.unified_search_results = [
                track
                for source_id in next_order
                for track in self.unified_search_results_by_source.get(source_id, [])
            ]
            self._unified_search_source_sizes = {
                source_id: len(self.unified_search_results_by_source.get(source_id, []))
                for source_id in next_order
            }

    def _replace_unified_search_source_results(
        self,
        source_id: str,
        results: list[dict],
    ) -> None:
        if source_id not in self._unified_search_source_order:
            self._unified_search_source_order.append(source_id)
        source_index = self._unified_search_source_order.index(source_id)
        start = sum(
            self._unified_search_source_sizes.get(item, 0)
            for item in self._unified_search_source_order[:source_index]
        )
        previous_size = self._unified_search_source_sizes.get(source_id, 0)
        self.unified_search_results[start:start + previous_size] = results
        self._unified_search_source_sizes[source_id] = len(results)
        self.unified_search_results_by_source[source_id] = results

    def decorate_unified_search_result(self, track: dict) -> dict:
        media_item = MediaItem.from_online(track)
        legacy = media_item.to_legacy_online()
        source = self.get_registered_source_safely(media_item.source_id)
        if not source or not source.get("enabled") or not source.get("sourceUrl"):
            media_item.availability = "unavailable"
            media_item.can_play = bool(media_item.local_file_path)
            media_item.can_download = False
        stable_id = RemoteTrackStore.stable_id_for_track(legacy)
        record = self.remote_tracks.get(stable_id)
        local_path = str((record or {}).get("local_path") or "")
        downloaded = bool(local_path and Path(local_path).is_file())
        media_item.local_file_path = str(Path(local_path).resolve()) if downloaded else ""
        media_item.can_play = bool(media_item.can_play or downloaded)
        media_item.extra["remote_stable_id"] = stable_id if isinstance(record, dict) else ""
        media_item.extra["local_existing"] = downloaded or self.has_matching_local_song(
            media_item.to_dict()
        )
        return media_item.to_dict()

    def has_matching_local_song(self, track: dict) -> bool:
        title, artist, album = self.local_song_match_key(track)
        if not title or not artist:
            return False
        return (title, artist, album) in self.get_local_song_match_index()

    @staticmethod
    def local_song_match_key(track: dict) -> tuple[str, str, str]:
        return tuple(
            " ".join(str(track.get(field) or "").casefold().split())
            for field in ("title", "artist", "album")
        )

    def get_local_song_match_index(self) -> set[tuple[str, str, str]]:
        revision = int(getattr(self, "library_data_revision", 0))
        if (
            self._local_song_match_index is not None
            and self._local_song_match_index_revision == revision
        ):
            return self._local_song_match_index
        index: set[tuple[str, str, str]] = set()
        for row in range(self.song_list.count()):
            item = self.song_list.item(row)
            song = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if not isinstance(song, dict) or song.get("recordKind") == "remote":
                continue
            key = self.local_song_match_key(song)
            if key[0] and key[1]:
                index.add(key)
        self._local_song_match_index = index
        self._local_song_match_index_revision = revision
        self._local_song_match_index_build_count += 1
        return index

    def invalidate_local_song_match_index(self) -> None:
        self._local_song_match_index = None
        self._local_song_match_index_revision = -1

    def refresh_unified_search_result_states(self, source_id: str = "") -> None:
        page = getattr(self, "search_page", None)
        if page is None or not self.unified_search_results:
            return
        target = str(source_id or "").strip()
        target_ids = (
            [target]
            if target
            else list(self._unified_search_source_order)
        )
        states = {
            str(state.get("sourceId") or state.get("source_id") or ""): dict(state)
            for state in self.unified_search_summary.get("sources", [])
            if isinstance(state, dict)
        }
        keyword = self.search_input.text().strip()
        for current_source_id in target_ids:
            current_results = self.unified_search_results_by_source.get(
                current_source_id,
                [],
            )
            if not current_results:
                continue
            decorated = [
                self.decorate_unified_search_result(result)
                for result in current_results
            ]
            self._replace_unified_search_source_results(
                current_source_id,
                decorated,
            )
            state = states.get(current_source_id, {})
            page.update_online_source_results(
                keyword,
                current_source_id,
                str(
                    state.get("sourceName")
                    or state.get("source_name")
                    or current_source_id
                ),
                decorated,
                state,
                self.unified_search_summary,
            )

    def play_unified_search_track(self, track: dict) -> None:
        media_item = MediaItem.from_mapping(track)
        stable_id = str(media_item.extra.get("remote_stable_id") or "").strip()
        record = self.remote_tracks.get(stable_id)
        if isinstance(record, dict):
            song_data = RemoteTrackStore.to_song_data(
                stable_id,
                record,
                self.is_remote_source_available(record),
            )
            media_item = self.media_item_from_song_data(song_data)
        if media_item.availability != "available" and not media_item.is_local_available:
            self.set_online_status_message("该在线来源当前不可用。")
            return
        self.create_playback_context(
            media_item,
            self.unified_search_results,
            source_type="online_search",
            source_id=self.search_input.text().strip() or "online",
        )
        self.play_queue_item(media_item)

    def remove_unified_track_from_current_playlist(self, track: dict) -> None:
        media_item = MediaItem.from_mapping(track)
        stable_id = str(media_item.extra.get("remote_stable_id") or "").strip()
        if not stable_id:
            stable_id = RemoteTrackStore.stable_id_for_track(
                media_item.to_legacy_online()
            )
        self.remove_remote_from_current_playlist(stable_id)
        self.refresh_unified_search_result_states()

    def clear_search(self) -> None:
        self.search_input.clear()

    def current_media_key(self) -> str:
        return self.current_track_identity()

    def browse_media_item(self, value: dict) -> None:
        try:
            media_item = MediaItem.from_mapping(value)
        except (TypeError, ValueError):
            return
        self.browsing_song_data = media_item.to_dict()
        self.browsing_song_path = (
            self.normalize_song_path(media_item.local_file_path)
            if media_item.local_file_path
            else None
        )
        print(f"你正在浏览：{media_item.title} - {media_item.artist}")

    def play_media_item(self, value: dict) -> None:
        try:
            media_item = MediaItem.from_mapping(value)
        except (TypeError, ValueError):
            return
        self.browse_media_item(media_item.to_dict())
        candidates = None
        source_type = None
        source_id = None
        search_page = getattr(self, "search_page", None)
        stack = getattr(self, "content_stack", None)
        if search_page is not None and stack is not None and stack.currentWidget() is search_page:
            if search_page.current_tab() == "local":
                candidates = list(getattr(search_page, "_local_results", []))
                source_type = "local_search"
            else:
                candidates = list(self.unified_search_results)
                source_type = "online_search"
            source_id = self.search_input.text().strip() or "search"
        self.create_playback_context(
            media_item,
            candidates,
            source_type=source_type,
            source_id=source_id,
        )
        if not self.play_queue_item(media_item):
            if media_item.media_type == "online":
                self.set_online_status_message("该在线来源当前不可播放。")
            else:
                QMessageBox.information(self, "无法播放", "本地音乐文件已经不存在。")

    def queue_media_item_next(self, value: dict) -> None:
        media_item = MediaItem.from_mapping(value)
        if self.queue_media_item(media_item, insert_next=True, notify_user=False):
            self.set_online_status_message(f"已将“{media_item.title}”设为下一首播放。")

    def get_local_media_item_collection_state(self, value: dict) -> dict:
        return self.media_interactions.get_local_state(value)

    def like_local_media_item(self, value: dict) -> None:
        self.media_interactions.like_local(value)

    def unlike_local_media_item(self, value: dict) -> None:
        self.media_interactions.unlike_local(value)

    def add_local_media_item_to_playlist(self, value: dict, playlist_id: str) -> None:
        self.media_interactions.add_local_to_playlist(value, playlist_id)

    def remove_local_media_item_from_current_playlist(self, value: dict) -> None:
        self.media_interactions.remove_local_from_current_playlist(value)

    def open_local_media_item_folder(self, value: dict) -> None:
        self.media_interactions.open_local_folder(value)

    def remove_local_media_item(self, value: dict) -> None:
        self.media_interactions.remove_local(value)

    def show_media_item_info(self, value: dict) -> None:
        self.media_interactions.show_info(value)

    def show_media_item_context_menu(self, value: dict, global_position) -> None:
        self.media_interactions.show_context_menu(value, global_position)
    def get_category_display_value(self, song_data: dict, field: str) -> str:
        if field == "artist":
            return str(song_data.get("artist") or "未知艺术家")

        if field == "album":
            return str(song_data.get("album") or "未知专辑")

        return ""

    def collect_category_values(self, field: str) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is None:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict) or song_data.get("demo"):
                continue

            if not self.song_matches_base_library_view(song_data):
                continue

            value = self.get_category_display_value(song_data, field)
            counts[value] = counts.get(value, 0) + 1

        return sorted(counts.items(), key=lambda pair: (pair[0] == "未知艺术家" or pair[0] == "未知专辑", pair[0].lower()))

    def show_artist_filter_menu(self) -> None:
        self.show_category_filter_menu("artist", self.artist_filter_btn)

    def show_album_filter_menu(self) -> None:
        self.show_category_filter_menu("album", self.album_filter_btn)

    def show_category_filter_menu(self, field: str, button: QPushButton) -> None:
        menu = QMenu(self)
        menu.setObjectName("songContextMenu")

        values = self.collect_category_values(field)

        if not values:
            empty_action = menu.addAction("没有可筛选的内容")
            empty_action.setEnabled(False)
        else:
            for value, count in values[:80]:
                action = menu.addAction(f"{value} ({count})")
                action.triggered.connect(lambda checked=False, f=field, v=value: self.apply_library_category_filter(f, v))

            if len(values) > 80:
                more_action = menu.addAction(f"还有 {len(values) - 80} 项，可用搜索缩小范围")
                more_action.setEnabled(False)

        menu.addSeparator()
        clear_action = menu.addAction("清除分类筛选")
        clear_action.triggered.connect(lambda checked=False: self.clear_library_category_filter())
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def apply_library_category_filter(self, filter_type: str, value: str) -> None:
        self.library_category_filter_type = filter_type if filter_type in {"artist", "album"} else None
        self.library_category_filter_value = str(value or "") if self.library_category_filter_type else ""
        self.filter_song_list(self.search_input.text())
        self.update_category_filter_controls()
        self.remember_library_view_key()

    def clear_library_category_filter(self, checked: bool = False, refresh: bool = True) -> None:
        self.library_category_filter_type = None
        self.library_category_filter_value = ""
        self.update_category_filter_controls()

        if refresh and hasattr(self, "song_list"):
            self.filter_song_list(self.search_input.text())
            self.remember_library_view_key()

    def update_category_filter_controls(self) -> None:
        filter_type = getattr(self, "library_category_filter_type", None)
        filter_value = str(getattr(self, "library_category_filter_value", "") or "")

        if hasattr(self, "category_filter_label"):
            if filter_type == "artist" and filter_value:
                self.category_filter_label.setText(f"当前筛选：歌手 - {filter_value}")
            elif filter_type == "album" and filter_value:
                self.category_filter_label.setText(f"当前筛选：专辑 - {filter_value}")
            else:
                self.category_filter_label.setText("当前筛选：全部")

        for button_name, active in (
            ("category_all_btn", not filter_type),
            ("artist_filter_btn", filter_type == "artist"),
            ("album_filter_btn", filter_type == "album"),
        ):
            button = getattr(self, button_name, None)

            if button is None:
                continue

            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def get_visible_song_items(self) -> list[QListWidgetItem]:
        items = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is not None and not item.isHidden() and self.get_song_data_from_item(item):
                items.append(item)

        return items

    def select_all_visible_songs(self) -> None:
        self.song_list.clearSelection()

        for item in self.get_visible_song_items():
            item.setSelected(True)

    def clear_song_selection(self) -> None:
        self.song_list.clearSelection()

    def select_same_category_songs(self, source_item: QListWidgetItem | None, field: str) -> None:
        source_data = self.get_song_data_from_item(source_item)

        if not source_data:
            return

        target = self.get_category_display_value(source_data, field)
        self.song_list.clearSelection()

        for item in self.get_visible_song_items():
            song_data = self.get_song_data_from_item(item)

            if song_data and self.get_category_display_value(song_data, field) == target:
                item.setSelected(True)

    def get_selected_song_items(self) -> list[QListWidgetItem]:
        selected_items = [item for item in self.song_list.selectedItems() if self.get_song_data_from_item(item)]

        if selected_items:
            return selected_items

        current_item = self.song_list.currentItem()
        return [current_item] if self.get_song_data_from_item(current_item) else []
    def filter_song_list(self, keyword: str) -> None:
        started_at = time.perf_counter()
        # Search lives on its own page. The library list only applies its active
        # category/playlist scope and therefore keeps its scroll and selection.
        keyword = ""
        visible_count = 0
        visible_song_data: list[dict] = []
        liked_paths_cache = None
        playlist_paths_cache = None
        liked_remote_ids_cache = None
        playlist_remote_ids_cache = None

        if self.current_library_view == "liked":
            liked_paths_cache = set(self.get_liked_song_paths())
            liked_remote_ids_cache = set(self.get_playlist_remote_ids("liked"))
        elif self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            playlist_paths_cache = set(self.get_playlist_song_paths(playlist_id))
            playlist_remote_ids_cache = set(
                self.get_playlist_remote_ids(playlist_id)
            )

        membership_cache_ready_at = time.perf_counter()

        previous_signal_state = self.song_list.blockSignals(True)
        self.song_list.setUpdatesEnabled(False)

        try:
            for index in range(self.song_list.count()):
                item = self.song_list.item(index)
                song_data = item.data(Qt.ItemDataRole.UserRole)

                if not isinstance(song_data, dict):
                    if item.isHidden():
                        item.setHidden(False)
                    visible_count += 1
                    continue

                title = str(song_data.get("title", ""))
                artist = str(song_data.get("artist", ""))
                album = str(song_data.get("album", ""))
                path = str(song_data.get("path", ""))

                search_text = f"{title} {artist} {album} {path}".lower()
                matches_keyword = not keyword or keyword in search_text
                matches_view = self.song_matches_current_view(
                    song_data,
                    liked_paths_cache,
                    playlist_paths_cache,
                    liked_remote_ids_cache,
                    playlist_remote_ids_cache,
                )
                should_show = matches_keyword and matches_view

                should_hide = not should_show
                if item.isHidden() != should_hide:
                    item.setHidden(should_hide)

                if should_show:
                    visible_count += 1
                    if not song_data.get("demo"):
                        visible_song_data.append(song_data)
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

        rows_filtered_at = time.perf_counter()

        if hasattr(self, "song_list_empty_hint"):
            if visible_count <= 0:
                if keyword:
                    self.song_list_empty_hint.setText("没有找到匹配的歌曲\n换个关键词，或清空搜索后再试。")
                elif self.current_library_view == "liked":
                    self.song_list_empty_hint.setText("“我喜欢”还是空的\n播放歌曲时点击底部收藏按钮即可加入。")
                elif str(self.current_library_view).startswith("playlist:"):
                    self.song_list_empty_hint.setText("这个歌单还没有歌曲\n可以从歌曲右键菜单添加。")
                else:
                    self.song_list_empty_hint.setText("音乐库还是空的\n导入本地音乐后，就可以在这里浏览和播放。")

                self.song_list_empty_hint.setVisible(True)
                self.song_list.setVisible(False)

                if hasattr(self, "song_table_header"):
                    self.song_table_header.setVisible(False)
            else:
                self.song_list_empty_hint.setVisible(False)
                self.song_list.setVisible(True)

                if hasattr(self, "song_table_header"):
                    self.song_table_header.setVisible(True)

                self.schedule_visible_library_durations()
        self.update_library_page_scope(visible_song_data)
        scope_updated_at = time.perf_counter()
        elapsed_ms = (scope_updated_at - started_at) * 1000
        if self.playlist_id_for_current_view():
            print(
                "[perf] playlist_view_filter phases: "
                f"membership={(membership_cache_ready_at - started_at) * 1000:.1f} ms, "
                f"rows={(rows_filtered_at - membership_cache_ready_at) * 1000:.1f} ms, "
                f"layout={(scope_updated_at - rows_filtered_at) * 1000:.1f} ms"
            )
        print(f"搜索关键词：{keyword or '无'}，显示歌曲数量：{visible_count}")
        print(f"[perf] filter_song_list: {elapsed_ms:.1f} ms, songs={self.song_list.count()}")

    def media_item_from_song_data(self, song_data: dict) -> MediaItem:
        if song_data.get("recordKind") != "remote":
            return MediaItem.from_local(song_data)
        remote = self.get_remote_record_from_song_data(song_data)
        if remote is None:
            return MediaItem.from_online(
                {
                    "track_id": str(song_data.get("remoteStableId") or "missing"),
                    "source_id": "missing",
                    "source_name": "来源不可用",
                    "title": song_data.get("title"),
                    "artist": song_data.get("artist"),
                    "album": song_data.get("album"),
                    "availability": "unavailable",
                }
            )
        stable_id, record = remote
        track = RemoteTrackStore.to_online_track(stable_id, record)
        source = self.get_registered_source_safely(str(record.get("source_id") or "")) or {}
        track["sourceName"] = str(source.get("name") or record.get("source_id") or "来源不可用")
        track["capabilities"] = dict(source.get("capabilities") or {})
        track["availability"] = "available" if self.is_remote_source_available(record) else "unavailable"
        local_path = str(record.get("local_path") or "")
        if local_path and Path(local_path).is_file():
            track["localPath"] = str(Path(local_path).resolve())
        return MediaItem.from_online(track)

    def update_library_page_scope(
        self,
        visible_song_data: list[dict] | None = None,
    ) -> None:
        page = getattr(self, "library_page", None)
        if page is None or not hasattr(self, "song_list"):
            return
        if visible_song_data is None:
            visible_song_data = []
            for row in range(self.song_list.count()):
                item = self.song_list.item(row)
                data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
                if (
                    item is None
                    or item.isHidden()
                    or not isinstance(data, dict)
                    or data.get("demo")
                ):
                    continue
                visible_song_data.append(data)
        tracks = [
            self.media_item_from_song_data(data).to_dict()
            for data in visible_song_data
        ]
        view_titles = {
            "all": "全部歌曲",
            "liked": "我喜欢",
            "recent_played": "最近播放",
            "frequent": "常听歌曲",
            "recent_added": "最近添加",
        }
        if self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
            title = self.get_playlist_name(playlist_id)
        else:
            title = view_titles.get(self.current_library_view, "音乐库")
        cache_key = (
            f"{self.current_library_view}:{self.library_data_revision}:"
            f"{len(tracks)}"
        )
        page.set_scope(title, tracks, cache_key)

    def on_library_content_view_changed(self, mode: str) -> None:
        mode = str(mode)
        if hasattr(self, "library_page"):
            self.library_page.scroll_current_view_to_top()
        if mode == getattr(self, "initial_library_content_view", "tracks"):
            return
        self.initial_library_content_view = mode
        self.save_hush_settings({"library_content_view": mode})

    def get_visible_rows(self) -> list[int]:
        visible_rows = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item and not item.isHidden():
                visible_rows.append(row)

        return visible_rows

    def add_demo_songs(self, refresh_view: bool = True) -> None:
        self.song_identity_to_item = {}
        self.song_list.clear()
        if refresh_view:
            self.filter_song_list(self.search_input.text())

    def has_demo_songs(self) -> bool:
        if self.song_list.count() == 0:
            return False

        for index in range(self.song_list.count()):
            item = self.song_list.item(index)
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict) and song_data.get("demo"):
                return True

        return False

    def get_existing_song_paths(self) -> set[str]:
        paths = set()

        for index in range(self.song_list.count()):
            item = self.song_list.item(index)
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            if song_data.get("demo") or song_data.get("recordKind") == "remote":
                continue

            path = song_data.get("path", "")

            if path:
                paths.add(str(Path(path).resolve()))

        return paths

    def load_pending_imports(self) -> list[dict]:
        if not hasattr(self, "pending_imports_file") or not self.pending_imports_file.exists():
            return []

        try:
            with self.pending_imports_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            pending = []
            seen = set()

            for item in data:
                if not isinstance(item, dict):
                    continue

                path = self.normalize_song_path(item.get("path", ""))

                if not path or path.lower() in seen:
                    continue

                if not Path(path).exists():
                    continue

                item = dict(item)
                item["path"] = path
                pending.append(item)
                seen.add(path.lower())

            return pending
        except Exception as error:
            print("读取待导入音乐失败：", error)
            return []

    def save_pending_imports(self) -> None:
        try:
            self.pending_imports_file.parent.mkdir(parents=True, exist_ok=True)

            with self.pending_imports_file.open("w", encoding="utf-8") as file:
                json.dump(self.pending_imports, file, ensure_ascii=False, indent=2)
        except Exception as error:
            print("保存待导入音乐失败：", error)

    def load_ignored_imports(self) -> set[str]:
        if not hasattr(self, "ignored_imports_file") or not self.ignored_imports_file.exists():
            return set()

        try:
            with self.ignored_imports_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                return set()

            ignored_paths = set()

            for path in data:
                normalized_path = self.normalize_song_path(path)

                if normalized_path:
                    ignored_paths.add(normalized_path.lower())

            return ignored_paths
        except Exception as error:
            print("读取忽略导入记录失败：", error)
            return set()

    def save_ignored_imports(self) -> None:
        try:
            self.ignored_imports_file.parent.mkdir(parents=True, exist_ok=True)

            with self.ignored_imports_file.open("w", encoding="utf-8") as file:
                json.dump(sorted(self.ignored_imports), file, ensure_ascii=False, indent=2)
        except Exception as error:
            print("保存忽略导入记录失败：", error)

    def get_pending_import_paths(self) -> set[str]:
        return {
            self.normalize_song_path(item.get("path", "")).lower()
            for item in getattr(self, "pending_imports", [])
            if self.normalize_song_path(item.get("path", ""))
        }

    def add_pending_import(self, song_data: dict) -> bool:
        path = self.normalize_song_path(song_data.get("path", ""))

        if not path:
            return False

        path_key = path.lower()

        if path_key in {item.lower() for item in self.get_existing_song_paths()}:
            return False

        if path_key in self.get_pending_import_paths():
            return False

        if path_key in getattr(self, "ignored_imports", set()):
            return False

        pending_song = dict(song_data)
        pending_song["path"] = path
        pending_song.setdefault("title", Path(path).stem)
        pending_song.setdefault("artist", "未知艺术家")
        pending_song.setdefault("album", "未知专辑")
        pending_song.setdefault("duration", 0)
        pending_song.setdefault("format", Path(path).suffix.lower().lstrip("."))
        pending_song.setdefault("source_folder", str(Path(path).parent))
        pending_song.setdefault("found_at", int(time.time()))
        pending_song.pop("demo", None)
        self.pending_imports.append(pending_song)
        return True

    def format_duration_text(self, seconds: int) -> str:
        seconds = max(0, int(seconds or 0))

        if seconds <= 0:
            return "未知"

        minutes = seconds // 60
        remaining = seconds % 60
        return f"{minutes}:{remaining:02d}"

    def format_pending_import_text(self, song_data: dict) -> str:
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")
        duration = self.format_duration_text(int(song_data.get("duration", 0) or 0))
        file_format = str(song_data.get("format", "")).upper() or Path(str(song_data.get("path", ""))).suffix.upper().lstrip(".")
        source_folder = song_data.get("source_folder", "")
        path = song_data.get("path", "")
        return f"{title}\n{artist} · {album} · {duration} · {file_format}\n{path}\n来源：{source_folder}"

    def refresh_pending_imports_list(self) -> None:
        if not hasattr(self, "pending_imports_list"):
            return

        self.pending_imports_list.setUpdatesEnabled(False)
        self.pending_imports_list.blockSignals(True)

        try:
            self.pending_imports_list.clear()

            for song_data in getattr(self, "pending_imports", []):
                item = QListWidgetItem(self.format_pending_import_text(song_data))
                item.setData(Qt.ItemDataRole.UserRole, song_data)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setSizeHint(QSize(0, 96))
                item.setToolTip(str(song_data.get("path", "")))
                self.pending_imports_list.addItem(item)

            pending_count = self.pending_imports_list.count()

            if hasattr(self, "pending_imports_hint"):
                self.pending_imports_hint.setText(f"待导入 {pending_count} 首音乐。试听不会加入正式音乐库。")

            if hasattr(self, "pending_empty_hint"):
                self.pending_empty_hint.setVisible(pending_count <= 0)
        finally:
            self.pending_imports_list.blockSignals(False)
            self.pending_imports_list.setUpdatesEnabled(True)

    def get_selected_pending_imports(self) -> list[dict]:
        selected = []

        if not hasattr(self, "pending_imports_list"):
            return selected

        for row in range(self.pending_imports_list.count()):
            item = self.pending_imports_list.item(row)

            if item and item.checkState() == Qt.CheckState.Checked:
                song_data = item.data(Qt.ItemDataRole.UserRole)

                if isinstance(song_data, dict):
                    selected.append(song_data)

        current_item = self.pending_imports_list.currentItem()

        if not selected and current_item is not None:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                selected.append(song_data)

        return selected

    def set_all_pending_checked(self, checked: bool) -> None:
        if not hasattr(self, "pending_imports_list"):
            return

        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked

        for row in range(self.pending_imports_list.count()):
            item = self.pending_imports_list.item(row)

            if item:
                item.setCheckState(state)

    def invert_pending_selection(self) -> None:
        if not hasattr(self, "pending_imports_list"):
            return

        for row in range(self.pending_imports_list.count()):
            item = self.pending_imports_list.item(row)

            if item:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def select_pending_by_field(self, field: str) -> None:
        current_item = self.pending_imports_list.currentItem() if hasattr(self, "pending_imports_list") else None

        if current_item is None:
            QMessageBox.information(self, "待导入音乐", "请先选中一首待导入音乐。")
            return

        current_data = current_item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(current_data, dict):
            return

        target = str(current_data.get(field, "")).strip()

        if not target:
            return

        for row in range(self.pending_imports_list.count()):
            item = self.pending_imports_list.item(row)
            song_data = item.data(Qt.ItemDataRole.UserRole) if item else None

            if isinstance(song_data, dict) and str(song_data.get(field, "")).strip() == target:
                item.setCheckState(Qt.CheckState.Checked)

    def show_pending_imports_page(self) -> None:
        self.set_sidebar_active("pending")

        if hasattr(self, "content_stack") and hasattr(self, "pending_imports_page"):
            self.content_stack.setCurrentWidget(self.pending_imports_page)

        self.set_right_panel_mode("info")
        self.refresh_pending_imports_list()

    def preview_pending_import(self, item: QListWidgetItem | None = None) -> None:
        if item is None and hasattr(self, "pending_imports_list"):
            item = self.pending_imports_list.currentItem()

        if item is None:
            QMessageBox.information(self, "待导入音乐", "请先选择一首待导入音乐。")
            return

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return

        self.load_song_for_playback(dict(song_data))
        self.play_current_song()
        print("正在试听待导入音乐，不会写入正式音乐库：", song_data.get("path", ""))

    def open_pending_import_folder(self) -> None:
        selected = self.get_selected_pending_imports()

        if not selected:
            QMessageBox.information(self, "待导入音乐", "请先选择一首待导入音乐。")
            return

        path = self.normalize_song_path(selected[0].get("path", ""))

        if not path:
            return

        try:
            os.startfile(str(Path(path).parent))
        except Exception as error:
            QMessageBox.warning(self, "打开文件夹失败", str(error))

    def import_pending_songs(self, songs: list[dict] | None = None) -> None:
        selected = songs or self.get_selected_pending_imports()

        if not selected:
            QMessageBox.information(self, "待导入音乐", "请先勾选或选中要加入音乐库的歌曲。")
            return

        existing_paths = {path.lower() for path in self.get_existing_song_paths()}
        selected_paths = {self.normalize_song_path(song.get("path", "")).lower() for song in selected if self.normalize_song_path(song.get("path", ""))}
        added_count = 0

        for song_data in selected:
            path = self.normalize_song_path(song_data.get("path", ""))

            if not path or path.lower() in existing_paths or not Path(path).exists():
                continue

            library_song = dict(song_data)
            library_song.update(
                {
                    "path": path,
                    "added_at": int(time.time()) + added_count,
                    "demo": False,
                }
            )
            item = self.create_song_list_item(library_song)
            self.song_list.addItem(item)
            existing_paths.add(path.lower())
            added_count += 1

        if selected_paths:
            self.pending_imports = [
                song for song in self.pending_imports
                if self.normalize_song_path(song.get("path", "")).lower() not in selected_paths
            ]
            self.save_pending_imports()

        if added_count > 0:
            self.mark_library_list_dirty()
            self.apply_current_library_sort(refresh_view=False)
            self.filter_song_list(self.search_input.text())
            self.save_music_library()
            self.update_side_info_panel()
            self.update_view_buttons()

        self.refresh_pending_imports_list()
        QMessageBox.information(self, "待导入音乐", f"已加入 {added_count} 首歌曲到音乐库。")

    def ignore_pending_imports(self, songs: list[dict] | None = None) -> None:
        selected = songs or self.get_selected_pending_imports()

        if not selected:
            QMessageBox.information(self, "待导入音乐", "请先勾选或选中要忽略的歌曲。")
            return

        selected_paths = set()

        for song_data in selected:
            path = self.normalize_song_path(song_data.get("path", ""))

            if path:
                selected_paths.add(path.lower())
                self.ignored_imports.add(path.lower())

        self.pending_imports = [
            song for song in self.pending_imports
            if self.normalize_song_path(song.get("path", "")).lower() not in selected_paths
        ]
        self.save_pending_imports()
        self.save_ignored_imports()
        self.refresh_pending_imports_list()
        QMessageBox.information(self, "待导入音乐", f"已忽略 {len(selected_paths)} 首歌曲。")
    def get_music_scan_folders(self) -> list[str]:
        folders = self.get_user_setting("music_scan_folders", [])

        if not isinstance(folders, list):
            return []

        cleaned_folders = []
        seen = set()

        for folder in folders:
            if not isinstance(folder, str):
                continue

            folder = folder.strip()

            if not folder:
                continue

            key = folder.lower()

            if key in seen:
                continue

            seen.add(key)
            cleaned_folders.append(folder)

        return cleaned_folders

    def auto_scan_music_folders_on_startup(self) -> None:
        if not bool(self.get_user_setting("auto_scan_music_folders_on_startup", True)):
            return

        if not self.get_music_scan_folders():
            return

        self.scan_music_folders(manual=False)

    def scan_music_folder_path(self, folder_path: str) -> None:
        if not folder_path:
            return

        self.scan_music_folders(manual=True, folders=[folder_path])

    def scan_music_folders(self, manual: bool = False, folders: list[str] | None = None) -> None:
        started_at = time.perf_counter()
        scan_folders = folders if folders is not None else self.get_music_scan_folders()
        scan_folders = [str(folder).strip() for folder in scan_folders if str(folder).strip()]

        if not scan_folders:
            if manual:
                QMessageBox.information(self, "音乐文件夹", "还没有添加需要扫描的音乐文件夹。")
            return

        if getattr(self, "music_scan_in_progress", False):
            if manual:
                QMessageBox.information(self, "音乐文件夹", "正在扫描音乐文件夹，请稍后再试。")
            return

        existing_paths = [path.lower() for path in self.get_existing_song_paths()]
        pending_paths = list(self.get_pending_import_paths())
        ignored_paths = list(getattr(self, "ignored_imports", set()))
        worker = MusicFolderScanWorker(scan_folders, existing_paths, pending_paths, ignored_paths)
        thread = QThread(self)
        worker.moveToThread(thread)

        self.music_scan_in_progress = True
        self.music_scan_workers.append(worker)
        self.music_scan_threads.append(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(lambda result, manual=manual: self.on_music_scan_finished(result, manual))
        worker.finished.connect(lambda result=None, worker=worker: self.cleanup_worker_reference(worker, "music_scan"))
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda thread=thread: self.cleanup_thread_reference(thread, "music_scan"))
        thread.finished.connect(thread.deleteLater)
        thread.start()
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] scan_music_folders dispatch: {elapsed_ms:.1f} ms, folders={len(scan_folders)}")

        if manual:
            print("开始扫描音乐文件夹：", scan_folders)

    def on_music_scan_finished(self, result: dict, manual: bool = False) -> None:
        self.music_scan_in_progress = False

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "scanned": 0,
                "new_songs": [],
                "duplicates": 0,
                "failed": 1,
                "errors": ["扫描结果无效"],
            }

        added_count = 0
        pending_count = 0
        new_songs = [
            song for song in result.get("new_songs", [])
            if isinstance(song, dict)
        ]
        import_mode = str(self.get_user_setting("music_scan_import_mode", "pending"))

        if import_mode == "auto":
            if self.has_demo_songs() and new_songs:
                self.song_identity_to_item = {}
                self.song_list.clear()

            existing_paths = {path.lower() for path in self.get_existing_song_paths()}

            for song_data in new_songs:
                path = str(song_data.get("path", "")).strip()

                if not path:
                    continue

                normalized_key = path.lower()

                if normalized_key in existing_paths:
                    result["duplicates"] = int(result.get("duplicates", 0) or 0) + 1
                    continue

                item = self.create_song_list_item(song_data)
                self.song_list.addItem(item)
                existing_paths.add(normalized_key)
                added_count += 1

            if added_count > 0:
                self.mark_library_list_dirty()
                self.apply_current_library_sort(refresh_view=False)
                self.filter_song_list(self.search_input.text())
                self.save_music_library()
                self.update_side_info_panel()
                self.update_view_buttons()
        else:
            for song_data in new_songs:
                if self.add_pending_import(song_data):
                    pending_count += 1

            if pending_count > 0:
                self.save_pending_imports()
                self.refresh_pending_imports_list()

        scanned_count = int(result.get("scanned", 0) or 0)
        duplicate_count = int(result.get("duplicates", 0) or 0)
        failed_count = int(result.get("failed", 0) or 0)

        if import_mode == "auto":
            print(
                f"音乐文件夹扫描完成：扫描 {scanned_count} 个文件，"
                f"新增 {added_count} 首，跳过重复 {duplicate_count} 首，失败 {failed_count} 个"
            )
        else:
            print(
                f"音乐文件夹扫描完成：扫描 {scanned_count} 个文件，"
                f"待导入 {pending_count} 首，跳过重复/已忽略 {duplicate_count} 首，失败 {failed_count} 个"
            )

        if manual:
            if import_mode == "auto":
                QMessageBox.information(
                    self,
                    "音乐文件夹扫描完成",
                    f"扫描了 {scanned_count} 个音频文件\n"
                    f"新增了 {added_count} 首歌\n"
                    f"跳过了 {duplicate_count} 首重复歌曲\n"
                    f"失败了 {failed_count} 个文件",
                )
            else:
                QMessageBox.information(
                    self,
                    "音乐文件夹扫描完成",
                    f"扫描了 {scanned_count} 个音频文件\n"
                    f"发现 {pending_count} 首待导入音乐\n"
                    f"跳过了 {duplicate_count} 首重复、已待导入或已忽略歌曲\n"
                    f"失败了 {failed_count} 个文件",
                )

                if pending_count > 0:
                    self.show_pending_imports_page()
    def save_music_library(self) -> None:
        self.library_file.parent.mkdir(parents=True, exist_ok=True)

        songs = []

        for index in range(self.song_list.count()):
            item = self.song_list.item(index)
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            if song_data.get("demo") or song_data.get("recordKind") == "remote":
                continue

            path = song_data.get("path", "")

            if not path:
                continue

            saved_song = dict(song_data)
            saved_song.pop("demo", None)
            saved_song.update(
                {
                    "title": song_data.get("title", "未知歌曲"),
                    "artist": song_data.get("artist", "未知艺术家"),
                    "album": song_data.get("album", "未知专辑"),
                    "path": str(Path(path).resolve()),
                    "added_at": int(song_data.get("added_at", 0) or 0),
                }
            )
            songs.append(saved_song)

        with self.library_file.open("w", encoding="utf-8") as file:
            json.dump(songs, file, ensure_ascii=False, indent=2)

        print(f"音乐库已保存：{self.library_file}")
        print(f"已保存歌曲数量：{len(songs)}")

    def load_metadata_cache(self) -> dict:
        if not hasattr(self, "metadata_cache_file") or not self.metadata_cache_file.exists():
            return {}

        try:
            with self.metadata_cache_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                return data

            return {}

        except Exception as error:
            print("读取歌曲信息匹配缓存失败：", error)
            return {}

    def save_metadata_cache(self) -> None:
        try:
            self.metadata_cache_file.parent.mkdir(parents=True, exist_ok=True)

            with self.metadata_cache_file.open("w", encoding="utf-8") as file:
                json.dump(self.metadata_cache, file, ensure_ascii=False, indent=2)

        except Exception as error:
            print("保存歌曲信息匹配缓存失败：", error)

    def update_library_json_song_metadata(self, song_path: str, updates: dict) -> None:
        normalized_target = self.normalize_song_path(song_path)

        if not normalized_target:
            return

        try:
            if self.library_file.exists():
                with self.library_file.open("r", encoding="utf-8") as file:
                    songs = json.load(file)
            else:
                songs = []

            if not isinstance(songs, list):
                songs = []

            updated = False

            for song in songs:
                if not isinstance(song, dict):
                    continue

                current_path = self.normalize_song_path(song.get("path", ""))

                if current_path != normalized_target:
                    continue

                for key in (
                    "title",
                    "artist",
                    "album",
                    "musicbrainz_recording_id",
                    "musicbrainz_release_id",
                ):
                    if key in updates:
                        song[key] = updates[key]

                updated = True
                break

            if not updated:
                new_song = {
                    "title": updates.get("title", "未知歌曲"),
                    "artist": updates.get("artist", "未知艺术家"),
                    "album": updates.get("album", "未知专辑"),
                    "path": normalized_target,
                    "added_at": int(time.time()),
                }

                for key in ("musicbrainz_recording_id", "musicbrainz_release_id"):
                    if key in updates:
                        new_song[key] = updates[key]

                songs.append(new_song)

            self.library_file.parent.mkdir(parents=True, exist_ok=True)

            with self.library_file.open("w", encoding="utf-8") as file:
                json.dump(songs, file, ensure_ascii=False, indent=2)

            print("已更新音乐库歌曲信息：", normalized_target)

        except Exception as error:
            print("更新音乐库歌曲信息失败：", error)
            raise

    def get_metadata_cache_key(self, song_data: dict) -> str:
        song_path = self.normalize_song_path(song_data.get("path", ""))

        if song_path:
            return hashlib.sha1(song_path.lower().encode("utf-8")).hexdigest()

        raw_key = f"{song_data.get('title', '')}|{song_data.get('artist', '')}|{song_data.get('album', '')}"
        return hashlib.sha1(raw_key.lower().encode("utf-8")).hexdigest()

    def build_metadata_search_query(self, song_data: dict) -> str:
        title = self.clean_search_text(song_data.get("title", ""))
        artist = self.clean_search_text(song_data.get("artist", ""))
        album = self.clean_search_text(song_data.get("album", ""))

        if not title:
            song_path = self.normalize_song_path(song_data.get("path", ""))

            if song_path:
                title = Path(song_path).stem

        parts = []

        if title and artist:
            parts.append(f'recording:"{title}" AND artist:"{artist}"')
        elif title:
            parts.append(f'recording:"{title}"')

        if album:
            parts.append(f'release:"{album}"')

        if parts:
            return " AND ".join(parts)

        song_path = self.normalize_song_path(song_data.get("path", ""))
        return Path(song_path).stem if song_path else ""

    def parse_musicbrainz_candidates(self, response_json: dict) -> list[dict]:
        recordings = response_json.get("recordings", [])

        if not isinstance(recordings, list):
            return []

        candidates = []

        for recording in recordings:
            if not isinstance(recording, dict):
                continue

            recording_id = str(recording.get("id", "")).strip()
            title = str(recording.get("title", "")).strip()

            if not recording_id or not title:
                continue

            artist_names = []

            for credit in recording.get("artist-credit", []) or []:
                if not isinstance(credit, dict):
                    continue

                artist = credit.get("artist", {})

                if isinstance(artist, dict):
                    name = str(artist.get("name", "")).strip()

                    if name:
                        artist_names.append(name)

            artist_text = " / ".join(artist_names) if artist_names else "未知艺术家"
            release_title = "未知专辑"
            release_date = ""
            release_id = ""

            releases = recording.get("releases", []) or []

            if isinstance(releases, list):
                for release in releases:
                    if not isinstance(release, dict):
                        continue

                    candidate_album = str(release.get("title", "")).strip()

                    if candidate_album:
                        release_title = candidate_album
                        release_date = str(release.get("date", "")).strip()
                        release_id = str(release.get("id", "")).strip()
                        break

            candidate = {
                "title": title,
                "artist": artist_text,
                "album": release_title,
                "release_date": release_date,
                "score": int(recording.get("score", 0) or 0),
                "musicbrainz_recording_id": recording_id,
            }

            if release_id:
                candidate["musicbrainz_release_id"] = release_id

            candidates.append(candidate)

            if len(candidates) >= 10:
                break

        return candidates

    def search_musicbrainz_metadata(self, song_data: dict) -> tuple[list[dict], str]:
        query = self.build_metadata_search_query(song_data)

        if not query:
            return [], ""

        cache_key = self.get_metadata_cache_key(song_data)
        cached = self.metadata_cache.get(cache_key, {})

        if (
            isinstance(cached, dict)
            and cached.get("query") == query
            and isinstance(cached.get("candidates"), list)
        ):
            return cached["candidates"], query

        headers = {
            "User-Agent": "HushPlayer/0.5 metadata matcher (local personal music player)",
            "Accept": "application/json",
        }

        response = requests.get(
            "https://musicbrainz.org/ws/2/recording/",
            params={
                "query": query,
                "fmt": "json",
                "limit": 10,
            },
            headers=headers,
            timeout=8,
        )
        response.raise_for_status()

        candidates = self.parse_musicbrainz_candidates(response.json())
        self.metadata_cache[cache_key] = {
            "query": query,
            "candidates": candidates,
            "queried_at": int(time.time()),
        }
        self.save_metadata_cache()
        return candidates, query

    def show_metadata_candidates_dialog(self, song_data: dict, candidates: list[dict]) -> dict | None:
        dialog = MetadataMatchDialog(song_data, candidates, self)
        self.apply_windows_dark_title_bar(dialog)
        QTimer.singleShot(0, lambda dialog=dialog: self.apply_windows_dark_title_bar(dialog))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        return dialog.selected_candidate

    def apply_metadata_candidate(self, song_data: dict, candidate: dict) -> None:
        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            QMessageBox.information(self, "联网匹配歌曲信息", "这首歌没有有效文件路径。")
            return

        updates = {
            "title": candidate.get("title", song_data.get("title", "未知歌曲")),
            "artist": candidate.get("artist", song_data.get("artist", "未知艺术家")),
            "album": candidate.get("album", song_data.get("album", "未知专辑")),
        }

        if candidate.get("musicbrainz_recording_id"):
            updates["musicbrainz_recording_id"] = candidate["musicbrainz_recording_id"]

        if candidate.get("musicbrainz_release_id"):
            updates["musicbrainz_release_id"] = candidate["musicbrainz_release_id"]

        try:
            self.update_library_json_song_metadata(song_path, updates)
        except Exception as error:
            QMessageBox.warning(self, "联网匹配歌曲信息", f"保存歌曲信息失败：{error}")
            return

        updated_song_data = None

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is None:
                continue

            item_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(item_data, dict):
                continue

            if self.normalize_song_path(item_data.get("path", "")) != song_path:
                continue

            item_data.update(updates)
            self.refresh_song_item_display(item, item_data)
            updated_song_data = item_data

        if updated_song_data is None:
            song_data.update(updates)
            updated_song_data = song_data

        self.mark_library_list_dirty()
        self.apply_current_library_sort(refresh_view=False)
        self.filter_song_list(self.search_input.text())

        current_path = self.normalize_song_path(self.current_song_path)
        browsing_path = self.normalize_song_path(self.browsing_song_path)

        if current_path == song_path:
            title = updated_song_data.get("title", "未知歌曲")
            artist = updated_song_data.get("artist", "未知艺术家")
            album = updated_song_data.get("album", "未知专辑")
            self.bottom_song_title.setText(title)
            self.bottom_song_artist.setText(artist)
            self.bottom_song_title.setToolTip(title)
            self.bottom_song_artist.setToolTip(artist)
            self.now_song_title.setText(title)
            self.now_artist.setText(f"{artist} · {album}")

        if browsing_path == song_path:
            self.browsing_song_data = updated_song_data

        self.update_side_info_panel()
        self.update_like_button()
        self.sync_full_lyrics_from_current()
        self.sync_immersive_lyrics()

        QMessageBox.information(self, "联网匹配歌曲信息", "歌曲信息已更新。")

    def match_selected_song_metadata_online(self) -> None:
        item = self.song_list.currentItem()
        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "联网匹配歌曲信息", "请先选择一首真实歌曲。")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            candidates, query = self.search_musicbrainz_metadata(song_data)

        except requests.RequestException:
            QMessageBox.warning(self, "联网匹配歌曲信息", "联网匹配失败，请检查网络。")
            return

        except Exception as error:
            QMessageBox.warning(self, "联网匹配歌曲信息", f"联网匹配失败：{error}")
            return

        finally:
            QApplication.restoreOverrideCursor()

        if not candidates:
            QMessageBox.information(self, "联网匹配歌曲信息", "没有找到可靠匹配结果。")
            return

        print("MusicBrainz 匹配查询：", query)
        candidate = self.show_metadata_candidates_dialog(song_data, candidates)

        if candidate:
            self.apply_metadata_candidate(song_data, candidate)

    def finish_music_library_load(self, valid_count: int) -> None:
        self.filter_song_list(self.search_input.text())
        self.last_song_list_order_key = self.current_song_list_order_key()
        self.remember_library_view_key()

        if valid_count <= 0:
            return
        visible_rows = self.get_visible_rows()
        if not visible_rows:
            return
        first_row = visible_rows[0]
        self.song_list.setCurrentRow(first_row)
        first_item = self.song_list.item(first_row)
        if first_item:
            self.select_song(first_item)

    def load_music_library(
        self,
        refresh_view: bool = True,
    ) -> tuple[int, bool]:
        self.invalidate_local_song_match_index()
        print("正在读取音乐库：", self.library_file)

        if not self.library_file.exists():
            print("没有找到已保存的音乐库，显示空状态。")
            self.add_demo_songs(refresh_view=refresh_view)
            return 0, True

        try:
            with self.library_file.open("r", encoding="utf-8") as file:
                songs = json.load(file)

        except Exception as error:
            print("读取音乐库失败：", error)
            self.add_demo_songs(refresh_view=refresh_view)
            return 0, True

        if not songs:
            print("音乐库为空，显示空状态。")
            self.add_demo_songs(refresh_view=refresh_view)
            return 0, True

        previous_signal_state = self.song_list.blockSignals(True)
        self.song_list.setUpdatesEnabled(False)
        valid_count = 0
        song_list_is_local_only = True

        try:
            self.song_identity_to_item = {}
            self.song_list.clear()

            for song in songs:
                path = song.get("path", "")

                if not path:
                    continue

                if not Path(path).exists():
                    print("歌曲文件不存在，已跳过：", path)
                    continue

                title = song.get("title", "未知歌曲")
                artist = song.get("artist", "未知艺术家")
                album = song.get("album", "未知专辑")
                added_at = int(song.get("added_at", 0) or 0)
                song_data = dict(song)
                song_data.update(
                    {
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "path": str(Path(path).resolve()),
                        "added_at": added_at,
                        "demo": False,
                    }
                )
                if song_data.get("recordKind") == "remote":
                    song_list_is_local_only = False

                item = self.create_song_list_item(song_data)
                self.song_list.addItem(item)
                valid_count += 1
        finally:
            self.song_list.blockSignals(previous_signal_state)
            self.song_list.setUpdatesEnabled(True)

        if valid_count > 0:
            if refresh_view:
                self.finish_music_library_load(valid_count)
            print(f"已加载音乐库，共 {valid_count} 首歌。")
        else:
            self.add_demo_songs(refresh_view=refresh_view)
            print("保存的音乐文件路径全部失效，显示空状态。")
        return valid_count, song_list_is_local_only






















    def get_hush_settings(self) -> dict:
        settings = getattr(self, "settings", {})
        if not isinstance(settings, dict):
            return {}
        return deepcopy(settings)

    def get_user_setting(self, key: str, default=None):
        settings = getattr(self, "settings", {})
        if not isinstance(settings, dict):
            return default
        return deepcopy(settings.get(key, default))

    def _write_settings_file(self, settings: dict) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.settings_file.with_suffix(
            self.settings_file.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.settings_file)

    def flush_settings(self) -> bool:
        if hasattr(self, "settings_save_timer"):
            self.settings_save_timer.stop()
        if not getattr(self, "_settings_dirty", False):
            return False

        settings_snapshot = deepcopy(self.settings)
        try:
            self._write_settings_file(settings_snapshot)
            self._saved_settings = settings_snapshot
            self._settings_dirty = False
            print("设置已保存：", self.settings_file)
            return True

        except Exception as error:
            print("保存设置失败：", error)
            QMessageBox.warning(self, "设置", f"保存设置失败：{error}")
            return False

    def save_hush_settings(self, updates: dict, *, immediate: bool = False) -> bool:
        if not isinstance(updates, dict):
            return False

        changed = False
        for key, value in updates.items():
            copied_value = deepcopy(value)
            if key in self.settings and self.settings[key] == copied_value:
                continue
            self.settings[key] = copied_value
            changed = True

        self._settings_dirty = self.settings != self._saved_settings
        if not self._settings_dirty:
            self.settings_save_timer.stop()
            return changed
        if immediate:
            return self.flush_settings()
        if changed:
            self.settings_save_timer.start()
        return changed

    def apply_runtime_settings(self) -> None:
        immersive_window = getattr(self, "immersive_lyrics_window", None)

        if immersive_window is not None:
            immersive_window.cover_background_enabled = bool(
                self.get_user_setting("immersive_cover_background_enabled", True)
            )
            immersive_window.auto_hide_enabled = bool(
                self.get_user_setting("immersive_auto_hide_ui", True)
            )
            immersive_window.background_alpha = int(
                self.get_user_setting("immersive_background_alpha", 68)
            )

            if hasattr(immersive_window, "alpha_slider"):
                immersive_window.alpha_slider.blockSignals(True)
                immersive_window.alpha_slider.setValue(immersive_window.background_alpha)
                immersive_window.alpha_slider.blockSignals(False)

            if immersive_window.auto_hide_enabled:
                immersive_window.show_controls_temporarily()
            else:
                if hasattr(immersive_window, "hide_ui_timer"):
                    immersive_window.hide_ui_timer.stop()

                if hasattr(immersive_window, "control_header"):
                    immersive_window.control_header.show()

                if hasattr(immersive_window, "footer"):
                    immersive_window.footer.show()

                immersive_window.ui_visible = True
                immersive_window.setCursor(Qt.CursorShape.ArrowCursor)

            immersive_window.apply_immersive_style()

        floating_window = getattr(self, "floating_lyrics_window", None)

        if floating_window is not None:
            floating_window.text_color_name = str(self.get_user_setting("floating_lyrics_color", "white"))
            floating_window.text_alpha = int(self.get_user_setting("floating_lyrics_opacity", 100))
            floating_window.font_size = int(self.get_user_setting("floating_lyrics_font_size", 42))
            new_width = int(self.get_user_setting("floating_lyrics_width", floating_window.width()))
            floating_window.resize(new_width, floating_window.height())
            floating_window.apply_style()
            floating_window.save_preferences()

    def open_settings_dialog(self) -> None:
        self.set_sidebar_active("settings")
        dialog = SettingsDialog(self)
        self.apply_windows_dark_title_bar(dialog)
        QTimer.singleShot(0, lambda dialog=dialog: self.apply_windows_dark_title_bar(dialog))
        dialog.exec()

    def install_floating_lyrics_button(self) -> None:
        if not hasattr(self, "floating_lyrics_button"):
            self.floating_lyrics_button = QPushButton("桌面歌词")
            self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
            self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.floating_lyrics_button.setMinimumHeight(34)
            self.floating_lyrics_button.setMinimumWidth(80)
            self.floating_lyrics_button.setMaximumWidth(96)
            self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)

        self.update_floating_lyrics_button_state()
        return

        existing_button = getattr(self, "floating_lyrics_button", None)

        if existing_button is None:
            self.floating_lyrics_button = QPushButton("桌面歌词")
            self.floating_lyrics_button.setObjectName("floatingLyricsToggleButton")
            self.floating_lyrics_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.floating_lyrics_button.setMinimumHeight(34)
            self.floating_lyrics_button.setMinimumWidth(80)
            self.floating_lyrics_button.setMaximumWidth(96)
            self.floating_lyrics_button.clicked.connect(self.toggle_floating_lyrics)
        else:
            old_parent = existing_button.parentWidget()

            if old_parent is not None:
                old_layout = old_parent.layout()

                if old_layout is not None:
                    old_layout.removeWidget(existing_button)

                existing_button.setParent(None)

        button = self.floating_lyrics_button

        def layout_contains_widget(layout, target_widget) -> bool:
            if layout is None or target_widget is None:
                return False

            for index in range(layout.count()):
                item = layout.itemAt(index)

                if item is None:
                    continue

                widget = item.widget()

                if widget is target_widget:
                    return True

                child_layout = item.layout()

                if child_layout is not None and layout_contains_widget(child_layout, target_widget):
                    return True

            return False

        def direct_widget_index(layout, target_widget) -> int:
            if layout is None or target_widget is None:
                return -1

            for index in range(layout.count()):
                item = layout.itemAt(index)

                if item is not None and item.widget() is target_widget:
                    return index

            return -1

        def find_button_by_text(text_candidates):
            for candidate_button in self.findChildren(QPushButton):
                text = candidate_button.text().strip()

                for candidate in text_candidates:
                    if candidate in text:
                        return candidate_button

            return None

        play_mode_button = getattr(self, "play_mode_button", None)

        if play_mode_button is None:
            play_mode_button = find_button_by_text(["顺序播放", "列表循环", "单曲循环", "随机播放"])

        like_button = getattr(self, "like_button", None)

        if like_button is None:
            like_button = find_button_by_text(["收藏", "已收藏"])

        target_layout = None
        anchor_widget = None

        for anchor in (play_mode_button, like_button):
            widget = anchor

            while widget is not None:
                parent = widget.parentWidget()

                if parent is None:
                    break

                layout = parent.layout()

                if layout is not None and layout_contains_widget(layout, anchor):
                    layout_name = layout.__class__.__name__.lower()

                    if "box" in layout_name and "vbox" not in layout_name:
                        target_layout = layout
                        anchor_widget = anchor
                        break

                    if target_layout is None:
                        target_layout = layout
                        anchor_widget = anchor

                widget = parent

            if target_layout is not None and "vbox" not in target_layout.__class__.__name__.lower():
                break

        if target_layout is None:
            print("没有找到适合放桌面歌词按钮的底部横向布局，仍可用 Ctrl+Shift+D 打开。")
            return

        insert_index = direct_widget_index(target_layout, anchor_widget)

        if insert_index >= 0 and hasattr(target_layout, "insertWidget"):
            target_layout.insertWidget(insert_index + 1, button)
        else:
            target_layout.addWidget(button)

        self.update_floating_lyrics_button_state()

    def update_floating_lyrics_button_state(self) -> None:
        button = getattr(self, "floating_lyrics_button", None)

        if button is None:
            return

        window = getattr(self, "floating_lyrics_window", None)
        is_active = window is not None and window.isVisible()

        if is_active:
            button.setText("桌面歌词开")
            button.setStyleSheet(
                "QPushButton#floatingLyricsToggleButton { background: #3b82f6; color: #ffffff; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; font-weight: 700; }"
                "QPushButton#floatingLyricsToggleButton:hover { background: #5594ff; }"
            )
        else:
            button.setText("桌面歌词")
            button.setStyleSheet(
                "QPushButton#floatingLyricsToggleButton { background: rgba(255,255,255,0.075); color: #dfe4ee; border: none; border-radius: 12px; padding: 8px 12px; font-size: 13px; }"
                "QPushButton#floatingLyricsToggleButton:hover { background: rgba(255,255,255,0.13); color: #ffffff; }"
            )

    def install_floating_lyrics_feature(self) -> None:
        if not hasattr(self, "floating_lyrics_window"):
            self.floating_lyrics_window = None

        if not hasattr(self, "floating_lyrics_shortcut"):
            self.floating_lyrics_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
            self.floating_lyrics_shortcut.activated.connect(self.toggle_floating_lyrics)

        if not hasattr(self, "floating_lyrics_timer"):
            self.floating_lyrics_timer = QTimer(self)
            self.floating_lyrics_timer.timeout.connect(self.sync_floating_lyrics)
            self.floating_lyrics_timer.start(220)

    def toggle_floating_lyrics(self) -> None:
        if self.floating_lyrics_window is not None and self.floating_lyrics_window.isVisible():
            self.floating_lyrics_window.close()
            self.floating_lyrics_window = None
            return

        self.show_floating_lyrics()

    def auto_open_floating_lyrics_if_enabled(self) -> None:
        if bool(self.get_user_setting("floating_lyrics_auto_open", False)):
            self.show_floating_lyrics()

    def reset_floating_lyrics_position_settings(self) -> None:
        self.save_hush_settings(
            {
                "floating_lyrics_x": None,
                "floating_lyrics_y": None,
            }
        )

        window = getattr(self, "floating_lyrics_window", None)

        if window is not None:
            x, y = self.get_default_floating_lyrics_position(window)
            window.move(x, y)
            window.save_preferences()

    def show_floating_lyrics(self) -> None:
        if self.floating_lyrics_window is None:
            self.floating_lyrics_window = FloatingLyricsWindow(self)

        self.sync_floating_lyrics()
        self.position_floating_lyrics_window(self.floating_lyrics_window)

        self.floating_lyrics_window.show()
        self.floating_lyrics_window.raise_()

    def get_default_floating_lyrics_position(self, window: QWidget) -> tuple[int, int]:
        screen = QApplication.primaryScreen()

        if screen:
            geometry = screen.availableGeometry()
            width = window.width()
            height = window.height()
            x = geometry.x() + (geometry.width() - width) // 2
            y = geometry.y() + geometry.height() - height - 80
            return x, y

        return 100, 100

    def is_floating_lyrics_position_visible(self, x: int, y: int, window: QWidget) -> bool:
        width = max(80, window.width())
        height = max(40, window.height())

        for screen in QApplication.screens():
            geometry = screen.availableGeometry()

            if (
                x + width > geometry.x()
                and x < geometry.x() + geometry.width()
                and y + height > geometry.y()
                and y < geometry.y() + geometry.height()
            ):
                return True

        return False

    def position_floating_lyrics_window(self, window: QWidget) -> None:
        raw_x = self.get_user_setting("floating_lyrics_x", None)
        raw_y = self.get_user_setting("floating_lyrics_y", None)

        try:
            x = int(raw_x)
            y = int(raw_y)
        except (TypeError, ValueError):
            x, y = self.get_default_floating_lyrics_position(window)

        if not self.is_floating_lyrics_position_visible(x, y, window):
            x, y = self.get_default_floating_lyrics_position(window)

        window.move(x, y)

    def get_lyric_context_by_position(self, position: int, lyrics: list[tuple[int, str]]) -> tuple[str, str, str]:
        if not lyrics:
            return "", "暂无歌词", ""

        current_index = 0

        for index, (start_time, line_text) in enumerate(lyrics):
            if position >= start_time:
                current_index = index
            else:
                break

        previous_line = ""
        current_line = lyrics[current_index][1]
        next_line = ""

        if current_index > 0:
            previous_line = lyrics[current_index - 1][1]

        if current_index + 1 < len(lyrics):
            next_line = lyrics[current_index + 1][1]

        return previous_line, current_line, next_line

    def sync_floating_lyrics(self) -> None:
        window = getattr(self, "floating_lyrics_window", None)

        if window is None or not window.isVisible():
            return

        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            if (
                self.displayed_lyrics_track_key == current.stable_identity
                and self.current_lyrics
            ):
                previous_line, current_line, next_line = self.get_lyric_context_by_position(
                    self.media_player.position(), self.current_lyrics
                )
                window.set_lines(previous_line, current_line, next_line)
            elif self.current_plain_lyrics:
                window.set_lines("", current.title, "纯文本歌词请在歌词页查看")
            else:
                window.set_lines("", current.title, "当前在线歌曲暂无同步歌词")
            return

        current_song_path = self.normalize_song_path(getattr(self, "current_song_path", ""))
        displayed_lyrics_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if not current_song_path:
            window.set_lines("", "还没有播放音乐", "播放一首歌后，这里会显示桌面歌词")
            return

        if displayed_lyrics_path != current_song_path or not getattr(self, "current_lyrics", None):
            title, artist_album, status = self.get_playing_song_display_data()
            window.set_lines("", title, "当前歌曲暂无同步歌词")
            return

        position = self.media_player.position()
        previous_line, current_line, next_line = self.get_lyric_context_by_position(
            position,
            self.current_lyrics,
        )
        window.set_lines(previous_line, current_line, next_line)

    def install_playlist_button_hook(self) -> None:
        button = getattr(self, "playlist_nav_button", None)

        if button is None:
            return

        if not button.property("hushPlaylistHooked"):
            try:
                button.clicked.disconnect()
            except Exception:
                pass

            button.clicked.connect(self.show_play_queue)
            button.setProperty("hushPlaylistHooked", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.update_play_queue_nav_badge()

    def update_play_queue_nav_badge(self) -> None:
        button = getattr(self, "playlist_nav_button", None)

        if button is None:
            return

        queue = getattr(self, "play_queue", [])
        count = len(queue) if isinstance(queue, list) else 0

        if count > 0:
            button.setText(f"播放列表 ({count})")
        else:
            button.setText("播放列表")

    def install_settings_button_hook(self) -> None:
        button = getattr(self, "settings_nav_button", None)

        if button is None or button.property("hushSettingsHooked"):
            return

        try:
            button.clicked.disconnect()
        except Exception:
            pass

        button.clicked.connect(self.open_settings_dialog)
        button.setProperty("hushSettingsHooked", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

    def clear_missing_cache_files(self) -> int:
        removed_count = 0
        cache_dirs = []

        for attr_name in ("cover_cache_dir", "lyrics_cache_dir"):
            cache_dir = getattr(self, attr_name, None)

            if cache_dir:
                cache_dirs.append(Path(cache_dir))

        for cache_dir in cache_dirs:
            if not cache_dir.exists():
                continue

            for missing_file in cache_dir.glob("*.missing"):
                try:
                    missing_file.unlink()
                    removed_count += 1
                except Exception as error:
                    print("删除失败缓存失败：", missing_file, error)

        return removed_count

    def load_play_queue(self) -> list[PlaybackQueueItem]:
        if not self.play_queue_file.exists():
            return []

        try:
            with self.play_queue_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            queue: list[PlaybackQueueItem] = []
            for value in data:
                queue_item = self.playback_queue_item_from_value(value)
                if queue_item is None:
                    continue
                if queue_item.kind == "local" and not Path(queue_item.local_path).is_file():
                    continue
                queue.append(queue_item)

            return queue

        except Exception as error:
            print("读取播放队列失败：", error)
            return []

    def save_play_queue(self) -> None:
        try:
            self.play_queue_file.parent.mkdir(parents=True, exist_ok=True)

            with self.play_queue_file.open("w", encoding="utf-8") as file:
                json.dump(
                    [item.to_storage_value() for item in self.play_queue],
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            print("播放队列已保存：", self.play_queue_file)

        except Exception as error:
            print("保存播放队列失败：", error)

        try:
            self.update_play_queue_nav_badge()
        except Exception:
            pass

    def get_song_title_for_queue(self, value) -> str:
        queue_item = self.playback_queue_item_from_value(value)
        if queue_item is None:
            return "未知歌曲"
        media_item = queue_item.media_item
        if queue_item.kind == "local" and hasattr(self, "song_list"):
            song_data = self.find_song_data_by_path(queue_item.local_path)
            if isinstance(song_data, dict):
                media_item = MediaItem.from_local(song_data)
        return f"{media_item.title} - {media_item.artist}"

    def queue_media_item(
        self,
        value,
        *,
        insert_next: bool = False,
        notify_user: bool = True,
    ) -> bool:
        queue_item = self.playback_queue_item_from_value(value)
        if queue_item is None:
            if notify_user:
                QMessageBox.information(self, "提示", "这首歌没有可用的播放信息。")
            return False
        if queue_item.kind == "local" and not Path(queue_item.local_path).is_file():
            if notify_user:
                QMessageBox.information(self, "提示", "这个音乐文件已经不存在。")
            return False
        if insert_next:
            self.play_queue.insert(0, queue_item)
            action_text = "已设为下一首播放"
        else:
            self.play_queue.append(queue_item)
            action_text = "已加入播放队列"
        self.save_play_queue()
        if hasattr(self, "play_queue_page_list"):
            self.refresh_play_queue_page()
        song_text = self.get_song_title_for_queue(queue_item)
        print(f"{action_text}：{song_text}")
        if notify_user:
            QMessageBox.information(self, "播放队列", f"{action_text}\n\n{song_text}")
        return True

    def queue_song_path(self, song_path: str | None, insert_next: bool = False) -> None:
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path:
            QMessageBox.information(self, "提示", "这首歌没有有效文件路径。")
            return

        if not Path(normalized_path).exists():
            QMessageBox.information(self, "提示", "这个音乐文件已经不存在。")
            return

        self.queue_media_item(normalized_path, insert_next=insert_next)

    def queue_selected_song_next(self, selected_item=None) -> None:
        item = selected_item or self.song_list.currentItem()

        if not item:
            QMessageBox.information(self, "提示", "请先选择一首歌。")
            return

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "提示", "请选择一首真实歌曲。")
            return

        queue_item = self.playback_queue_item_from_song_data(song_data)
        if queue_item is not None:
            self.queue_media_item(queue_item, insert_next=True)

    def queue_selected_song_last(self, selected_item=None) -> None:
        item = selected_item or self.song_list.currentItem()

        if not item:
            QMessageBox.information(self, "提示", "请先选择一首歌。")
            return

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            QMessageBox.information(self, "提示", "请选择一首真实歌曲。")
            return

        queue_item = self.playback_queue_item_from_song_data(song_data)
        if queue_item is not None:
            self.queue_media_item(queue_item, insert_next=False)

    def get_main_stack_widget(self):
        possible_names = [
            "content_stack",
            "main_stack",
            "page_stack",
            "stacked_widget",
            "stack",
            "center_stack",
        ]

        for name in possible_names:
            stack = getattr(self, name, None)

            if isinstance(stack, QStackedWidget):
                return stack

        stacks = self.findChildren(QStackedWidget)

        if not stacks:
            return None

        stacks.sort(key=lambda item: item.count(), reverse=True)
        return stacks[0]

    def ensure_play_queue_page(self) -> None:
        if hasattr(self, "play_queue_page") and self.play_queue_page is not None:
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            QMessageBox.information(self, "播放列表", "没有找到主页面容器，暂时无法切换到播放列表页面。")
            return

        self.play_queue_page = QFrame()
        self.play_queue_page.setObjectName("playQueuePage")

        layout = QVBoxLayout(self.play_queue_page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(6)

        title = QLabel("播放列表")
        title.setObjectName("playQueuePageTitle")

        subtitle = QLabel("这里显示接下来会优先播放的歌曲。右键音乐库里的歌曲，可以选择“下一首播放”或“加入播放队列”。")
        subtitle.setObjectName("playQueuePageSubtitle")
        subtitle.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.play_queue_back_btn = QPushButton("返回音乐库")
        self.play_queue_back_btn.setObjectName("playQueuePageSecondaryButton")
        self.play_queue_back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_queue_back_btn.clicked.connect(self.return_from_play_queue_page)

        header.addLayout(title_box, 1)
        header.addWidget(self.play_queue_back_btn)

        self.play_queue_page_list = QListWidget()
        self.play_queue_page_list.setObjectName("playQueuePageList")
        self.play_queue_page_list.itemDoubleClicked.connect(self.play_selected_queue_page_song)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)

        self.queue_page_play_btn = QPushButton("立即播放")
        self.queue_page_play_btn.setObjectName("playQueuePagePrimaryButton")
        self.queue_page_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_play_btn.clicked.connect(self.play_selected_queue_page_song)

        self.queue_page_remove_btn = QPushButton("移除")
        self.queue_page_remove_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_remove_btn.clicked.connect(self.remove_selected_queue_page_song)

        self.queue_page_up_btn = QPushButton("上移")
        self.queue_page_up_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_up_btn.clicked.connect(self.move_selected_queue_page_song_up)

        self.queue_page_down_btn = QPushButton("下移")
        self.queue_page_down_btn.setObjectName("playQueuePageSecondaryButton")
        self.queue_page_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_down_btn.clicked.connect(self.move_selected_queue_page_song_down)

        self.queue_page_clear_btn = QPushButton("清空队列")
        self.queue_page_clear_btn.setObjectName("playQueuePageDangerButton")
        self.queue_page_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_page_clear_btn.clicked.connect(self.clear_queue_from_page)

        button_row.addWidget(self.queue_page_play_btn)
        button_row.addWidget(self.queue_page_remove_btn)
        button_row.addWidget(self.queue_page_up_btn)
        button_row.addWidget(self.queue_page_down_btn)
        button_row.addStretch(1)
        button_row.addWidget(self.queue_page_clear_btn)

        self.play_queue_page_hint = QLabel("播放队列为空。")
        self.play_queue_page_hint.setObjectName("playQueuePageHint")
        self.play_queue_page_hint.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(self.play_queue_page_list, 1)
        layout.addLayout(button_row)
        layout.addWidget(self.play_queue_page_hint)

        self.play_queue_page.setStyleSheet(
            "QFrame#playQueuePage { background: transparent; color: #e8ecf5; }"
            "QLabel#playQueuePageTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#playQueuePageSubtitle { color: #8f98aa; font-size: 13px; }"
            "QLabel#playQueuePageHint { color: #8f98aa; font-size: 12px; }"
            "QListWidget#playQueuePageList { background: #11131a; color: #e8ecf5; border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 8px; outline: none; }"
            "QListWidget#playQueuePageList::item { padding: 13px 12px; border-radius: 12px; margin: 3px; }"
            "QListWidget#playQueuePageList::item:hover { background: rgba(255,255,255,0.07); }"
            "QListWidget#playQueuePageList::item:selected { background: #3b82f6; color: #ffffff; }"
            "QPushButton#playQueuePagePrimaryButton { background: #3b82f6; color: #ffffff; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; font-weight: 700; }"
            "QPushButton#playQueuePagePrimaryButton:hover { background: #5594ff; }"
            "QPushButton#playQueuePageSecondaryButton { background: rgba(255,255,255,0.07); color: #dfe4ee; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#playQueuePageSecondaryButton:hover { background: rgba(255,255,255,0.11); color: #ffffff; }"
            "QPushButton#playQueuePageDangerButton { background: rgba(239,68,68,0.15); color: #ffd7dd; border: none; border-radius: 12px; padding: 10px 16px; font-size: 13px; }"
            "QPushButton#playQueuePageDangerButton:hover { background: rgba(239,68,68,0.26); color: #ffffff; }"
        )

        stack.addWidget(self.play_queue_page)

    def show_play_queue_page(self) -> None:
        self.set_sidebar_active("playlists")
        self.ensure_play_queue_page()

        if not hasattr(self, "play_queue_page") or self.play_queue_page is None:
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            return

        self.play_queue_previous_stack_index = stack.currentIndex()

        if hasattr(self, "set_right_panel_mode"):
            self.set_right_panel_mode("normal")

        self.refresh_play_queue_page()
        stack.setCurrentWidget(self.play_queue_page)

    def return_from_play_queue_page(self) -> None:
        if hasattr(self, "show_library_page"):
            self.show_library_page()
            return

        stack = self.get_main_stack_widget()

        if stack is None:
            return

        previous_index = getattr(self, "play_queue_previous_stack_index", 0)

        if previous_index < 0 or previous_index >= stack.count():
            previous_index = 0

        stack.setCurrentIndex(previous_index)

    def refresh_play_queue_page(self) -> None:
        if not hasattr(self, "play_queue_page_list"):
            return
        if not hasattr(self, "play_queue"):
            self.play_queue = []
        valid_queue: list[PlaybackQueueItem] = []
        for value in self.play_queue:
            queue_item = self.playback_queue_item_from_value(value)
            if queue_item is None:
                continue
            if queue_item.kind == "local" and not Path(queue_item.local_path).is_file():
                continue
            valid_queue.append(queue_item)
        if valid_queue != self.play_queue:
            self.play_queue = valid_queue
            self.save_play_queue()
        self.play_queue_page_list.clear()
        for index, queue_item in enumerate(self.play_queue, start=1):
            media_item = queue_item.media_item
            kind_text = (
                f"{media_item.source_name} · 在线"
                if queue_item.kind == "remote"
                else "本地"
            )
            item = QListWidgetItem(
                f"{index}. {media_item.title} - {media_item.artist}  [{kind_text}]"
            )
            item.setData(Qt.ItemDataRole.UserRole, queue_item.to_mapping())
            self.play_queue_page_list.addItem(item)
        if self.play_queue_page_list.count() > 0 and self.play_queue_page_list.currentRow() < 0:
            self.play_queue_page_list.setCurrentRow(0)
        count = self.play_queue_page_list.count()
        if count == 0:
            self.play_queue_page_hint.setText(
                "播放队列是空的。可在本地或在线歌曲右键菜单选择“下一首播放”。"
            )
        else:
            self.play_queue_page_hint.setText(
                f"队列里有 {count} 首歌。本地和在线歌曲会按当前顺序播放。"
            )
        self.update_play_queue_nav_badge()

    def get_selected_queue_page_index(self) -> int:
        if not hasattr(self, "play_queue_page_list"):
            return -1
        row = self.play_queue_page_list.currentRow()
        total = len(self.play_queue)
        if row < 0 or row >= total:
            QMessageBox.information(self, "播放列表", "请先选择播放列表里的一首歌。")
            return -1
        return row

    def play_selected_queue_page_song(self) -> None:
        row = self.get_selected_queue_page_index()
        if row < 0:
            return
        queue_item = self.play_queue.pop(row)
        self.save_play_queue()
        self.remember_queue_return_state()
        if not self.play_queue_item(queue_item, update_context=False):
            QMessageBox.information(self, "播放列表", "这首歌无法播放，可能文件已经不存在。")
        self.refresh_play_queue_page()

    def remove_selected_queue_page_song(self) -> None:
        row = self.get_selected_queue_page_index()
        if row < 0:
            return
        self.play_queue.pop(row)
        self.save_play_queue()
        self.refresh_play_queue_page()
        if self.play_queue_page_list.count() > 0:
            self.play_queue_page_list.setCurrentRow(
                min(row, self.play_queue_page_list.count() - 1)
            )

    def move_selected_queue_page_song_up(self) -> None:
        row = self.get_selected_queue_page_index()
        if row <= 0:
            return
        self.play_queue[row - 1], self.play_queue[row] = (
            self.play_queue[row],
            self.play_queue[row - 1],
        )
        self.save_play_queue()
        self.refresh_play_queue_page()
        self.play_queue_page_list.setCurrentRow(row - 1)

    def move_selected_queue_page_song_down(self) -> None:
        row = self.get_selected_queue_page_index()
        if row < 0:
            return
        if row >= len(self.play_queue) - 1:
            return
        self.play_queue[row + 1], self.play_queue[row] = (
            self.play_queue[row],
            self.play_queue[row + 1],
        )
        self.save_play_queue()
        self.refresh_play_queue_page()
        self.play_queue_page_list.setCurrentRow(row + 1)
    def clear_queue_from_page(self) -> None:
        if not self.play_queue:
            QMessageBox.information(self, "播放列表", "播放列表已经是空的。")
            return

        reply = QMessageBox.question(
            self,
            "清空播放列表",
            "确定要清空当前播放列表吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.play_queue.clear()
        self.save_play_queue()
        self.refresh_play_queue_page()

    def show_play_queue(self) -> None:
        self.show_play_queue_page()

    def clear_play_queue(self) -> None:
        if not hasattr(self, "play_queue"):
            self.play_queue = []

        if not self.play_queue:
            QMessageBox.information(self, "播放队列", "播放队列已经是空的。")
            self.save_play_queue()
            return

        self.play_queue.clear()
        self.save_play_queue()
        QMessageBox.information(self, "播放队列", "播放队列已清空。")
        print("播放队列已清空")

    def play_song_from_queue_path(self, song_path: str) -> bool:
        queue_item = self.playback_queue_item_from_value(song_path)
        if queue_item is None:
            return False
        self.remember_queue_return_state()
        return self.play_queue_item(queue_item, update_context=False)

    def play_next_queued_song(self) -> bool:
        if not hasattr(self, "play_queue"):
            self.play_queue = []

        if not self.play_queue:
            return False

        while self.play_queue:
            queue_item = self.play_queue.pop(0)
            self.remember_queue_return_state()
            if self.play_queue_item(queue_item, update_context=False):
                self.save_play_queue()
                return True

        self.save_play_queue()
        return False

    def remember_queue_return_state(self) -> None:
        if isinstance(self.queue_return_state, dict):
            return

        ordered_items = self.get_playback_context_items()
        if not ordered_items:
            return
        anchor_identity = self.playback_queue.current_identity
        anchor_index = self.playback_queue.current_index
        if not anchor_identity or anchor_index < 0:
            return

        self.queue_return_state = {
            "anchor_identity": anchor_identity,
            "anchor_index": anchor_index,
        }
        print("已记录队列返回位置：", anchor_identity)

    def resume_playback_context_after_queue(self) -> bool:
        state = self.queue_return_state

        if not isinstance(state, dict):
            return False

        ordered_items = self.get_playback_context_items()
        anchor_identity = str(state.get("anchor_identity") or "")
        if self.playback_queue.index_for_identity(anchor_identity) < 0:
            try:
                anchor_index = int(state.get("anchor_index", -1))
            except (TypeError, ValueError):
                anchor_index = -1

            if 0 <= anchor_index < len(ordered_items):
                anchor_identity = ordered_items[anchor_index].stable_identity
            else:
                anchor_identity = ""

        self.queue_return_state = None

        if not anchor_identity:
            print("队列已结束，但原播放上下文返回位置不可用。")
            return False
        self.playback_queue.set_current_identity(anchor_identity)
        print("队列已结束，返回原播放上下文：", anchor_identity)
        return self.play_from_playback_context(
            1,
            respect_single_loop=False,
        )

    def load_playback_session(self) -> dict:
        if not self.playback_session_file.exists():
            return {}

        try:
            with self.playback_session_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                return data

            return {}

        except Exception as error:
            print("读取上次播放状态失败：", error)
            return {}

    def request_save_playback_session(self) -> None:
        if not hasattr(self, "playback_save_timer"):
            self.save_playback_session()
            return

        self.playback_save_timer.start()
    def save_playback_session(self) -> None:
        if not hasattr(self, "media_player"):
            return

        current_path = self.normalize_song_path(getattr(self, "current_song_path", ""))

        if not current_path:
            return

        try:
            position = int(self.media_player.position())
        except Exception:
            position = 0

        pending_position = int(getattr(self, "pending_restore_position", 0) or 0)

        if pending_position > 0:
            position = pending_position

        session = {
            "path": current_path,
            "position": position,
            "saved_at": int(time.time()),
            "library_view": getattr(self, "current_library_view", "all"),
        }

        context = self.get_playback_context_for_session()

        if context:
            session["playback_context"] = context

        try:
            self.playback_session_file.parent.mkdir(parents=True, exist_ok=True)

            with self.playback_session_file.open("w", encoding="utf-8") as file:
                json.dump(session, file, ensure_ascii=False, indent=2)
        except Exception as error:
            print("保存播放会话失败：", error)

    def get_playback_context_for_session(self) -> dict | None:
        context = self.playback_context

        if not isinstance(context, dict):
            return None

        ordered_paths = self.get_playback_context_paths()

        if not ordered_paths:
            return None

        current_path = self.normalize_song_path(self.current_song_path)

        if current_path in ordered_paths:
            current_index = ordered_paths.index(current_path)
        else:
            try:
                current_index = int(context.get("current_index", 0))
            except (TypeError, ValueError):
                current_index = 0

            current_index = max(0, min(current_index, len(ordered_paths) - 1))

        return {
            "source_type": str(context.get("source_type", "library") or "library"),
            "source_id": str(context.get("source_id", "all") or "all"),
            "ordered_paths": ordered_paths,
            "current_index": current_index,
        }

    def restore_playback_context_from_session(
        self,
        raw_context,
        current_path: str,
    ) -> None:
        started_at = time.perf_counter()

        if not isinstance(raw_context, dict):
            self.create_playback_context(current_path)
            print(
                f"[startup] 恢复播放上下文（回退当前视图）："
                f"{(time.perf_counter() - started_at) * 1000:.1f} ms"
            )
            return

        raw_paths = raw_context.get("ordered_paths", [])
        ordered_paths = []
        seen_paths = set()
        available_paths = set()

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is None:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            if song_data.get("recordKind") == "remote":
                continue

            library_path = self.normalize_song_path(song_data.get("path", ""))

            if library_path:
                available_paths.add(library_path)

        if isinstance(raw_paths, list):
            for path in raw_paths:
                normalized_path = self.normalize_song_path(path)

                if (
                    normalized_path
                    and normalized_path not in seen_paths
                    and normalized_path in available_paths
                    and Path(normalized_path).exists()
                ):
                    ordered_paths.append(normalized_path)
                    seen_paths.add(normalized_path)

        if not ordered_paths:
            self.create_playback_context(current_path)
            print(
                f"[startup] 恢复播放上下文（无有效历史路径）："
                f"{(time.perf_counter() - started_at) * 1000:.1f} ms"
            )
            return

        if current_path in ordered_paths:
            current_index = ordered_paths.index(current_path)
        else:
            try:
                current_index = int(raw_context.get("current_index", 0))
            except (TypeError, ValueError):
                current_index = 0

            current_index = max(0, min(current_index, len(ordered_paths) - 1))

        self.queue_return_state = None
        self.playback_context = {
            "source_type": str(raw_context.get("source_type", "library") or "library"),
            "source_id": str(raw_context.get("source_id", "all") or "all"),
            "ordered_paths": ordered_paths,
            "current_index": current_index,
        }
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(
            f"[startup] 恢复播放上下文：{elapsed_ms:.1f} ms, "
            f"history={len(raw_paths) if isinstance(raw_paths, list) else 0}, "
            f"restored={len(ordered_paths)}"
        )

    def apply_pending_restore_position(self) -> bool:
        position = int(getattr(self, "pending_restore_position", 0) or 0)

        if position <= 0:
            return False

        duration = int(self.media_player.duration())

        if duration <= 0:
            return False

        target_position = max(0, min(position, duration))
        self.media_player.setPosition(target_position)
        self.last_recorded_position = target_position
        print("已恢复播放进度：", target_position, "ms")
        return True

    def finalize_pending_restore_position(self) -> None:
        if int(getattr(self, "pending_restore_position", 0) or 0) <= 0:
            return

        if self.apply_pending_restore_position():
            self.pending_restore_position = 0

    def find_song_item_by_path(self, song_path: str | None):
        normalized_path = self.normalize_song_path(song_path)

        if not normalized_path:
            return None

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if not item:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            item_path = self.normalize_song_path(song_data.get("path", ""))

            if item_path == normalized_path:
                return item

        return None

    def restore_playback_session(self) -> None:
        if getattr(self, "restored_playback_session", False):
            return

        self.restored_playback_session = True

        if not bool(self.get_user_setting("restore_last_playback", True)):
            print("已按设置跳过恢复上次播放。")
            return

        session = getattr(self, "playback_session", {})

        if not isinstance(session, dict):
            return

        lookup_started_at = time.perf_counter()
        song_path = self.normalize_song_path(session.get("path", ""))

        try:
            position = max(0, int(session.get("position", 0) or 0))
        except (TypeError, ValueError):
            position = 0

        if not song_path:
            return

        if not Path(song_path).exists():
            print("上次播放的文件已经不存在：", song_path)
            return

        song_data = self.find_song_data_by_path(song_path)

        if not isinstance(song_data, dict):
            print("音乐库里没有找到上次播放歌曲：", song_path)
            return

        print(
            f"[startup] 恢复歌曲路径校验与查找："
            f"{(time.perf_counter() - lookup_started_at) * 1000:.1f} ms"
        )

        self.restore_playback_context_from_session(
            session.get("playback_context"),
            song_path,
        )
        self.pending_lazy_restore_song_data = dict(song_data)
        self.pending_restore_position = position
        ui_started_at = time.perf_counter()
        self.show_pending_playback_restore(song_data, position)
        print(
            f"[startup] 恢复歌曲信息 UI："
            f"{(time.perf_counter() - ui_started_at) * 1000:.1f} ms"
        )

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")

        print(f"已准备延迟恢复：{title} - {artist} @ {position // 1000}s")

    def show_pending_playback_restore(self, song_data: dict, position: int) -> None:
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")

        self.bottom_song_title.setText(title)
        self.bottom_song_artist.setText(artist)
        self.bottom_song_title.setToolTip(title)
        self.bottom_song_artist.setToolTip(artist)
        self.now_song_title.setText(title)
        self.now_artist.setText(f"{artist} · {album}")

        if hasattr(self, "now_stats"):
            progress_text = self.format_player_time(position)
            self.now_stats.setText(f"等待播放 · 上次进度 {progress_text}")

        if hasattr(self, "now_open_folder_btn"):
            self.now_open_folder_btn.setText("打开文件位置")
            self.now_open_folder_btn.setEnabled(True)

        self.progress_slider.setValue(0)
        self.update_current_time_display(position)
        self.update_total_time_display(0)
        self.update_like_button()

    def load_pending_playback_restore(self) -> bool:
        song_data = getattr(self, "pending_lazy_restore_song_data", None)

        if not isinstance(song_data, dict):
            return False

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path or not Path(song_path).exists():
            self.pending_lazy_restore_song_data = None
            self.pending_restore_position = 0
            print("待恢复歌曲已经不存在：", song_path)
            return False

        self.pending_lazy_restore_song_data = None
        self.restoring_playback_session = True
        started_at = time.perf_counter()

        try:
            self.load_song_for_playback(song_data)
        except Exception as error:
            self.pending_restore_position = 0
            print("延迟恢复上次播放歌曲失败：", error)
            return False
        finally:
            self.restoring_playback_session = False

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[perf] 延迟恢复媒体加载：{elapsed_ms:.1f} ms")
        return bool(self.current_song_path and self.media_player.source().isValid())

    def load_settings(self) -> dict:
        default_settings = {
            "volume": 65,
            "play_mode": "list_loop",
        }

        if not self.settings_file.exists():
            print("设置文件不存在，使用默认设置。")
            return dict(default_settings)

        try:
            with self.settings_file.open("r", encoding="utf-8") as file:
                settings = json.load(file)

            if not isinstance(settings, dict):
                print("设置文件内容不是对象，使用默认设置。")
                return dict(default_settings)

        except Exception as error:
            print("读取设置失败：", error)
            return dict(default_settings)

        try:
            volume = int(settings.get("volume", default_settings["volume"]))
        except (TypeError, ValueError):
            print("设置项 volume 类型无效，使用默认值 65。")
            volume = default_settings["volume"]
        settings["volume"] = max(0, min(100, volume))

        play_mode = settings.get("play_mode", default_settings["play_mode"])
        if not isinstance(play_mode, str) or play_mode not in {
            "sequence",
            "list_loop",
            "single_loop",
            "shuffle",
        }:
            print("设置项 play_mode 无效，使用默认值 list_loop。")
            play_mode = default_settings["play_mode"]
        settings["play_mode"] = play_mode

        integer_defaults = {
            "immersive_background_alpha": 68,
            "floating_lyrics_opacity": 100,
            "floating_lyrics_font_size": 42,
            "floating_lyrics_width": 980,
            "floating_lyrics_height": 135,
        }
        for key, default_value in integer_defaults.items():
            if key not in settings:
                continue
            try:
                settings[key] = int(settings[key])
            except (TypeError, ValueError):
                print(f"设置项 {key} 类型无效，使用默认值 {default_value}。")
                settings[key] = default_value

        if "music_scan_folders" in settings and not isinstance(
            settings["music_scan_folders"], list
        ):
            print("设置项 music_scan_folders 类型无效，使用空列表。")
            settings["music_scan_folders"] = []
        return settings

    def load_playlists(self) -> dict:
        self.playlist_membership_snapshots = {}
        self.playlists_migration_pending = False
        default_playlists = {
            "liked": {
                "name": "我喜欢",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": True,
            }
        }

        if not self.playlists_file.exists():
            self.playlists_load_error = ""
            return default_playlists

        try:
            with self.playlists_file.open("r", encoding="utf-8") as file:
                playlists = json.load(file)

            if not isinstance(playlists, dict):
                raise ValueError("歌单文件根节点不是对象")

            if "liked" not in playlists:
                playlists["liked"] = default_playlists["liked"]

            if not isinstance(playlists["liked"], dict):
                playlists["liked"] = default_playlists["liked"]

            playlists["liked"].setdefault("name", "我喜欢")
            playlists["liked"].setdefault("songs", [])
            playlists["liked"].setdefault("remoteSongs", [])
            playlists["liked"]["fixed"] = True

            if not isinstance(playlists["liked"]["songs"], list):
                playlists["liked"]["songs"] = []

            for playlist in playlists.values():
                if not isinstance(playlist, dict):
                    continue
                playlist.setdefault("remoteSongs", [])
                if not isinstance(playlist["remoteSongs"], list):
                    playlist["remoteSongs"] = []

            try:
                anchor_ms = int(self.playlists_file.stat().st_mtime * 1000)
            except OSError:
                anchor_ms = int(time.time() * 1000)
            self.playlists_migration_pending = PlaylistMembership.normalize_document(
                playlists,
                self.normalize_song_path,
                anchor_ms=anchor_ms,
            )

            self.playlists_load_error = ""
            return playlists

        except Exception as error:
            self.playlists_load_error = f"读取歌单失败，已禁止覆盖原文件：{error}"
            print(self.playlists_load_error)
            return default_playlists

    def save_playlists(self) -> bool:
        if getattr(self, "playlists_load_error", ""):
            print(self.playlists_load_error)
            if hasattr(self, "content_stack"):
                QMessageBox.warning(self, "歌单未保存", self.playlists_load_error)
            return False
        self.playlists_file.parent.mkdir(parents=True, exist_ok=True)

        if "liked" not in self.playlists:
            self.playlists["liked"] = {
                "name": "我喜欢",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": True,
            }

        PlaylistMembership.normalize_document(
            self.playlists,
            self.normalize_song_path,
        )

        temporary_path = self.playlists_file.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(self.playlists, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.playlists_file)

        self.playlists_migration_pending = False
        print("歌单已保存：", self.playlists_file)
        return True

    def persist_pending_playlist_migration(self) -> None:
        if not getattr(self, "playlists_migration_pending", False):
            return
        started_at = time.perf_counter()
        if self.save_playlists():
            print(
                "[perf] 旧歌单加入时间迁移持久化："
                f"{(time.perf_counter() - started_at) * 1000:.1f} ms"
            )

    def normalize_song_path(self, path: str | None) -> str:
        if not path:
            return ""

        try:
            return str(Path(path).resolve())
        except Exception:
            return str(path)

    def get_liked_song_paths(self) -> list[str]:
        liked_playlist = self.playlists.setdefault(
            "liked",
            {
                "name": "我喜欢",
                "songs": [],
                "remoteSongs": [],
                "members": [],
                "membershipVersion": PlaylistMembership.VERSION,
                "fixed": True,
            },
        )

        return self.get_playlist_song_paths("liked")

    def is_song_liked(self, path: str | None) -> bool:
        normalized_path = self.normalize_song_path(path)

        if not normalized_path:
            return False

        liked_songs = self.get_liked_song_paths()
        return normalized_path in liked_songs

    def update_like_button(self) -> None:
        if not hasattr(self, "like_btn"):
            return

        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            liked = bool(
                self.get_online_track_collection_state(current.to_dict()).get("liked")
            )
            self.like_btn.setText("♥ 已收藏" if liked else "♡ 收藏")
            self.like_btn.setProperty("liked", liked)
            self.like_btn.setEnabled(True)
            self.like_btn.style().unpolish(self.like_btn)
            self.like_btn.style().polish(self.like_btn)
            self.like_btn.update()
            return

        target_path = self.normalize_song_path(self.current_song_path)

        if not target_path:
            self.like_btn.setText("♡ 收藏")
            self.like_btn.setProperty("liked", False)
            self.like_btn.setEnabled(False)
        elif self.is_song_liked(target_path):
            self.like_btn.setText("♥ 已收藏")
            self.like_btn.setProperty("liked", True)
            self.like_btn.setEnabled(True)
        else:
            self.like_btn.setText("♡ 收藏")
            self.like_btn.setProperty("liked", False)
            self.like_btn.setEnabled(True)

        self.like_btn.style().unpolish(self.like_btn)
        self.like_btn.style().polish(self.like_btn)
        self.like_btn.update()

    def toggle_like_current_song(self) -> None:
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            state = self.get_online_track_collection_state(current.to_dict())
            if state.get("liked"):
                self.unlike_online_track(current.to_dict())
            else:
                self.like_online_track(current.to_dict())
            self.update_like_button()
            return

        target_path = self.normalize_song_path(self.current_song_path)

        if not target_path:
            print("当前没有可收藏的真实歌曲。")
            return

        if self.is_song_liked(target_path):
            changed = self.remove_local_path_from_playlist(target_path, "liked")
            print("已取消收藏：", target_path)
        else:
            changed = self.add_local_path_to_playlist(target_path, "liked")
            print("已加入我喜欢：", target_path)

        if not changed:
            return
        self.update_like_button()
        self.update_side_info_panel()
        self.refresh_playlist_membership_views()

    def load_song_stats(self) -> dict:
        if not self.stats_file.exists():
            return {}

        try:
            with self.stats_file.open("r", encoding="utf-8") as file:
                raw_stats = json.load(file)

            if not isinstance(raw_stats, dict):
                return {}

            cleaned_stats = {}

            for path, stats in raw_stats.items():
                if not isinstance(stats, dict):
                    continue

                normalized_path = self.normalize_song_path(path)

                if not normalized_path:
                    continue

                cleaned_stats[normalized_path] = {
                    "play_count": max(0, int(stats.get("play_count", 0))),
                    "total_listen_time": max(0, int(stats.get("total_listen_time", 0))),
                    "last_played": max(0, int(stats.get("last_played", 0))),
                }

            return cleaned_stats

        except Exception as error:
            print("读取播放统计失败：", error)
            return {}

    def save_song_stats(self) -> None:
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        with self.stats_file.open("w", encoding="utf-8") as file:
            json.dump(self.song_stats, file, ensure_ascii=False, indent=2)

        print("播放统计已保存：", self.stats_file)

    def get_song_stats(self, path: str | None) -> dict | None:
        normalized_path = self.normalize_song_path(path)

        if not normalized_path:
            return None

        if normalized_path not in self.song_stats:
            self.song_stats[normalized_path] = {
                "play_count": 0,
                "total_listen_time": 0,
                "last_played": 0,
            }

        return self.song_stats[normalized_path]

    def format_listen_time(self, seconds: int) -> str:
        seconds = max(0, int(seconds))

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"

        return f"{minutes}:{remaining_seconds:02d}"

    def update_current_song_stats_label(self) -> None:
        if not hasattr(self, "now_stats"):
            return

        target_path = self.normalize_song_path(self.current_song_path)

        if not target_path:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        stats = self.get_song_stats(target_path)

        if not stats:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        play_count = int(stats.get("play_count", 0))
        total_listen_time = int(stats.get("total_listen_time", 0))
        formatted_time = self.format_listen_time(total_listen_time)

        self.now_stats.setText(f"播放 {play_count} 次 · 累计 {formatted_time}")

    def reset_playback_stats_session(self) -> None:
        self.last_recorded_position = 0
        self.pending_listen_ms = 0
        self.current_session_listen_ms = 0
        self.play_count_marked = False

    def record_listen_progress(self, position: int) -> None:
        if not self.current_song_path:
            self.last_recorded_position = position
            return

        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.last_recorded_position = position
            return

        if self.last_recorded_position <= 0:
            self.last_recorded_position = position
            return

        delta = position - self.last_recorded_position
        self.last_recorded_position = position

        if delta <= 0:
            return

        if delta > 5000:
            return

        self.pending_listen_ms += delta
        self.current_session_listen_ms += delta

        self.mark_current_song_played_if_needed()

        if self.pending_listen_ms >= 10000:
            self.flush_current_listen_time()

    def mark_current_song_played_if_needed(self) -> None:
        if self.play_count_marked:
            return

        if not self.current_song_path:
            return

        threshold = 30000

        if self.current_duration > 0:
            threshold = min(30000, max(8000, int(self.current_duration * 0.3)))

        if self.current_session_listen_ms < threshold:
            return

        stats = self.get_song_stats(self.current_song_path)

        if not stats:
            return

        stats["play_count"] = int(stats.get("play_count", 0)) + 1
        stats["last_played"] = int(time.time())

        self.play_count_marked = True
        self.save_song_stats()
        self.request_save_playback_session()
        self.update_current_song_stats_label()
        self.update_side_info_panel()

        print("本次播放已计入播放次数：", self.current_song_path)

    def flush_current_listen_time(self) -> bool:
        if not self.current_song_path:
            self.pending_listen_ms = 0
            return False

        saved_seconds = self.pending_listen_ms // 1000
        self.pending_listen_ms = self.pending_listen_ms % 1000

        if saved_seconds <= 0:
            return False

        stats = self.get_song_stats(self.current_song_path)

        if not stats:
            return False

        stats["total_listen_time"] = int(stats.get("total_listen_time", 0)) + int(saved_seconds)
        stats["last_played"] = int(time.time())

        self.save_song_stats()
        self.update_current_song_stats_label()
        self.update_side_info_panel()

        print(f"已累计听歌时长：{saved_seconds} 秒")
        return True

    def load_lyrics_bindings(self) -> dict:
        if not self.lyrics_bindings_file.exists():
            return {}

        try:
            with self.lyrics_bindings_file.open("r", encoding="utf-8") as file:
                raw_bindings = json.load(file)

            if not isinstance(raw_bindings, dict):
                return {}

            bindings = {}

            for song_path, lyric_path in raw_bindings.items():
                normalized_song_path = self.normalize_song_path(str(song_path))
                normalized_lyric_path = self.normalize_song_path(str(lyric_path))

                if not normalized_song_path or not normalized_lyric_path:
                    continue

                if not Path(normalized_lyric_path).exists():
                    continue

                bindings[normalized_song_path] = normalized_lyric_path

            return bindings

        except Exception as error:
            print("读取歌词绑定失败：", error)
            return {}

    def save_lyrics_bindings(self) -> None:
        self.lyrics_bindings_file.parent.mkdir(parents=True, exist_ok=True)

        with self.lyrics_bindings_file.open("w", encoding="utf-8") as file:
            json.dump(self.lyrics_bindings, file, ensure_ascii=False, indent=2)

        print("歌词绑定已保存：", self.lyrics_bindings_file)

    def get_bound_lyrics_path(self, song_path: str | None) -> str:
        normalized_song_path = self.normalize_song_path(song_path)

        if not normalized_song_path:
            return ""

        lyric_path = self.lyrics_bindings.get(normalized_song_path, "")

        if not lyric_path:
            return ""

        normalized_lyric_path = self.normalize_song_path(lyric_path)

        if not Path(normalized_lyric_path).exists():
            self.lyrics_bindings.pop(normalized_song_path, None)
            self.save_lyrics_bindings()
            return ""

        return normalized_lyric_path

    def get_song_cache_path(self, song_path: str | None, cache_dir: Path, suffix: str) -> Path | None:
        normalized_song_path = self.normalize_song_path(song_path)

        if not normalized_song_path:
            return None

        digest = hashlib.sha1(normalized_song_path.lower().encode("utf-8")).hexdigest()
        return cache_dir / f"{digest}{suffix}"

    def clear_lyrics_cache_for_song(self, song_path: str | None) -> None:
        cache_path = self.get_song_cache_path(song_path, self.lyrics_cache_dir, ".lrc")

        if not cache_path:
            return

        missing_path = cache_path.with_suffix(".missing")

        for path in (cache_path, missing_path):
            try:
                if path.exists():
                    path.unlink()
                    print("已删除歌词缓存：", path)
            except Exception as error:
                print("删除歌词缓存失败：", error)

    def clear_cover_cache_for_song(self, song_path: str | None) -> None:
        cache_path = self.get_song_cache_path(song_path, self.cover_cache_dir, ".jpg")

        if not cache_path:
            return

        missing_path = cache_path.with_suffix(".missing")

        for path in (cache_path, missing_path):
            try:
                if path.exists():
                    path.unlink()
                    print("已删除封面缓存：", path)
            except Exception as error:
                print("删除封面缓存失败：", error)

    def get_selected_real_song_data(self) -> dict | None:
        item = self.song_list.currentItem()
        return self.get_song_data_from_item(item)

    def reload_selected_song_lyrics(self, ignore_binding: bool = False) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")

        self.load_lyrics_for_song(
            file_path=song_path,
            title=title,
            artist=artist,
            ignore_binding=ignore_binding,
        )

    def bind_selected_song_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            QMessageBox.information(self, "提示", "这首歌没有有效文件路径。")
            return

        lyric_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择 LRC 歌词文件",
            str(Path(song_path).parent),
            "LRC Lyrics (*.lrc);;All Files (*)",
        )

        if not lyric_file:
            return

        lyric_path = self.normalize_song_path(lyric_file)
        lyrics = self.parse_lrc_file(Path(lyric_path))

        if not lyrics:
            QMessageBox.warning(
                self,
                "歌词不可用",
                "这个 .lrc 文件没有解析出有效时间轴，请换一个带时间轴的 LRC 文件。",
            )
            return

        self.lyrics_bindings[song_path] = lyric_path
        self.save_lyrics_bindings()
        self.clear_lyrics_cache_for_song(song_path)

        if song_path == self.normalize_song_path(self.current_song_path):
            self.current_lyrics = lyrics
            self.displayed_lyrics_song_path = song_path
            self.lyrics_view.set_lyrics(self.current_lyrics)
            self.sync_full_lyrics_from_current()
            self.set_lyrics_status("已手动绑定歌词")
            self.update_side_info_panel()

        QMessageBox.information(self, "绑定成功", "已为选中歌曲绑定这个 LRC 歌词文件。")
        print("已手动绑定歌词：", song_path, "->", lyric_path)

    def unbind_selected_song_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            return

        if song_path not in self.lyrics_bindings:
            QMessageBox.information(self, "提示", "这首歌当前没有手动绑定歌词。")
            return

        self.lyrics_bindings.pop(song_path, None)
        self.save_lyrics_bindings()

        if song_path == self.normalize_song_path(self.current_song_path):
            self.set_lyrics_status("已取消手动歌词绑定")
            self.reload_selected_song_lyrics(ignore_binding=True)

        print("已取消歌词绑定：", song_path)

    def force_search_selected_lyrics(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        self.clear_lyrics_cache_for_song(song_path)
        self.reload_selected_song_lyrics(ignore_binding=True)

        print("已清除歌词缓存并重新搜索：", song_path)

    def force_search_selected_cover(self) -> None:
        song_data = self.get_selected_real_song_data()

        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))
        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")

        self.clear_cover_cache_for_song(song_path)

        if song_path == self.normalize_song_path(self.current_song_path):
            self.update_cover(
                file_path=song_path,
                title=title,
                artist=artist,
                album=album,
            )

        print("已清除封面缓存并重新搜索：", song_path)

    def save_settings(self) -> None:
        self.save_hush_settings(
            {
                "volume": max(0, min(100, int(self.current_volume))),
                "play_mode": self.play_mode,
            }
        )

    def update_bottom_player(self, song_data: dict) -> None:
        song_path = self.normalize_song_path(song_data.get("path", ""))

        if song_path != self.normalize_song_path(self.current_song_path):
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        self.bottom_song_title.setText(title)
        self.bottom_song_artist.setText(artist)
        self.bottom_song_title.setToolTip(title)
        self.bottom_song_artist.setToolTip(artist)

    def update_now_playing_panel(self, song_data: dict) -> None:
        song_path = self.normalize_song_path(song_data.get("path", ""))

        if song_path != self.normalize_song_path(self.current_song_path):
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")

        self.now_song_title.setText(title)
        self.now_artist.setText(f"{artist} · {album}")

        if hasattr(self, "now_open_folder_btn"):
            self.now_open_folder_btn.setText("打开文件位置")
            self.now_open_folder_btn.setEnabled(True)

        self.update_cover(
            file_path=song_path,
            title=title,
            artist=artist,
            album=album,
        )
        self.load_lyrics_for_song(
            file_path=song_path,
            title=title,
            artist=artist,
        )
        self.update_current_song_stats_label()
        self.update_side_info_panel()

    def set_lyrics_status(self, message: str) -> None:
        print("歌词状态：", message)

        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText(f"歌词：{message}")

        if hasattr(self, "full_lyrics_status"):
            self.full_lyrics_status.setText(message)

        if hasattr(self, "side_lyrics_status_value"):
            self.side_lyrics_status_value.setText(message)

        self.sync_immersive_lyrics()

        QApplication.processEvents()

    def on_online_lyrics_status_changed(
        self,
        generation: int,
        track_key: str,
        message: str,
    ) -> None:
        current = getattr(self, "current_media_item", None)
        if (
            generation != self.online_lyrics_service.generation
            or not isinstance(current, MediaItem)
            or current.media_type != "online"
            or current.stable_identity != track_key
        ):
            return
        if message.startswith("正在"):
            self.current_online_lyrics_state = "loading"
        self.set_lyrics_status(message)

    def on_online_lyrics_ready(
        self,
        generation: int,
        track_key: str,
        payload: dict,
    ) -> None:
        current = getattr(self, "current_media_item", None)
        if (
            generation != self.online_lyrics_service.generation
            or not isinstance(current, MediaItem)
            or current.media_type != "online"
            or current.stable_identity != track_key
        ):
            print("已忽略过期在线歌词：", track_key)
            return
        text = str(payload.get("text") or "").strip()
        lyrics_type = str(payload.get("type") or "none")
        source = str(payload.get("source") or "在线来源")
        self.current_lyrics = []
        self.current_plain_lyrics = ""
        self.displayed_lyrics_song_path = None
        self.displayed_lyrics_track_key = track_key
        if payload.get("error") or lyrics_type == "error":
            self.current_online_lyrics_state = "error"
            self.lyrics_view.set_placeholder("歌词获取失败", source)
            self.set_lyrics_status("歌词获取失败")
        elif not text or payload.get("not_found"):
            self.current_online_lyrics_state = "none"
            self.lyrics_view.set_placeholder("暂无歌词", source)
            self.set_lyrics_status("暂无歌词")
        elif lyrics_type == "lrc":
            parsed = self.parse_lrc_text(text)
            if parsed:
                self.current_online_lyrics_state = "ready"
                self.current_lyrics = parsed
                self.lyrics_view.set_lyrics(parsed)
                self.set_lyrics_status(f"时间轴歌词 · {source}")
            else:
                self.current_online_lyrics_state = "ready"
                self.current_plain_lyrics = text
                self.lyrics_view.set_plain_text(text)
                self.set_lyrics_status(f"纯文本歌词 · {source}")
        else:
            self.current_online_lyrics_state = "ready"
            self.current_plain_lyrics = text
            self.lyrics_view.set_plain_text(text)
            self.set_lyrics_status(f"纯文本歌词 · {source}")
        self.sync_full_lyrics_from_current()
        self.sync_immersive_lyrics()

    def on_online_artwork_ready(
        self,
        generation: int,
        track_key: str,
        data: bytes,
    ) -> None:
        if (
            generation != self.online_artwork_service.generation
            or track_key != self.presented_online_identity
        ):
            return
        if self.show_cover_from_bytes(data):
            self.sync_immersive_lyrics()

    def on_online_artwork_failed(
        self,
        generation: int,
        track_key: str,
        _message: str,
    ) -> None:
        if (
            generation != self.online_artwork_service.generation
            or track_key != self.presented_online_identity
        ):
            return
        self.reset_cover()

    def load_song_for_playback(
        self,
        song_data: dict | None,
        *,
        playback_generation: int | None = None,
        queue_identity: str = "",
    ) -> None:
        if not isinstance(song_data, dict):
            return

        if song_data.get("demo"):
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        file_path = song_data.get("path", "")

        if not file_path:
            return

        normalized_path = self.normalize_song_path(file_path)

        if not normalized_path:
            return

        local_media_item = MediaItem.from_local(song_data)
        identity = str(queue_identity or local_media_item.stable_identity)
        if playback_generation is None:
            playback_generation = self.begin_playback_generation(identity)
        elif playback_generation != self.playback_generation:
            return
        else:
            self.current_queue_identity = identity
            self.media_loading_generation = playback_generation

        pending_request = int(getattr(self, "pending_online_playback_request", 0) or 0)
        if pending_request:
            self.online_source_client.cancel_request(pending_request)
        self.pending_online_playback_request = 0
        self.pending_online_playback_generation = 0
        self.pending_online_playback_identity = ""
        self.pending_online_keep_target_on_failure = False
        self.pending_online_track = None
        self.cancel_pending_online_metadata()
        if self.pending_online_ui_snapshot is not None:
            self.restore_online_playback_ui_snapshot()
        else:
            self.pending_online_media_item = None
            self.presented_online_identity = ""
            self.presented_online_cover_url = ""
        self.current_track_kind = "local"
        self.current_online_track = None
        self.current_media_item = local_media_item
        self.current_plain_lyrics = ""
        self.current_online_lyrics_state = ""
        self.displayed_lyrics_track_key = ""
        self.online_lyrics_service.cancel()
        self.online_artwork_service.cancel()
        if hasattr(self, "bottom_source_badge"):
            self.bottom_source_badge.hide()
        if hasattr(self, "now_stats"):
            self.now_stats.show()

        if not getattr(self, "restoring_playback_session", False):
            self.pending_lazy_restore_song_data = None
            self.pending_restore_position = 0

        current_normalized_path = self.normalize_song_path(self.current_song_path)

        if current_normalized_path == normalized_path and self.media_player.source().toString():
            return

        self.flush_current_listen_time()

        self.current_song_path = normalized_path
        self.current_queue_identity = identity
        self.current_duration = 0
        self.reset_playback_stats_session()
        self.update_bottom_player(song_data)
        self.refresh_playing_song_indicators()

        self.media_loading_generation = playback_generation
        self.media_player.stop()
        source_started_at = time.perf_counter()
        self.media_player.setSource(QUrl.fromLocalFile(self.current_song_path))
        print(f"[perf] media_player.setSource：{(time.perf_counter() - source_started_at) * 1000:.1f} ms")
        self.progress_slider.setValue(0)
        panel_started_at = time.perf_counter()
        self.update_now_playing_panel(song_data)
        print(f"[perf] 当前播放信息初始化：{(time.perf_counter() - panel_started_at) * 1000:.1f} ms")
        self.update_like_button()

        print("已切换播放器当前歌曲：", title, "-", artist)
        self.sync_immersive_lyrics()
        print("文件路径：", self.current_song_path)
        print("已设置 source：", self.media_player.source().toString())

    def select_song(self, item: QListWidgetItem) -> None:
        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            self.browsing_song_path = None
            self.browsing_song_data = None
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        file_path = song_data.get("path", "")

        print(f"你正在浏览：{title} - {artist}")

        if song_data.get("recordKind") == "remote":
            self.browsing_song_path = self.normalize_song_path(file_path) if file_path else None
            self.browsing_song_data = song_data
            print(f"在线歌曲状态：{song_data.get('onlineStatus') or '在线'}")
            return

        if file_path:
            self.browsing_song_path = self.normalize_song_path(file_path)
            self.browsing_song_data = song_data if isinstance(song_data, dict) else None
        else:
            self.browsing_song_path = None
            self.browsing_song_data = None

        if self.browsing_song_path:
            print(f"浏览文件路径：{self.browsing_song_path}")
            print("单击只浏览，不会打断当前播放。双击才会播放这首歌。")
        else:
            print("这是演示歌曲，没有真实音乐文件。")

    def reset_now_playing_info(self) -> None:
        self.flush_current_listen_time()
        self.invalidate_media_worker_request("cover")
        self.invalidate_media_worker_request("lyrics")

        pending_request = int(getattr(self, "pending_online_playback_request", 0) or 0)
        if pending_request:
            self.online_source_client.cancel_request(pending_request)
        self.pending_online_playback_request = 0
        self.pending_online_playback_generation = 0
        self.pending_online_playback_identity = ""
        self.pending_online_keep_target_on_failure = False
        self.pending_online_track = None
        self.pending_online_media_item = None
        self.pending_online_ui_snapshot = None
        self.cancel_pending_online_metadata()
        self.presented_online_identity = ""
        self.presented_online_cover_url = ""

        self.current_song_path = None
        self.current_queue_identity = ""
        self.current_media_item = None
        self.current_track_kind = "local"
        self.current_online_track = None
        self.online_lyrics_service.cancel()
        self.online_artwork_service.cancel()
        self.pending_lazy_restore_song_data = None
        self.pending_restore_position = 0
        self.browsing_song_path = None
        self.browsing_song_data = None
        self.playback_context = None
        self.playback_queue.clear()
        self.queue_return_state = None
        self.playback_generation = int(getattr(self, "playback_generation", 0) or 0) + 1
        self.media_loading_generation = 0
        self.handled_end_generation = -1

        self.current_duration = 0
        self.current_lyrics = []
        self.current_plain_lyrics = ""
        self.current_online_lyrics_state = ""
        self.displayed_lyrics_track_key = ""

        self.reset_playback_stats_session()

        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.progress_slider.setValue(0)

        self.now_song_title.setText("还没有播放音乐")
        self.now_artist.setText("请选择一首歌曲")

        if hasattr(self, "now_stats"):
            self.now_stats.setText("播放 0 次 · 累计 0:00")

        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText("歌词：等待选择歌曲")

        if hasattr(self, "now_open_folder_btn"):
            self.now_open_folder_btn.setText("打开文件位置")
            self.now_open_folder_btn.setEnabled(False)

        self.bottom_song_title.setText("未播放")
        self.bottom_song_artist.setText("请选择一首音乐")
        if hasattr(self, "bottom_source_badge"):
            self.bottom_source_badge.hide()
        self.lyrics_view.set_placeholder("这里会显示歌词", "支持本地 .lrc 和联网同步歌词")
        self.reset_cover()
        self.update_like_button()
        self.update_side_info_panel()

    def select_first_available_song(self) -> None:
        visible_rows = self.get_visible_rows()

        if not visible_rows:
            self.reset_now_playing_info()
            return

        first_row = visible_rows[0]
        self.song_list.setCurrentRow(first_row)
        first_item = self.song_list.item(first_row)

        if first_item:
            self.select_song(first_item)

    def remove_selected_song(self) -> None:
        self.remove_selected_songs_from_library()

    def remove_songs_from_playlists_and_queue(self, removed_paths: set[str]) -> None:
        if not removed_paths:
            return

        previous_playlists = deepcopy(self.playlists)
        playlists_changed = False

        for playlist in self.playlists.values():
            if not isinstance(playlist, dict):
                continue

            for path in removed_paths:
                playlists_changed = PlaylistMembership.remove_member(
                    playlist,
                    PlaylistMembership.LOCAL,
                    path,
                    self.normalize_song_path,
                ) or playlists_changed

        if playlists_changed:
            self.invalidate_playlist_membership_snapshot()
            if self.save_playlists():
                self.mark_library_list_dirty()
                self.refresh_playlist_view_buttons()
            else:
                self.playlists = previous_playlists
                self.invalidate_playlist_membership_snapshot()

        if isinstance(getattr(self, "play_queue", None), list):
            cleaned_queue = [
                item
                for item in self.play_queue
                if not (
                    item.kind == "local"
                    and self.normalize_song_path(item.local_path) in removed_paths
                )
            ]

            if cleaned_queue != self.play_queue:
                self.play_queue = cleaned_queue
                self.save_play_queue()
                self.refresh_play_queue_page()

    def remove_selected_songs_from_library(self) -> None:
        selected_items = self.get_selected_song_items() if hasattr(self, "get_selected_song_items") else []

        if not selected_items:
            QMessageBox.information(self, "从音乐库移除歌曲", "请先选择要从音乐库移除的歌曲。")
            return

        songs_to_remove = []
        removed_paths = set()

        for item in selected_items:
            song_data = self.get_song_data_from_item(item)

            if not song_data:
                continue

            song_path = self.normalize_song_path(song_data.get("path", ""))

            if song_path and song_path not in removed_paths:
                songs_to_remove.append((item, song_path))
                removed_paths.add(song_path)

        if not songs_to_remove:
            QMessageBox.information(self, "从音乐库移除歌曲", "没有可移除的真实歌曲。")
            return

        count = len(songs_to_remove)
        reply = QMessageBox.question(
            self,
            "从音乐库移除歌曲",
            f"确定要从音乐库移除选中的 {count} 首歌曲吗？\n这不会删除硬盘上的音乐文件。",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        rows = sorted({self.song_list.row(item) for item, _ in songs_to_remove}, reverse=True)

        for row in rows:
            if row >= 0:
                taken_item = self.song_list.takeItem(row)

                if taken_item:
                    del taken_item

        current_removed = self.normalize_song_path(self.current_song_path) in removed_paths

        self.remove_songs_from_playlists_and_queue(removed_paths)

        if current_removed:
            self.reset_now_playing_info()

        self.mark_library_list_dirty()
        self.filter_song_list(self.search_input.text())
        self.save_music_library()
        self.update_like_button()
        self.update_side_info_panel()
        self.update_view_buttons()

        print(f"已从音乐库移除 {count} 首歌曲；未删除硬盘文件。")

    def clean_missing_songs(self) -> None:
        removed_count = 0
        removed_current_song = False

        for row in range(self.song_list.count() - 1, -1, -1):
            item = self.song_list.item(row)
            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict):
                continue

            if song_data.get("demo") or song_data.get("recordKind") == "remote":
                continue

            path_text = song_data.get("path", "")

            if not path_text:
                continue

            path = Path(path_text)

            if path.exists():
                continue

            print("清理失效歌曲：", item.text())
            print("失效路径：", path_text)

            if self.current_song_path:
                try:
                    if Path(self.current_song_path).resolve() == path.resolve():
                        removed_current_song = True
                except Exception:
                    if self.current_song_path == path_text:
                        removed_current_song = True

            taken_item = self.song_list.takeItem(row)

            if taken_item:
                del taken_item

            removed_count += 1

        self.filter_song_list(self.search_input.text())
        self.save_music_library()

        if removed_current_song:
            self.reset_now_playing_info()

        if self.song_list.count() == 0:
            self.add_demo_songs()
            self.save_music_library()
            self.reset_now_playing_info()
        else:
            current_item = self.song_list.currentItem()

            if current_item is None or current_item.isHidden():
                self.select_first_available_song()

        print(f"清理完成，移除失效歌曲数量：{removed_count}")

    def reset_cover(self) -> None:
        self.cover_label.clear()
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setText("Hush")

    def cleanup_thread_reference(self, thread: QThread, kind: str) -> None:
        try:
            if kind == "music_scan" and thread in self.music_scan_threads:
                self.music_scan_threads.remove(thread)
        except Exception:
            pass

    def cleanup_worker_reference(self, worker: QObject, kind: str) -> None:
        try:
            if kind == "music_scan" and worker in self.music_scan_workers:
                self.music_scan_workers.remove(worker)
        except Exception:
            pass

    def _media_lifecycle_collections(self, kind: str):
        if kind == "cover":
            return (
                self.cover_workers,
                self.cover_threads,
                self.retiring_cover_workers,
                self.retiring_cover_threads,
            )
        if kind == "lyrics":
            return (
                self.lyrics_workers,
                self.lyrics_threads,
                self.retiring_lyrics_workers,
                self.retiring_lyrics_threads,
            )
        raise ValueError(f"未知媒体 worker 类型：{kind}")

    def _trace_media_lifecycle(self, stage: str, token: str) -> None:
        callback = getattr(self, "_media_lifecycle_trace", None)
        if callable(callback):
            callback(stage, token)

    @staticmethod
    def media_worker_request_matches(
        request: dict | None,
        file_path: str,
        title: str,
        artist: str,
        album: str,
    ) -> bool:
        if not isinstance(request, dict):
            return False
        return (
            request.get("file_path") == file_path
            and request.get("title") == title
            and request.get("artist") == artist
            and request.get("album") == album
        )

    @staticmethod
    def media_thread_is_running(thread: QThread) -> bool:
        try:
            return thread.isRunning()
        except RuntimeError:
            return False

    def cancel_media_workers(self, kind: str) -> None:
        try:
            workers, threads, _retiring_workers, _retiring_threads = (
                self._media_lifecycle_collections(kind)
            )
        except ValueError:
            return

        for token, worker in tuple(workers.items()):
            record = self._media_lifecycle_records.get(token, {})
            if record.get("worker_destroyed"):
                continue
            try:
                worker.cancel()
            except (AttributeError, RuntimeError):
                pass

        for token, thread in tuple(threads.items()):
            record = self._media_lifecycle_records.get(token, {})
            if record.get("thread_finished") or record.get("thread_destroyed"):
                continue
            try:
                thread.requestInterruption()
                thread.quit()
            except RuntimeError:
                pass

    def invalidate_media_worker_request(self, kind: str) -> None:
        if kind == "cover":
            self.cover_request_id += 1
            self.active_cover_request_id = str(self.cover_request_id)
            self._pending_cover_request = None
        elif kind == "lyrics":
            self.lyrics_request_id += 1
            self.active_lyrics_request_id = str(self.lyrics_request_id)
            self._pending_lyrics_request = None
        else:
            return
        self.cancel_media_workers(kind)

    def _register_media_worker(
        self,
        kind: str,
        request_id: str,
        worker: QObject,
        thread: QThread,
    ) -> str:
        expected_type = CoverSearchWorker if kind == "cover" else LyricsSearchWorker
        if not isinstance(worker, expected_type):
            raise TypeError(f"{kind} worker 类型不匹配：{type(worker).__name__}")
        token = f"{kind}:{request_id}"
        workers, threads, _retiring_workers, _retiring_threads = (
            self._media_lifecycle_collections(kind)
        )
        workers[token] = worker
        threads[token] = thread
        self._media_lifecycle_records[token] = {
            "kind": kind,
            "state": "active",
            "worker_destroyed": False,
            "thread_finished": False,
            "thread_destroyed": False,
            "thread_delete_scheduled": False,
        }
        worker.destroyed.connect(
            lambda _object=None, stable_token=token: (
                self.media_worker_destroyed_notice.emit(stable_token)
            ),
            Qt.ConnectionType.DirectConnection,
        )
        thread.finished.connect(
            lambda stable_token=token: self.media_thread_finished_notice.emit(
                stable_token
            ),
            Qt.ConnectionType.DirectConnection,
        )
        thread.destroyed.connect(
            lambda _object=None, stable_token=token: (
                self.media_thread_destroyed_notice.emit(stable_token)
            ),
            Qt.ConnectionType.DirectConnection,
        )
        return token

    def _finalize_media_lifecycle_record(self, token: str) -> None:
        record = self._media_lifecycle_records.get(token)
        if not isinstance(record, dict):
            return
        if not record.get("worker_destroyed") or not record.get("thread_destroyed"):
            return
        kind = str(record.get("kind") or "")
        try:
            _workers, _threads, retiring_workers, retiring_threads = (
                self._media_lifecycle_collections(kind)
            )
        except ValueError:
            self._media_lifecycle_records.pop(token, None)
            return
        retiring_workers.pop(token, None)
        retiring_threads.pop(token, None)
        self._media_lifecycle_records.pop(token, None)

    def _retire_media_thread(self, token: str) -> None:
        record = self._media_lifecycle_records.get(token)
        if not isinstance(record, dict) or record.get("state") != "active":
            return
        kind = str(record.get("kind") or "")
        try:
            workers, threads, retiring_workers, retiring_threads = (
                self._media_lifecycle_collections(kind)
            )
        except ValueError:
            return

        worker = workers.pop(token, None)
        thread = threads.pop(token, None)
        if worker is not None:
            retiring_workers[token] = worker
        if thread is not None:
            retiring_threads[token] = thread
        record["state"] = "retiring"
        record["thread_finished"] = True
        self._trace_media_lifecycle("thread finished", token)

        if record.get("worker_destroyed"):
            retiring_workers.pop(token, None)

        if thread is not None and not record.get("thread_delete_scheduled"):
            record["thread_delete_scheduled"] = True
            try:
                thread.deleteLater()
            except RuntimeError:
                record["thread_destroyed"] = True
                retiring_threads.pop(token, None)

        if kind == "cover":
            self._running_cover_request = None
            if not self._media_workers_closing:
                self._launch_pending_cover_worker()
        elif kind == "lyrics":
            self._running_lyrics_request = None
            if not self._media_workers_closing:
                self._launch_pending_lyrics_worker()

        self._finalize_media_lifecycle_record(token)

    @Slot(str)
    def _on_media_worker_destroyed_notice(self, token: str) -> None:
        record = self._media_lifecycle_records.get(token)
        if not isinstance(record, dict):
            return
        record["worker_destroyed"] = True
        self._trace_media_lifecycle("worker destroyed", token)
        if record.get("state") == "retiring":
            kind = str(record.get("kind") or "")
            try:
                _workers, _threads, retiring_workers, _retiring_threads = (
                    self._media_lifecycle_collections(kind)
                )
            except ValueError:
                retiring_workers = {}
            retiring_workers.pop(token, None)
        self._finalize_media_lifecycle_record(token)

    @Slot(str)
    def _on_media_thread_finished_notice(self, token: str) -> None:
        self._retire_media_thread(token)

    @Slot(str)
    def _on_media_thread_destroyed_notice(self, token: str) -> None:
        record = self._media_lifecycle_records.get(token)
        if not isinstance(record, dict):
            return
        record["thread_destroyed"] = True
        self._trace_media_lifecycle("thread destroyed", token)
        kind = str(record.get("kind") or "")
        try:
            _workers, _threads, _retiring_workers, retiring_threads = (
                self._media_lifecycle_collections(kind)
            )
        except ValueError:
            retiring_threads = {}
        retiring_threads.pop(token, None)
        self._finalize_media_lifecycle_record(token)

    def _media_lifecycle_has_references(self) -> bool:
        return bool(
            self.cover_workers
            or self.lyrics_workers
            or self.cover_threads
            or self.lyrics_threads
            or self.retiring_cover_workers
            or self.retiring_lyrics_workers
            or self.retiring_cover_threads
            or self.retiring_lyrics_threads
            or self._media_lifecycle_records
        )

    def shutdown_media_workers(self, timeout_ms: int | None = None) -> bool:
        self._media_workers_closing = True
        self.active_cover_request_id = ""
        self.active_lyrics_request_id = ""
        self._pending_cover_request = None
        self._pending_lyrics_request = None
        self.cancel_media_workers("cover")
        self.cancel_media_workers("lyrics")

        if timeout_ms is None:
            timeout_ms = self.MEDIA_WORKER_SHUTDOWN_TIMEOUT_MS
        deadline = time.monotonic() + max(0, int(timeout_ms)) / 1000.0
        threads = tuple(self.cover_threads.items()) + tuple(self.lyrics_threads.items())

        for _token, thread in threads:
            if not self.media_thread_is_running(thread):
                continue
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if remaining_ms <= 0:
                break
            try:
                thread.wait(remaining_ms)
            except RuntimeError:
                pass

        for token, thread in tuple(self.cover_threads.items()):
            if not self.media_thread_is_running(thread):
                self._retire_media_thread(token)
        for token, thread in tuple(self.lyrics_threads.items()):
            if not self.media_thread_is_running(thread):
                self._retire_media_thread(token)

        return not self._media_lifecycle_has_references()

    def schedule_media_worker_close_retry(self) -> None:
        if self._media_shutdown_retry_scheduled:
            return
        self._media_shutdown_retry_scheduled = True
        QTimer.singleShot(100, self._retry_close_after_media_workers)

    def _retry_close_after_media_workers(self) -> None:
        self._media_shutdown_retry_scheduled = False
        for token, thread in tuple(self.cover_threads.items()):
            if not self.media_thread_is_running(thread):
                self._retire_media_thread(token)
        for token, thread in tuple(self.lyrics_threads.items()):
            if not self.media_thread_is_running(thread):
                self._retire_media_thread(token)
        if self._media_lifecycle_has_references():
            self.schedule_media_worker_close_retry()
            return
        self.close()

    def start_cover_worker(
        self,
        file_path: str,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        if self._media_workers_closing:
            return

        existing_request = self._pending_cover_request or self._running_cover_request
        if (
            self.active_cover_request_id == str((existing_request or {}).get("request_id", ""))
            and self.media_worker_request_matches(
                existing_request,
                file_path,
                title,
                artist,
                album,
            )
        ):
            return

        self.cover_request_id += 1
        request_id = str(self.cover_request_id)
        self.active_cover_request_id = request_id
        self._pending_cover_request = {
            "request_id": request_id,
            "file_path": file_path,
            "title": title,
            "artist": artist,
            "album": album,
        }
        self.cancel_media_workers("cover")
        self._launch_pending_cover_worker()

    def _launch_pending_cover_worker(self) -> None:
        if self._media_workers_closing or self.cover_threads:
            return
        request = self._pending_cover_request
        if not isinstance(request, dict):
            return
        if request.get("request_id") != self.active_cover_request_id:
            self._pending_cover_request = None
            return
        self._pending_cover_request = None
        self._running_cover_request = request

        worker = CoverSearchWorker(
            request_id=str(request["request_id"]),
            file_path=str(request["file_path"]),
            title=str(request["title"]),
            artist=str(request["artist"]),
            album=str(request["album"]),
            cover_cache_dir=str(self.cover_cache_dir),
            http_headers=self.http_headers,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        self._register_media_worker(
            "cover",
            str(request["request_id"]),
            worker,
            thread,
        )

        thread.started.connect(worker.run)
        worker.status_changed.connect(
            self.on_cover_worker_status,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            self.on_cover_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            worker.deleteLater,
            Qt.ConnectionType.DirectConnection,
        )
        worker.finished.connect(
            thread.quit,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.start()

    def on_cover_worker_status(self, request_id: str, message: str) -> None:
        if self._media_workers_closing or request_id != self.active_cover_request_id:
            return

        print("封面状态：", message)
        self.cover_label.setText(message)

    def on_cover_worker_finished(self, request_id: str, result: object) -> None:
        if self._media_workers_closing:
            return

        if request_id != self.active_cover_request_id:
            print("已忽略过期封面结果：", request_id)
            return

        if not isinstance(result, dict):
            self.cover_label.setText("封面加载失败")
            return

        result_song_path = self.normalize_song_path(result.get("song_path", ""))

        if result_song_path != self.normalize_song_path(self.current_song_path):
            print("已忽略非当前播放歌曲的封面结果：", result_song_path)
            return

        if result.get("ok"):
            cover_path = result.get("cover_path", "")

            if cover_path and self.show_cover_from_file(Path(cover_path)):
                print("已加载后台封面：", cover_path)
                return

        message = result.get("message", "未找到封面")
        print("封面搜索结束：", message)
        self.cover_label.clear()
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setText("无封面")

    def start_lyrics_worker(
        self,
        file_path: str,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        if self._media_workers_closing:
            return

        existing_request = self._pending_lyrics_request or self._running_lyrics_request
        if (
            self.active_lyrics_request_id == str((existing_request or {}).get("request_id", ""))
            and self.media_worker_request_matches(
                existing_request,
                file_path,
                title,
                artist,
                album,
            )
        ):
            return

        self.lyrics_request_id += 1
        request_id = str(self.lyrics_request_id)
        self.active_lyrics_request_id = request_id
        self._pending_lyrics_request = {
            "request_id": request_id,
            "file_path": file_path,
            "title": title,
            "artist": artist,
            "album": album,
        }
        self.cancel_media_workers("lyrics")
        self._launch_pending_lyrics_worker()

    def _launch_pending_lyrics_worker(self) -> None:
        if self._media_workers_closing or self.lyrics_threads:
            return
        request = self._pending_lyrics_request
        if not isinstance(request, dict):
            return
        if request.get("request_id") != self.active_lyrics_request_id:
            self._pending_lyrics_request = None
            return
        self._pending_lyrics_request = None
        self._running_lyrics_request = request

        worker = LyricsSearchWorker(
            request_id=str(request["request_id"]),
            file_path=str(request["file_path"]),
            title=str(request["title"]),
            artist=str(request["artist"]),
            album=str(request["album"]),
            lyrics_cache_dir=str(self.lyrics_cache_dir),
            http_headers=self.http_headers,
        )

        thread = QThread(self)
        worker.moveToThread(thread)
        self._register_media_worker(
            "lyrics",
            str(request["request_id"]),
            worker,
            thread,
        )

        thread.started.connect(worker.run)
        worker.status_changed.connect(
            self.on_lyrics_worker_status,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            self.on_lyrics_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            worker.deleteLater,
            Qt.ConnectionType.DirectConnection,
        )
        worker.finished.connect(
            thread.quit,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.start()

    def on_lyrics_worker_status(self, request_id: str, message: str) -> None:
        if self._media_workers_closing or request_id != self.active_lyrics_request_id:
            return

        self.set_lyrics_status(message)

    def on_lyrics_worker_finished(self, request_id: str, result: object) -> None:
        if self._media_workers_closing:
            return

        if request_id != self.active_lyrics_request_id:
            print("已忽略过期歌词结果：", request_id)
            return

        if not isinstance(result, dict):
            self.lyrics_view.set_placeholder("歌词加载失败", "")
            self.set_lyrics_status("歌词加载失败")
            return

        result_song_path = self.normalize_song_path(result.get("song_path", ""))

        if result_song_path != self.normalize_song_path(self.current_song_path):
            print("已忽略非当前播放歌曲的歌词结果：", result_song_path)
            return

        if result.get("ok"):
            lyrics_path = result.get("lyrics_path", "")
            song_path = result.get("song_path", "")

            if not lyrics_path:
                self.lyrics_view.set_placeholder("歌词路径为空", "")
                self.set_lyrics_status("歌词加载失败")
                return

            lyrics = self.parse_lrc_file(Path(lyrics_path))

            if not lyrics:
                self.lyrics_view.set_placeholder("歌词格式无法解析", "可以换成本地 .lrc 歌词")
                self.set_lyrics_status("歌词解析失败")
                return

            self.current_lyrics = lyrics
            self.displayed_lyrics_song_path = self.normalize_song_path(song_path)
            self.lyrics_view.set_lyrics(self.current_lyrics)
            self.sync_full_lyrics_from_current()

            source = result.get("source", "")

            if source == "local":
                self.set_lyrics_status("已加载本地歌词")
            elif source == "cache":
                self.set_lyrics_status("已加载缓存歌词")
            elif source == "online":
                self.set_lyrics_status("已加载联网歌词")
            else:
                self.set_lyrics_status("已加载歌词")

            print("已加载后台歌词：", lyrics_path)
            print("歌词行数：", len(self.current_lyrics))
            return

        message = result.get("message", "未找到同步歌词")
        source = result.get("source", "")

        if source == "missing_cache":
            self.lyrics_view.set_placeholder("近期已搜索过，未找到同步歌词", "之后会自动隔几天再试")
            self.set_lyrics_status("近期已搜索过，未找到歌词")
        else:
            self.lyrics_view.set_placeholder("未找到同步歌词", "可以手动放一个同名 .lrc 文件到歌曲旁边")
            self.set_lyrics_status(str(message))

        self.current_lyrics = []

    def update_cover(
        self,
        file_path: str | None,
        title: str,
        artist: str,
        album: str,
    ) -> None:
        normalized_file_path = self.normalize_song_path(file_path)

        if not normalized_file_path:
            return

        if normalized_file_path != self.normalize_song_path(self.current_song_path):
            return

        self.reset_cover()

        self.cover_label.setText("正在查找封面")
        self.start_cover_worker(
            file_path=normalized_file_path,
            title=title,
            artist=artist,
            album=album,
        )

    def get_cover_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.cover_cache_dir / f"{digest}.jpg"

    def show_cover_from_file(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))

        if pixmap.isNull():
            return False

        self.show_cover_pixmap(pixmap)
        return True

    def show_cover_from_bytes(self, data: bytes) -> bool:
        pixmap = QPixmap()
        loaded = pixmap.loadFromData(data)

        if not loaded or pixmap.isNull():
            return False

        self.show_cover_pixmap(pixmap)
        return True

    def show_cover_pixmap(self, pixmap: QPixmap) -> None:
        self.cover_label.setText("")
        self.cover_label.setPixmap(pixmap)

    def extract_album_cover(self, path: Path) -> bytes | None:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return None

            if hasattr(audio, "pictures") and audio.pictures:
                return audio.pictures[0].data

            if audio.tags is None:
                return None

            for key in audio.tags.keys():
                if str(key).startswith("APIC"):
                    tag = audio.tags[key]

                    if hasattr(tag, "data"):
                        return tag.data

            mp4_cover = audio.tags.get("covr")
            if mp4_cover:
                return bytes(mp4_cover[0])

        except Exception as error:
            print("读取内嵌封面失败：", path)
            print(error)

        return None

    def find_folder_cover(self, music_path: Path) -> Path | None:
        folder = music_path.parent

        possible_names = [
            "cover.jpg",
            "cover.jpeg",
            "cover.png",
            "folder.jpg",
            "folder.jpeg",
            "folder.png",
            "front.jpg",
            "front.jpeg",
            "front.png",
            "album.jpg",
            "album.jpeg",
            "album.png",
        ]

        for name in possible_names:
            candidate = folder / name

            if candidate.exists():
                return candidate

        return None

    def fetch_online_cover(self, title: str, artist: str, album: str) -> bytes | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_artist:
            print("缺少歌手信息，跳过联网封面查询。")
            return None

        if cleaned_album and cleaned_album not in {"未知专辑", "unknown album"}:
            queries = [
                f'release:"{cleaned_album}" AND artist:"{cleaned_artist}"',
                f'{cleaned_album} {cleaned_artist}',
            ]
        else:
            queries = [
                f'recording:"{cleaned_title}" AND artist:"{cleaned_artist}"',
                f'{cleaned_title} {cleaned_artist}',
            ]

        for query in queries:
            release_ids = self.search_musicbrainz_release_ids(query)

            for release_id in release_ids:
                cover_data = self.fetch_cover_art_archive(release_id)

                if cover_data:
                    return cover_data

        return None

    def clean_search_text(self, text: str) -> str:
        text = text.strip()

        if text in {"未知歌曲", "未知艺术家", "未知专辑"}:
            return ""

        return text

    def wait_for_musicbrainz_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self.last_musicbrainz_request_time

        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        self.last_musicbrainz_request_time = time.time()

    def search_musicbrainz_release_ids(self, query: str) -> list[str]:
        print("正在搜索 MusicBrainz：", query)

        try:
            self.wait_for_musicbrainz_rate_limit()

            response = requests.get(
                "https://musicbrainz.org/ws/2/release/",
                params={
                    "query": query,
                    "fmt": "json",
                    "limit": 5,
                },
                headers=self.http_headers,
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

        except Exception as error:
            print("MusicBrainz 搜索失败：", error)
            return []

        releases = data.get("releases", [])
        release_ids = []

        for release in releases:
            release_id = release.get("id")
            title = release.get("title", "")
            score = release.get("score", "")

            if release_id:
                print(f"找到候选专辑：{title} / score={score} / id={release_id}")
                release_ids.append(release_id)

        return release_ids

    def fetch_cover_art_archive(self, release_id: str) -> bytes | None:
        url = f"https://coverartarchive.org/release/{release_id}/front-500"
        print("正在获取封面：", release_id)

        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": self.http_headers["User-Agent"],
                    "Accept": "image/*",
                },
                timeout=15,
                allow_redirects=True,
            )

            if response.status_code != 200:
                print("这个 release 没有可用封面：", response.status_code)
                return None

            content_type = response.headers.get("Content-Type", "")

            if "image" not in content_type.lower():
                print("返回内容不是图片：", content_type)
                return None

            return response.content

        except Exception as error:
            print("Cover Art Archive 获取失败：", error)
            return None

    def get_lyrics_cache_path(self, path: Path) -> Path:
        normalized_path = str(path.resolve()).lower()
        digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()
        return self.lyrics_cache_dir / f"{digest}.lrc"

    def get_audio_duration_seconds(self, path: Path) -> int:
        try:
            audio = MutagenFile(path)

            if audio is None:
                return 0

            info = getattr(audio, "info", None)

            if info is None:
                return 0

            length = getattr(info, "length", 0)

            if not length:
                return 0

            return int(round(float(length)))

        except Exception as error:
            print("读取歌曲时长失败：", path)
            print(error)
            return 0

    def normalize_match_text(self, text: str) -> str:
        text = self.clean_search_text(text).lower()
        text = re.sub(r"[\s\\-_.,，。:：;；!！?？'\"“”‘’()\[\]{}【】<>《》/\\\\]+", "", text)
        return text

    def calculate_lyrics_result_score(
        self,
        result: dict,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> int:
        score = 0

        synced_lyrics = result.get("syncedLyrics")

        if not synced_lyrics:
            return -9999

        result_title = str(result.get("trackName", ""))
        result_artist = str(result.get("artistName", ""))
        result_album = str(result.get("albumName", ""))

        target_title = self.normalize_match_text(title)
        target_artist = self.normalize_match_text(artist)
        target_album = self.normalize_match_text(album)

        matched_title = self.normalize_match_text(result_title)
        matched_artist = self.normalize_match_text(result_artist)
        matched_album = self.normalize_match_text(result_album)

        if target_title and matched_title:
            if target_title == matched_title:
                score += 80
            elif target_title in matched_title or matched_title in target_title:
                score += 45

        if target_artist and matched_artist:
            if target_artist == matched_artist:
                score += 60
            elif target_artist in matched_artist or matched_artist in target_artist:
                score += 30

        if target_album and matched_album:
            if target_album == matched_album:
                score += 20
            elif target_album in matched_album or matched_album in target_album:
                score += 8

        result_duration = int(result.get("duration", 0) or 0)

        if duration_seconds > 0 and result_duration > 0:
            diff = abs(duration_seconds - result_duration)

            if diff <= 2:
                score += 30
            elif diff <= 5:
                score += 18
            elif diff <= 10:
                score += 8

        if synced_lyrics:
            score += 40

        return score

    def search_lrclib_synced_lyrics(
        self,
        title: str,
        artist: str,
        album: str,
        duration_seconds: int,
    ) -> str | None:
        cleaned_title = self.clean_search_text(title)
        cleaned_artist = self.clean_search_text(artist)
        cleaned_album = self.clean_search_text(album)

        if not cleaned_title:
            print("缺少歌曲名，跳过联网歌词搜索。")
            return None

        search_requests = []

        first_params = {
            "track_name": cleaned_title,
        }

        if cleaned_artist:
            first_params["artist_name"] = cleaned_artist

        if cleaned_album:
            first_params["album_name"] = cleaned_album

        search_requests.append(first_params)

        if cleaned_artist:
            search_requests.append(
                {
                    "q": f"{cleaned_title} {cleaned_artist}",
                }
            )

        search_requests.append(
            {
                "q": cleaned_title,
            }
        )

        best_result = None
        best_score = -9999

        for params in search_requests:
            try:
                print("正在搜索 LRCLIB 歌词：", params)

                response = requests.get(
                    "https://lrclib.net/api/search",
                    params=params,
                    headers=self.http_headers,
                    timeout=12,
                )

                response.raise_for_status()
                results = response.json()

                if not isinstance(results, list):
                    continue

            except Exception as error:
                print("LRCLIB 搜索失败：", error)
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue

                score = self.calculate_lyrics_result_score(
                    result=result,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_seconds=duration_seconds,
                )

                result_title = result.get("trackName", "")
                result_artist = result.get("artistName", "")
                result_duration = result.get("duration", "")

                print(
                    "歌词候选：",
                    result_title,
                    "-",
                    result_artist,
                    "duration=",
                    result_duration,
                    "score=",
                    score,
                )

                if score > best_score:
                    best_score = score
                    best_result = result

            if best_result and best_score >= 110:
                break

        if not best_result:
            print("没有找到合适的联网歌词。")
            return None

        synced_lyrics = best_result.get("syncedLyrics")

        if not synced_lyrics:
            print("最佳结果没有同步歌词。")
            return None

        if best_score < 80:
            print("联网歌词匹配分数过低，已放弃：", best_score)
            return None

        print(
            "已匹配联网歌词：",
            best_result.get("trackName", ""),
            "-",
            best_result.get("artistName", ""),
            "score=",
            best_score,
        )

        return str(synced_lyrics).strip()

    def write_lyrics_cache(self, cache_path: Path, lyrics_text: str) -> bool:
        try:
            self.lyrics_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(lyrics_text, encoding="utf-8")
            print("歌词已缓存：", cache_path)
            return True

        except Exception as error:
            print("写入歌词缓存失败：", error)
            return False

    def load_lyrics_for_song(
        self,
        file_path: str | None,
        title: str,
        artist: str,
        ignore_binding: bool = False,
    ) -> None:
        normalized_file_path = self.normalize_song_path(file_path)

        if not normalized_file_path:
            return

        if normalized_file_path != self.normalize_song_path(self.current_song_path):
            print("已跳过非当前播放歌曲的共享歌词刷新：", normalized_file_path)
            return

        self.current_lyrics = []
        self.current_plain_lyrics = ""
        current = getattr(self, "current_media_item", None)
        self.displayed_lyrics_track_key = (
            current.stable_identity if isinstance(current, MediaItem) else ""
        )
        self.displayed_lyrics_song_path = normalized_file_path
        self.lyrics_view.set_placeholder("正在查找歌词", "优先手动绑定，其次本地歌词，然后缓存和联网")
        self.set_lyrics_status("正在查找歌词")

        if not ignore_binding:
            bound_lyrics_path = self.get_bound_lyrics_path(normalized_file_path)

            if bound_lyrics_path:
                self.invalidate_media_worker_request("lyrics")
                self.set_lyrics_status("正在读取手动绑定歌词")
                lyrics = self.parse_lrc_file(Path(bound_lyrics_path))

                if lyrics:
                    self.current_lyrics = lyrics
                    self.displayed_lyrics_song_path = normalized_file_path
                    self.lyrics_view.set_lyrics(self.current_lyrics)
                    self.sync_full_lyrics_from_current()
                    self.set_lyrics_status("已加载手动绑定歌词")

                    print("已加载手动绑定歌词：", bound_lyrics_path)
                    print("歌词行数：", len(self.current_lyrics))
                    return

                self.set_lyrics_status("手动绑定歌词解析失败，继续自动查找")
                print("手动绑定歌词解析失败：", bound_lyrics_path)

        album = "未知专辑"
        song_data = self.find_song_data_by_path(normalized_file_path)

        if isinstance(song_data, dict):
            album = song_data.get("album", "未知专辑")

        self.start_lyrics_worker(
            file_path=normalized_file_path,
            title=title,
            artist=artist,
            album=album,
        )

    def find_lrc_file(self, music_path: Path, title: str, artist: str) -> Path | None:
        folder = music_path.parent

        candidates = [
            music_path.with_suffix(".lrc"),
            folder / f"{music_path.stem}.lrc",
            folder / f"{title}.lrc",
            folder / f"{artist} - {title}.lrc",
            folder / f"{title} - {artist}.lrc",
        ]

        seen = set()

        for candidate in candidates:
            normalized = str(candidate).lower()

            if normalized in seen:
                continue

            seen.add(normalized)

            if candidate.exists():
                return candidate

        for candidate in folder.glob("*.lrc"):
            if candidate.stem.lower() == music_path.stem.lower():
                return candidate

        return None

    def parse_lrc_file(self, lrc_path: Path) -> list[tuple[int, str]]:
        content = None
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
            try:
                content = lrc_path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
            except Exception as error:
                print("读取歌词文件失败：", error)
                return []
        return self.parse_lrc_text(content or "")

    @staticmethod
    def parse_lrc_text(content: str) -> list[tuple[int, str]]:
        lyrics: list[tuple[int, str]] = []
        time_pattern = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]")
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matches = list(time_pattern.finditer(line))
            if not matches:
                continue
            lyric_text = time_pattern.sub("", line).strip() or "♪"
            for match in matches:
                minute = int(match.group(1))
                second = int(match.group(2))
                millisecond_text = match.group(3) or "0"
                if len(millisecond_text) == 1:
                    millisecond = int(millisecond_text) * 100
                elif len(millisecond_text) == 2:
                    millisecond = int(millisecond_text) * 10
                else:
                    millisecond = int(millisecond_text[:3])
                timestamp = minute * 60 * 1000 + second * 1000 + millisecond
                lyrics.append((timestamp, lyric_text))
        lyrics.sort(key=lambda item: item[0])
        return lyrics
    def playback_queue_item_from_song_data(
        self,
        song_data: dict,
    ) -> PlaybackQueueItem | None:
        if not isinstance(song_data, dict) or song_data.get("demo"):
            return None
        try:
            media_item = self.media_item_from_song_data(song_data)
        except (TypeError, ValueError):
            return None
        if media_item.media_type == "local" and not media_item.local_file_path:
            return None
        return PlaybackQueueItem(media_item)

    def playback_queue_item_from_value(
        self,
        value,
    ) -> PlaybackQueueItem | None:
        if isinstance(value, str):
            normalized_path = self.normalize_song_path(value)
            song_data = (
                self.find_song_data_by_path(normalized_path)
                if hasattr(self, "song_list")
                else None
            )
            if isinstance(song_data, dict):
                return self.playback_queue_item_from_song_data(song_data)
            value = normalized_path
        try:
            return PlaybackQueueItem.from_value(value)
        except (TypeError, ValueError):
            return None

    def get_visible_playback_items(self) -> list[PlaybackQueueItem]:
        ordered_items: list[PlaybackQueueItem] = []
        seen: set[str] = set()
        for row in self.get_visible_rows():
            item = self.song_list.item(row)
            song_data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            queue_item = (
                self.playback_queue_item_from_song_data(song_data)
                if isinstance(song_data, dict)
                else None
            )
            if queue_item is None or queue_item.stable_identity in seen:
                continue
            seen.add(queue_item.stable_identity)
            ordered_items.append(queue_item)
        return ordered_items

    def get_visible_playback_paths(self) -> list[str]:
        """Compatibility view for local-only playback session persistence."""

        return [
            item.local_path
            for item in self.get_visible_playback_items()
            if item.kind == "local" and item.local_path
        ]

    def get_playback_context_source(self) -> tuple[str, str]:
        view_name = str(getattr(self, "current_library_view", "all") or "all")

        if view_name.startswith("playlist:"):
            source_type = "playlist"
            source_id = view_name.split("playlist:", 1)[1]
        elif view_name == "liked":
            source_type = "liked"
            source_id = "liked"
        elif view_name == "all":
            source_type = "library"
            source_id = "all"
        else:
            source_type = "library_view"
            source_id = view_name

        search_keyword = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        filter_type = str(getattr(self, "library_category_filter_type", "") or "")
        filter_value = str(getattr(self, "library_category_filter_value", "") or "")
        source_details = [source_id]

        if search_keyword:
            source_details.append(f"search:{search_keyword}")

        if filter_type and filter_value:
            source_details.append(f"{filter_type}:{filter_value}")

        return source_type, "|".join(source_details)

    def create_playback_context(
        self,
        current_value,
        candidates: list | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        current_item = self.playback_queue_item_from_value(current_value)
        if current_item is None:
            return False
        if candidates is None:
            ordered_items = self.get_visible_playback_items()
        else:
            ordered_items = []
            for value in candidates:
                item = self.playback_queue_item_from_value(value)
                if item is not None:
                    ordered_items.append(item)
        if not any(
            item.stable_identity == current_item.stable_identity
            for item in ordered_items
        ):
            ordered_items.append(current_item)

        if source_type is None or source_id is None:
            detected_type, detected_id = self.get_playback_context_source()
            source_type = source_type or detected_type
            source_id = source_id or detected_id
        self.playback_queue.replace(ordered_items, current_item.stable_identity)
        self.queue_return_state = None
        self.playback_context = {
            "source_type": source_type,
            "source_id": source_id,
            "ordered_items": [item.to_mapping() for item in self.playback_queue.items],
            "ordered_paths": [
                item.local_path
                for item in self.playback_queue.items
                if item.kind == "local" and item.local_path
            ],
            "current_identity": current_item.stable_identity,
            "current_index": self.playback_queue.current_index,
        }
        print(
            "已建立播放上下文：",
            source_type,
            source_id,
            f"歌曲数={len(self.playback_queue.items)}",
            f"当前位置={self.playback_context['current_index']}",
        )
        return True

    def get_playback_context_items(self) -> list[PlaybackQueueItem]:
        context = self.playback_context
        if not isinstance(context, dict):
            return []
        raw_items = context.get("ordered_items")
        items: list[PlaybackQueueItem] = []
        if isinstance(raw_items, list):
            for value in raw_items:
                item = self.playback_queue_item_from_value(value)
                if item is not None:
                    items.append(item)
        if not items:
            raw_paths = context.get("ordered_paths", [])
            if isinstance(raw_paths, list):
                for value in raw_paths:
                    item = self.playback_queue_item_from_value(value)
                    if item is not None:
                        items.append(item)
        identities = [item.stable_identity for item in items]
        if identities != [item.stable_identity for item in self.playback_queue.items]:
            current_identity = str(context.get("current_identity") or "")
            if not current_identity:
                try:
                    index = int(context.get("current_index", 0))
                except (TypeError, ValueError):
                    index = 0
                if 0 <= index < len(items):
                    current_identity = items[index].stable_identity
            self.playback_queue.replace(items, current_identity)
        return list(self.playback_queue.items)

    def get_playback_context_paths(self) -> list[str]:
        context = self.playback_context

        if not isinstance(context, dict):
            return []

        return [
            item.local_path
            for item in self.get_playback_context_items()
            if item.kind == "local" and item.local_path
        ]

    def get_playback_context_anchor_index(
        self,
        ordered_paths: list[str],
        anchor_path: str | None = None,
    ) -> int:
        if not ordered_paths:
            return -1

        current_path = self.normalize_song_path(anchor_path or self.current_song_path)

        if current_path in ordered_paths:
            current_index = ordered_paths.index(current_path)
        else:
            context = self.playback_context if isinstance(self.playback_context, dict) else {}

            try:
                current_index = int(context.get("current_index", 0))
            except (TypeError, ValueError):
                current_index = 0

            current_index = max(0, min(current_index, len(ordered_paths) - 1))

        if isinstance(self.playback_context, dict):
            self.playback_context["current_index"] = current_index

        return current_index

    def get_playback_navigation_indices(
        self,
        direction: int,
        anchor_path: str | None = None,
    ) -> list[int]:
        self.get_playback_context_items()
        if anchor_path:
            anchor_item = self.playback_queue_item_from_value(anchor_path)
            if anchor_item is not None:
                self.playback_queue.set_current_identity(anchor_item.stable_identity)
        target_index = self.playback_queue.next_index(self.play_mode, direction)
        return [] if target_index is None else [target_index]

    def replay_current_song(self) -> bool:
        current_media = getattr(self, "current_media_item", None)
        if (
            isinstance(current_media, MediaItem)
            and current_media.media_type == "online"
            and getattr(self, "current_track_kind", "local") == "online"
        ):
            identity = self.current_track_identity() or current_media.stable_identity
            if self.media_player.source().isValid():
                self.media_player.setPosition(0)
                self.progress_slider.setValue(0)
                self.last_recorded_position = 0
                self.media_player.play()
                self.play_btn.setText("暂停")
                print("重新播放当前在线歌曲：", identity)
                return True
            generation = self.begin_playback_generation(identity)
            self.request_online_playback(
                current_media.to_legacy_online(),
                playback_generation=generation,
                queue_identity=identity,
            )
            return True

        current_path = self.normalize_song_path(self.current_song_path)
        if not current_path:
            return False
        self.media_player.setPosition(0)
        self.progress_slider.setValue(0)
        self.last_recorded_position = 0
        self.media_player.play()
        self.play_btn.setText("暂停")
        print("重新播放当前歌曲：", current_path)
        return True

    def sync_playback_context_current(self, identity: str) -> None:
        if not isinstance(self.playback_context, dict):
            return
        if self.playback_queue.set_current_identity(identity):
            self.playback_context["current_identity"] = identity
            self.playback_context["current_index"] = self.playback_queue.current_index

    def play_queue_item(
        self,
        value,
        *,
        update_context: bool = True,
    ) -> bool:
        queue_item = self.playback_queue_item_from_value(value)
        if queue_item is None:
            return False
        identity = queue_item.stable_identity
        if update_context:
            self.sync_playback_context_current(identity)
        generation = self.begin_playback_generation(identity)
        media_item = queue_item.media_item
        self.browse_media_item(media_item.to_dict())

        if queue_item.kind == "remote" and not media_item.is_local_available:
            self.flush_current_listen_time()
            self.current_track_kind = "online"
            self.current_media_item = media_item
            self.current_online_track = media_item.to_legacy_online()
            self.current_song_path = None
            self.invalidate_media_worker_request("cover")
            self.invalidate_media_worker_request("lyrics")
            self.refresh_playing_song_indicators()
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            if media_item.availability != "available":
                self.media_loading_generation = 0
                self.present_online_media_item(media_item)
                self.set_online_status_message("该在线来源当前不可用。")
                return False
            self.request_online_playback(
                media_item.to_legacy_online(),
                playback_generation=generation,
                queue_identity=identity,
                keep_target_on_failure=True,
            )
            return True

        local_path = self.normalize_song_path(media_item.local_file_path)
        if not local_path or not Path(local_path).is_file():
            return False
        song_data = self.find_song_data_by_path(local_path)
        if not isinstance(song_data, dict) or song_data.get("recordKind") == "remote":
            song_data = media_item.to_legacy_local()
        self.load_song_for_playback(
            song_data,
            playback_generation=generation,
            queue_identity=identity,
        )
        if queue_item.kind == "remote":
            self.current_media_item = media_item
            self.current_online_track = media_item.to_legacy_online()
            self.current_queue_identity = identity
            self.refresh_playing_song_indicators()
            self.update_like_button()
        self.play_current_song()
        return True

    def play_from_playback_context(
        self,
        direction: int,
        respect_single_loop: bool = True,
        anchor_path: str | None = None,
    ) -> bool:
        if respect_single_loop and self.play_mode == "single_loop":
            return self.replay_current_song()

        ordered_items = self.get_playback_context_items()
        if not ordered_items:
            print("当前没有可用的播放上下文，无法导航歌曲。")
            return False

        if anchor_path:
            anchor_item = self.playback_queue_item_from_value(anchor_path)
            if anchor_item is not None:
                self.playback_queue.set_current_identity(anchor_item.stable_identity)
        attempts = 0
        while attempts < len(ordered_items):
            target_index = self.playback_queue.next_index(self.play_mode, direction)
            if target_index is None:
                print("播放上下文已经到达边界。")
                return False
            target_item = self.playback_queue.items[target_index]
            if isinstance(self.playback_context, dict):
                self.playback_context["current_index"] = target_index
                self.playback_context["current_identity"] = target_item.stable_identity
            if target_item.stable_identity == self.current_track_identity():
                return self.replay_current_song()
            if self.play_queue_item(target_item, update_context=True):
                return True
            if target_item.kind == "remote":
                return False
            attempts += 1

        print("播放上下文中没有可播放的歌曲。")
        return False

    def play_selected_song(self, item: QListWidgetItem) -> None:
        self.select_song(item)

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return

        queue_item = self.playback_queue_item_from_song_data(song_data)
        if queue_item is None:
            return
        self.create_playback_context(queue_item)
        self.play_queue_item(queue_item)

    def get_remote_record_from_song_data(self, song_data: dict) -> tuple[str, dict] | None:
        stable_id = str(song_data.get("remoteStableId") or "").strip()
        record = self.remote_tracks.get(stable_id)
        if not stable_id or not isinstance(record, dict):
            return None
        return stable_id, record

    def play_remote_song_data(self, song_data: dict) -> None:
        queue_item = self.playback_queue_item_from_song_data(song_data)
        if queue_item is None:
            QMessageBox.warning(self, "在线歌曲不可用", "没有找到这首在线歌曲的持久化记录。")
            return
        if self.playback_queue.index_for_identity(queue_item.stable_identity) < 0:
            self.create_playback_context(queue_item)
        if not self.play_queue_item(queue_item):
            QMessageBox.information(
                self,
                "在线来源不可用",
                "保存的歌曲记录仍会保留，但对应的自定义 URL 来源当前未注册或已不可用。",
            )

    def play_current_song(self) -> None:
        if not self.current_song_path:
            self.load_pending_playback_restore()

        if not self.current_song_path:
            current_item = self.song_list.currentItem()

            if current_item:
                song_data = current_item.data(Qt.ItemDataRole.UserRole)

                if isinstance(song_data, dict):
                    self.create_playback_context(song_data.get("path", ""))
                    self.load_song_for_playback(song_data)

        if not self.current_song_path:
            self.lyrics_view.set_placeholder(
                "请先导入并选择一首真实的本地音乐",
                "单击浏览，双击播放",
            )
            return

        print("准备播放：", self.current_song_path)
        print("当前音量：", self.audio_output.volume())
        print("当前 source：", self.media_player.source().toString())

        self.last_recorded_position = self.media_player.position()
        self.media_player.play()
        self.play_btn.setText("暂停")

    def toggle_play(self) -> None:
        state = self.media_player.playbackState()
        print("当前播放状态：", state)

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("播放")
        elif getattr(self, "current_track_kind", "local") == "online" and self.media_player.source().isValid():
            self.media_player.play()
        else:
            self.play_current_song()

    def toggle_play_mode(self) -> None:
        if self.play_mode == "sequence":
            self.play_mode = "list_loop"
        elif self.play_mode == "list_loop":
            self.play_mode = "single_loop"
        elif self.play_mode == "single_loop":
            self.play_mode = "shuffle"
        else:
            self.play_mode = "sequence"

        self.update_play_mode_button()
        self.save_settings()

    def update_play_mode_button(self) -> None:
        if not hasattr(self, "play_mode_btn"):
            return

        mode_text = {
            "sequence": "顺序播放",
            "list_loop": "列表循环",
            "single_loop": "单曲循环",
            "shuffle": "随机播放",
        }

        self.play_mode_btn.setText(mode_text.get(self.play_mode, "列表循环"))

    def play_song_by_row(self, row: int) -> None:
        if row < 0 or row >= self.song_list.count():
            return

        self.song_list.setCurrentRow(row)
        item = self.song_list.item(row)

        if item:
            self.play_selected_song(item)

    def play_random_library_song(self) -> None:
        candidates = []

        for row in range(self.song_list.count()):
            item = self.song_list.item(row)

            if item is None:
                continue

            song_data = item.data(Qt.ItemDataRole.UserRole)

            if not isinstance(song_data, dict) or song_data.get("demo"):
                continue

            queue_item = self.playback_queue_item_from_song_data(song_data)
            if queue_item is not None:
                if (
                    queue_item.kind == "remote"
                    and queue_item.media_item.availability != "available"
                ):
                    continue
                candidates.append(row)

        if not candidates:
            QMessageBox.information(self, "随机播放", "音乐库里还没有可以播放的真实歌曲。")
            return

        self.play_mode = "shuffle"
        self.update_play_mode_button()
        self.save_settings()
        self.play_song_by_row(random.choice(candidates))

    def open_current_song_folder(self) -> None:
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem) and current.media_type == "online":
            self.show_media_item_info(current.to_dict())
            return
        song_path = self.normalize_song_path(self.current_song_path)

        if not song_path:
            QMessageBox.information(self, "打开文件夹", "还没有正在播放的歌曲。")
            return

        path = Path(song_path)

        if not path.exists():
            QMessageBox.warning(self, "文件不存在", "当前播放的音乐文件已经不存在。")
            return

        try:
            os.startfile(str(path.parent))
        except Exception as error:
            QMessageBox.warning(self, "打开失败", str(error))

    def show_current_playing_info(self) -> None:
        current = getattr(self, "current_media_item", None)
        if isinstance(current, MediaItem):
            self.show_media_item_info(current.to_dict())
            return
        song_data = self.find_song_data_by_path(self.current_song_path)
        if isinstance(song_data, dict):
            self.show_media_item_info(MediaItem.from_local(song_data).to_dict())
            return
        QMessageBox.information(self, "歌曲信息", "还没有正在播放的歌曲。")

    def play_previous_song(self) -> None:
        self.play_from_playback_context(-1)

    def play_next_with_queue_priority(self, reason: str = "manual") -> bool:
        now = time.monotonic()
        last_reason = str(getattr(self, "last_advance_reason", "") or "")
        last_at = float(getattr(self, "last_advance_at", 0.0) or 0.0)
        if (
            reason in {"manual", "end"}
            and last_reason in {"manual", "end"}
            and reason != last_reason
            and now - last_at < 0.35
        ):
            print("已忽略同一切歌边界上的重复推进：", last_reason, "->", reason)
            return False
        self.last_advance_reason = reason
        self.last_advance_at = now
        if reason == "end" and self.play_mode == "single_loop":
            return self.play_from_playback_context(1)
        if self.play_next_queued_song():
            return True

        if isinstance(self.queue_return_state, dict):
            return self.resume_playback_context_after_queue()

        return self.play_from_playback_context(1)

    def play_next_song(self) -> None:
        self.play_next_with_queue_priority("manual")

    def handle_song_finished(self, expected_generation: int | None = None) -> None:
        generation = int(getattr(self, "playback_generation", 0) or 0)
        if expected_generation is not None and expected_generation != generation:
            print("已忽略旧播放会话的结束事件：", expected_generation, generation)
            return
        if self.handled_end_generation == generation:
            print("已忽略重复的媒体结束事件：", generation)
            return
        now = time.monotonic()
        if now - float(getattr(self, "last_end_advance_at", 0.0) or 0.0) < 0.35:
            print("已忽略短时间内重复到达的媒体结束事件。")
            return
        self.last_end_advance_at = now
        self.handled_end_generation = generation
        print("歌曲播放结束，准备根据播放模式切歌：", self.play_mode)
        self.play_next_with_queue_priority("end")

    def import_music_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音乐文件",
            str(Path.home()),
            "Audio Files (*.mp3 *.flac *.wav *.m4a *.aac *.ogg);;All Files (*)",
        )

        if not file_paths:
            return

        self.add_music_paths([Path(file_path) for file_path in file_paths])

    def import_music_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择音乐文件夹",
            str(Path.home()),
        )

        if not folder_path:
            return

        folder = Path(folder_path)
        music_paths = self.scan_music_folder(folder)

        print(f"选择的文件夹：{folder}")
        print(f"扫描到音乐文件数量：{len(music_paths)}")

        if not music_paths:
            return

        self.add_music_paths(music_paths)

    def scan_music_folder(self, folder: Path) -> list[Path]:
        music_paths = []

        try:
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() in AUDIO_EXTENSIONS:
                    music_paths.append(path)

        except Exception as error:
            print("扫描文件夹失败：", error)

        music_paths.sort(key=lambda item: str(item).lower())
        return music_paths

    def add_music_paths(self, paths: list[Path]) -> None:
        if not paths:
            return

        if self.has_demo_songs():
            self.song_identity_to_item = {}
            self.song_list.clear()

        existing_paths = self.get_existing_song_paths()
        added_items: list[QListWidgetItem] = []
        skipped_count = 0
        failed_count = 0

        for raw_path in paths:
            try:
                path = Path(raw_path).resolve()
            except Exception:
                failed_count += 1
                continue

            normalized_path = str(path)

            if normalized_path in existing_paths:
                skipped_count += 1
                continue

            if not path.exists() or not path.is_file():
                failed_count += 1
                continue

            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                skipped_count += 1
                continue

            title, artist, album = self._read_audio_metadata(path)
            added_at = int(time.time()) + len(added_items)

            item = self.create_song_list_item(
                {
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "path": normalized_path,
                    "added_at": added_at,
                    "demo": False,
                }
            )

            self.song_list.addItem(item)
            added_items.append(item)
            existing_paths.add(normalized_path)

        self.mark_library_list_dirty()
        self.apply_current_library_sort(refresh_view=False)
        self.filter_song_list(self.search_input.text())

        visible_added_items = [
            item for item in added_items
            if item is not None and not item.isHidden()
        ]

        if visible_added_items:
            first_added_item = visible_added_items[0]
            self.song_list.setCurrentItem(first_added_item)
            self.select_song(first_added_item)
        elif added_items:
            first_added_item = added_items[0]
            self.song_list.setCurrentItem(first_added_item)
            self.select_song(first_added_item)

        self.save_music_library()

        print(f"本次新增歌曲数量：{len(added_items)}")
        print(f"本次跳过重复或非音频数量：{skipped_count}")
        print(f"本次导入失败数量：{failed_count}")

    def _read_audio_metadata(self, path: Path) -> tuple[str, str, str]:
        title = path.stem
        artist = "未知艺术家"
        album = "未知专辑"

        try:
            audio = MutagenFile(path, easy=True)

            if audio is None or audio.tags is None:
                return title, artist, album

            title = audio.tags.get("title", [title])[0]
            artist = audio.tags.get("artist", [artist])[0]
            album = audio.tags.get("album", [album])[0]

        except Exception as error:
            print(f"读取歌曲信息失败：{path}")
            print(error)
            return title, artist, album

        return title, artist, album

    def change_volume(self, value: int) -> None:
        self.current_volume = value
        self.audio_output.setVolume(value / 100)
        self.save_hush_settings({"volume": value})
        print("音量改为：", value)

    def on_seek_start(self) -> None:
        self.is_seeking = True

    def on_seek_end(self) -> None:
        self.is_seeking = False

        if self.current_duration <= 0:
            return

        slider_value = self.progress_slider.value()
        target_position = int(self.current_duration * slider_value / 100)
        self.pending_restore_position = 0
        self.media_player.setPosition(target_position)
        self.last_recorded_position = target_position

    def on_position_changed(self, position: int) -> None:
        if self.is_seeking or self.current_duration <= 0:
            return

        if (
            position >= 1000
            and getattr(self, "current_track_kind", "local") == "online"
        ):
            self.online_loop_retry_count = 0

        progress = int(position * 100 / self.current_duration)
        self.progress_slider.setValue(progress)

        self.record_listen_progress(position)

        current = getattr(self, "current_media_item", None)
        if (
            isinstance(current, MediaItem)
            and current.media_type == "online"
            and self.displayed_lyrics_track_key == current.stable_identity
        ):
            self.lyrics_view.update_by_position(position, self.current_lyrics)
            if hasattr(self, "full_lyrics_view"):
                self.full_lyrics_view.update_by_position(position, self.current_lyrics)
            if self.immersive_lyrics_window is not None:
                self.immersive_lyrics_window.update_position(position, self.current_lyrics)
            return

        current_playing_path = self.normalize_song_path(self.current_song_path)
        displayed_lyrics_path = self.normalize_song_path(self.displayed_lyrics_song_path)

        if current_playing_path and displayed_lyrics_path == current_playing_path:
            self.lyrics_view.update_by_position(position, self.current_lyrics)
            if hasattr(self, "full_lyrics_view"):
                self.full_lyrics_view.update_by_position(position, self.current_lyrics)
                if self.immersive_lyrics_window is not None:
                    self.immersive_lyrics_window.update_position(position, self.current_lyrics)

    def on_duration_changed(self, duration: int) -> None:
        self.current_duration = duration
        print("歌曲时长：", duration, "ms")

        if duration > 0:
            self.apply_pending_restore_position()

    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        print("播放状态变化：", state)

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("暂停")

            if int(getattr(self, "pending_restore_position", 0) or 0) > 0:
                self.apply_pending_restore_position()
                QTimer.singleShot(180, self.finalize_pending_restore_position)
        else:
            self.play_btn.setText("播放")
            self.flush_current_listen_time()

    def on_media_status_changed(self, status) -> None:
        print("媒体状态：", status)
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            if self.media_loading_generation == self.playback_generation:
                self.media_loading_generation = 0
            if getattr(self, "current_track_kind", "local") == "online":
                self.set_online_status_message("在线歌曲正在播放。")
            else:
                self.apply_pending_restore_position()

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            generation = int(getattr(self, "playback_generation", 0) or 0)
            if self.media_loading_generation == generation:
                print("已忽略切换媒体期间到达的旧结束事件：", generation)
                return
            self.flush_current_listen_time()
            if getattr(self, "current_track_kind", "local") == "online":
                self.set_online_status_message("在线歌曲已播放结束，正在继续队列。")
            self.handle_song_finished(generation)

    def on_player_error(self, error=None, error_string: str = "") -> None:
        real_error_text = error_string or self.media_player.errorString()

        print("播放错误：", error)
        print("错误信息：", real_error_text)

        if real_error_text and getattr(self, "current_track_kind", "local") == "online":
            queue_item = self.playback_queue.current_item
            identity = self.current_track_identity()
            current_media = getattr(self, "current_media_item", None)
            if (
                (queue_item is None or queue_item.stable_identity != identity)
                and isinstance(current_media, MediaItem)
                and current_media.media_type == "online"
            ):
                queue_item = PlaybackQueueItem(current_media)
            if (
                self.play_mode == "single_loop"
                and queue_item is not None
                and queue_item.kind == "remote"
                and queue_item.stable_identity == identity
                and self.online_loop_retry_count < 1
            ):
                self.online_loop_retry_identity = identity
                self.online_loop_retry_count += 1
                generation = self.begin_playback_generation(identity)
                self.media_player.stop()
                self.media_player.setSource(QUrl())
                self.request_online_playback(
                    queue_item.media_item.to_legacy_online(),
                    playback_generation=generation,
                    queue_identity=identity,
                )
                return
            self.set_online_status_message(f"在线播放失败：{real_error_text}")
        elif real_error_text:
            self.lyrics_view.set_placeholder("播放失败", real_error_text)

    def get_song_data_from_item(self, item: QListWidgetItem | None) -> dict | None:
        if item is None:
            return None

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return None

        if song_data.get("demo"):
            return None

        if song_data.get("recordKind") == "remote":
            return song_data

        path = self.normalize_song_path(song_data.get("path", ""))

        if not path:
            return None

        return song_data

    def prepare_song_context_item(self, position) -> QListWidgetItem | None:
        item = self.song_list.itemAt(position)

        if item is None:
            return None

        selection_command = (
            QItemSelectionModel.SelectionFlag.NoUpdate
            if item.isSelected()
            else QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self.song_list.setCurrentItem(item, selection_command)
        return item

    def show_song_context_menu(self, position) -> None:
        item = self.prepare_song_context_item(position)

        if item is None:
            return

        song_data = self.get_song_data_from_item(item)

        if not song_data:
            return

        if song_data.get("recordKind") == "remote":
            self.show_remote_song_context_menu(item, song_data, position)
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        menu = QMenu(self)
        menu.setObjectName("songContextMenu")

        play_action = menu.addAction("播放")
        play_action.triggered.connect(lambda checked=False, selected_item=item: self.play_selected_song(selected_item))

        floating_lyrics_action = menu.addAction("打开/关闭桌面歌词")
        floating_lyrics_action.triggered.connect(self.toggle_floating_lyrics)

        next_queue_action = menu.addAction("下一首播放")
        next_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_next(selected_item))

        add_queue_action = menu.addAction("加入播放队列")
        add_queue_action.triggered.connect(lambda checked=False, selected_item=item: self.queue_selected_song_last(selected_item))

        show_queue_action = menu.addAction("查看播放队列")
        show_queue_action.triggered.connect(self.show_play_queue)

        clear_queue_action = menu.addAction("清空播放队列")
        clear_queue_action.triggered.connect(self.clear_play_queue)

        menu.addSeparator()

        if self.is_song_liked(song_path):
            like_action = menu.addAction("取消收藏")
        else:
            like_action = menu.addAction("添加到我喜欢")

        like_action.triggered.connect(lambda checked=False, selected_item=item: self.toggle_like_selected_song(selected_item))

        add_to_playlist_action = menu.addAction("添加到歌单")
        add_to_playlist_action.triggered.connect(self.add_current_song_to_playlist)

        if self.current_library_view == "liked":
            remove_from_playlist_action = menu.addAction("从我喜欢移除")
            remove_from_playlist_action.triggered.connect(self.remove_current_song_from_current_playlist)
        elif self.current_library_view.startswith("playlist:"):
            remove_from_playlist_action = menu.addAction("从当前歌单移除")
            remove_from_playlist_action.triggered.connect(self.remove_current_song_from_current_playlist)

        menu.addSeparator()

        bind_lyrics_action = menu.addAction("手动绑定歌词")
        bind_lyrics_action.triggered.connect(self.bind_selected_song_lyrics)

        if self.get_bound_lyrics_path(song_path):
            unbind_lyrics_action = menu.addAction("取消歌词绑定")
            unbind_lyrics_action.triggered.connect(self.unbind_selected_song_lyrics)

        retry_lyrics_action = menu.addAction("重新搜索歌词")
        retry_lyrics_action.triggered.connect(self.force_search_selected_lyrics)

        metadata_match_action = menu.addAction("联网匹配歌曲信息")
        metadata_match_action.triggered.connect(self.match_selected_song_metadata_online)

        retry_cover_action = menu.addAction("重新搜索封面")
        retry_cover_action.triggered.connect(self.force_search_selected_cover)

        menu.addSeparator()

        open_folder_action = menu.addAction("打开文件夹")
        open_folder_action.triggered.connect(self.open_selected_song_folder)

        song_info_action = menu.addAction("查看歌曲信息")
        song_info_action.triggered.connect(self.show_selected_song_info)

        menu.addSeparator()

        select_menu = menu.addMenu("选择")
        select_visible_action = select_menu.addAction("选择当前列表全部歌曲")
        select_visible_action.triggered.connect(self.select_all_visible_songs)

        clear_selection_action = select_menu.addAction("取消选择")
        clear_selection_action.triggered.connect(self.clear_song_selection)

        select_artist_action = select_menu.addAction("选择同一歌手")
        select_artist_action.triggered.connect(lambda checked=False, selected_item=item: self.select_same_category_songs(selected_item, "artist"))

        select_album_action = select_menu.addAction("选择同一专辑")
        select_album_action.triggered.connect(lambda checked=False, selected_item=item: self.select_same_category_songs(selected_item, "album"))

        remove_menu = menu.addMenu("移除")
        remove_selected_action = remove_menu.addAction("从音乐库移除选中歌曲")
        remove_selected_action.triggered.connect(self.remove_selected_songs_from_library)

        menu.exec(self.song_list.mapToGlobal(position))

    def show_remote_song_context_menu(
        self,
        item: QListWidgetItem,
        song_data: dict,
        position,
    ) -> None:
        remote = self.get_remote_record_from_song_data(song_data)
        if remote is None:
            return
        stable_id, record = remote
        track = RemoteTrackStore.to_online_track(stable_id, record)
        source = self.get_registered_source_safely(str(record.get("source_id") or "")) or {}
        track["sourceName"] = str(source.get("name") or record.get("source_id") or "在线来源")
        track["capabilities"] = dict(source.get("capabilities") or {})
        local_path = str(record.get("local_path") or "")
        local_exists = bool(local_path and Path(local_path).is_file())
        menu = QMenu(self)
        play_action = menu.addAction("播放")
        play_action.setEnabled(local_exists or self.is_remote_source_available(record))
        play_action.triggered.connect(
            lambda checked=False, selected_item=item: self.play_selected_song(selected_item)
        )
        next_action = menu.addAction("下一首播放")
        next_action.setEnabled(play_action.isEnabled())
        next_action.triggered.connect(
            lambda checked=False, current_track=track: self.queue_media_item_next(current_track)
        )
        if (track.get("capabilities") or {}).get("download") is True:
            download_action = menu.addAction("下载")
            download_action.setEnabled(
                self.is_remote_source_available(record)
                and not self.online_download_manager.is_active()
            )
            download_action.triggered.connect(
                lambda checked=False, current_track=track: self.request_online_download(current_track)
            )
        menu.addSeparator()
        liked_ids = self.get_playlist_remote_ids("liked")
        if stable_id in liked_ids:
            like_action = menu.addAction("取消收藏")
            like_action.triggered.connect(
                lambda checked=False, current_track=track: self.unlike_online_track(current_track)
            )
        else:
            like_action = menu.addAction("添加到我喜欢")
            like_action.triggered.connect(
                lambda checked=False, current_track=track: self.like_online_track(current_track)
            )
        playlist_menu = menu.addMenu("添加到歌单")
        playlists = self.get_online_playlist_choices()
        if not playlists:
            empty_action = playlist_menu.addAction("暂无自定义歌单")
            empty_action.setEnabled(False)
        for playlist_id, playlist_name in playlists:
            action = playlist_menu.addAction(playlist_name)
            action.triggered.connect(
                lambda checked=False, current_track=track, target_id=playlist_id:
                self.add_online_track_to_playlist(current_track, target_id)
            )
        if self.current_library_view == "liked" or self.current_library_view.startswith("playlist:"):
            remove_action = menu.addAction("从当前歌单移除")
            remove_action.triggered.connect(
                lambda checked=False, target_id=stable_id: self.remove_remote_from_current_playlist(target_id)
            )
        menu.addSeparator()
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(
            lambda checked=False, current_track=track: self.show_online_track_info(current_track)
        )
        menu.exec(self.song_list.mapToGlobal(position))

    def remove_remote_from_current_playlist(self, stable_id: str) -> None:
        if self.current_library_view == "liked":
            playlist_id = "liked"
        elif self.current_library_view.startswith("playlist:"):
            playlist_id = self.current_library_view.split("playlist:", 1)[1]
        else:
            return
        if stable_id in self.get_playlist_remote_ids(playlist_id):
            if not self.remove_remote_id_from_playlist(stable_id, playlist_id):
                return
            self.refresh_playlist_membership_views()

    def open_remote_song_folder(self, local_path: str) -> None:
        path = Path(str(local_path or ""))
        if not path.is_file():
            QMessageBox.information(self, "打开文件夹", "这首在线歌曲还没有有效的本地文件。")
            return
        try:
            os.startfile(str(path.parent))
        except Exception as error:
            QMessageBox.warning(self, "打开失败", str(error))

    def toggle_like_selected_song(self, item: QListWidgetItem | None) -> None:
        song_data = self.get_song_data_from_item(item)

        if not song_data:
            return

        song_path = self.normalize_song_path(song_data.get("path", ""))

        if not song_path:
            return

        if self.is_song_liked(song_path):
            changed = self.remove_local_path_from_playlist(song_path, "liked")
            print("已取消收藏：", song_path)
        else:
            changed = self.add_local_path_to_playlist(song_path, "liked")
            print("已加入我喜欢：", song_path)

        if not changed:
            return

        if self.current_song_path and self.normalize_song_path(self.current_song_path) == song_path:
            self.update_like_button()
            self.update_side_info_panel()

        self.refresh_playlist_membership_views()

    def open_selected_song_folder(self) -> None:
        song_path = self.get_current_selected_song_path()

        if not song_path:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return

        path = Path(song_path)

        if not path.exists():
            QMessageBox.warning(self, "文件不存在", "这个音乐文件已经不存在。")
            return

        try:
            os.startfile(str(path.parent))
        except Exception as error:
            QMessageBox.warning(self, "打开失败", str(error))

    def show_selected_song_info(self) -> None:
        item = self.song_list.currentItem()
        song_data = self.get_song_data_from_item(item)
        if not song_data:
            QMessageBox.information(self, "提示", "请先选择一首真实歌曲。")
            return
        self.show_media_item_info(self.media_item_from_song_data(song_data).to_dict())
    def closeEvent(self, event) -> None:
        if not self.shutdown_media_workers():
            print("媒体后台任务仍在安全退出，已暂缓关闭窗口。")
            event.ignore()
            self.schedule_media_worker_close_retry()
            return

        stats_saved = self.flush_current_listen_time()
        if not stats_saved:
            self.save_song_stats()

        if hasattr(self, "settings_save_timer"):
            self.settings_save_timer.stop()

        if hasattr(self, "playback_save_timer"):
            self.playback_save_timer.stop()

        if hasattr(self, "session_save_timer"):
            self.session_save_timer.stop()

        if hasattr(self, "search_debounce_timer"):
            self.cancel_pending_local_search()

        self.save_playback_session()
        floating_window = getattr(self, "floating_lyrics_window", None)

        if floating_window is not None:
            floating_window.close()
            self.floating_lyrics_window = None

        if self.immersive_lyrics_window is not None:
            self.immersive_lyrics_window.close()
            self.immersive_lyrics_window = None

        online_source_client = getattr(self, "online_source_client", None)
        unified_search_service = getattr(self, "unified_search_service", None)

        online_download_manager = getattr(self, "online_download_manager", None)

        if online_download_manager is not None:
            online_download_manager.cancel()

        if unified_search_service is not None:
            unified_search_service.shutdown()

        if online_source_client is not None:
            online_source_client.stop()

        self.flush_settings()

        super().closeEvent(event)

    def get_dark_theme_tokens(self) -> dict:
        return dict(DARK_THEME_TOKENS)

    def build_player_product_qss(self) -> str:
        t = self.get_dark_theme_tokens()
        return f"""
        QFrame#playerBar {{
            background: #10141c;
            border-top: 1px solid {t["border"]};
            border-bottom-left-radius: 22px;
            border-bottom-right-radius: 22px;
        }}

        QFrame#playerLeft,
        QFrame#playerCenter,
        QFrame#playerRight {{
            background: transparent;
            border: none;
        }}

        QPushButton#transportButton {{
            background: rgba(255, 255, 255, 0.055);
            border: 1px solid {t["border"]};
            border-radius: 21px;
            padding: 0;
        }}

        QPushButton#transportButton:hover {{
            background: rgba(255, 255, 255, 0.105);
            border-color: {t["border_strong"]};
        }}

        QPushButton#transportButton:pressed {{
            background: rgba(255, 255, 255, 0.145);
        }}

        QPushButton#transportPlayButton {{
            background: {t["accent"]};
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 25px;
            padding: 0;
        }}

        QPushButton#transportPlayButton:hover {{
            background: #65a0ff;
        }}

        QPushButton#transportPlayButton:pressed {{
            background: #3978dd;
        }}

        QLabel#playerTimeLabel,
        QLabel#volumeStateLabel {{
            color: {t["text_muted"]};
            font-family: "Segoe UI Variable Text", "Segoe UI";
            font-size: 11px;
            font-weight: 600;
        }}

        QLabel#volumeIconLabel {{
            background: transparent;
        }}

        QSlider#progressSlider::groove:horizontal,
        QSlider#volumeSlider::groove:horizontal {{
            height: 4px;
            background: rgba(255, 255, 255, 0.14);
            border-radius: 2px;
        }}

        QSlider#progressSlider::sub-page:horizontal {{
            background: {t["accent"]};
            border-radius: 2px;
        }}

        QSlider#volumeSlider::sub-page:horizontal {{
            background: #8fb8ff;
            border-radius: 2px;
        }}

        QSlider#progressSlider::handle:horizontal,
        QSlider#volumeSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0;
            background: #f8fbff;
            border: 1px solid rgba(15, 17, 23, 0.38);
            border-radius: 7px;
        }}

        QFrame#nowPlayingPanel {{
            background: #11151d;
            border-left: 1px solid {t["border"]};
            border-top-right-radius: 22px;
        }}

        QFrame#nowInfoBox {{
            background: qlineargradient(
                x1: 0, y1: 0,
                x2: 1, y2: 1,
                stop: 0 rgba(255, 255, 255, 0.070),
                stop: 1 rgba(255, 255, 255, 0.032)
            );
            border: 1px solid {t["border"]};
            border-radius: 18px;
        }}

        QLabel#coverLabel {{
            border: 1px solid {t["border_strong"]};
            border-radius: 20px;
        }}

        QLabel#nowSongTitle {{
            color: {t["text"]};
            font-size: 19px;
            font-weight: 800;
        }}

        QLabel#nowArtist {{
            color: {t["text_secondary"]};
            font-size: 13px;
        }}

        QPushButton#nowPlayingActionButton {{
            background: transparent;
            color: {t["text_muted"]};
            border: 1px solid transparent;
            border-radius: 9px;
            padding: 5px 8px;
            font-size: 12px;
        }}

        QPushButton#nowPlayingActionButton:hover {{
            background: {t["hover"]};
            color: {t["text"]};
            border-color: {t["border"]};
        }}

        QPushButton#nowPlayingActionButton:disabled {{
            background: transparent;
            color: {t["text_disabled"]};
            border-color: transparent;
        }}

        QPushButton#libraryMoreButton {{
            background: rgba(255, 255, 255, 0.055);
            color: {t["text_secondary"]};
            border: 1px solid {t["border"]};
            border-radius: 12px;
            padding: 9px 13px;
        }}

        QPushButton#libraryMoreButton:hover {{
            background: {t["hover"]};
            color: {t["text"]};
            border-color: {t["border_strong"]};
        }}

        QPushButton#libraryMoreButton::menu-indicator {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            right: 7px;
        }}

        QFrame#songTableHeader {{
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid {t["border"]};
            border-radius: 12px;
            min-height: 38px;
        }}

        QPushButton#songTableHeaderButton {{
            background: transparent;
            color: {t["text_muted"]};
            border: none;
            padding: 6px 2px;
            text-align: left;
            font-size: 12px;
            font-weight: 600;
        }}

        QPushButton#songTableHeaderButton[alignRight="true"] {{
            text-align: right;
        }}

        QPushButton#songTableHeaderButton:hover {{
            color: {t["text"]};
        }}

        QPushButton#songTableHeaderButton[sortActive="true"] {{
            color: #8fb8ff;
        }}

        QLabel#songTableHeaderLabel {{
            color: {t["text_muted"]};
            font-size: 12px;
            font-weight: 600;
        }}

        QListWidget#songList {{
            background: #10141c;
            border: 1px solid {t["border"]};
            border-radius: 16px;
            padding: 6px;
            outline: none;
        }}

        QListWidget#songList::item {{
            min-height: 58px;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 0;
            margin: 2px;
        }}

        QListWidget#songList::item:hover {{
            background: rgba(255, 255, 255, 0.055);
            border-color: rgba(255, 255, 255, 0.035);
        }}

        QListWidget#songList::item:selected {{
            background: rgba(76, 141, 255, 0.20);
            border-color: rgba(76, 141, 255, 0.46);
        }}

        QLabel#listEmptyHint {{
            background: rgba(255, 255, 255, 0.026);
            color: {t["text_muted"]};
            border: 1px dashed {t["border_strong"]};
            border-radius: 18px;
            padding: 28px;
            font-size: 14px;
        }}
        """

    def build_visual_polish_qss(self) -> str:
        t = self.get_dark_theme_tokens()
        return f"""
        QWidget#root {{
            background: {t["app_bg"]};
            color: {t["text"]};
            font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
        }}

        QFrame#shell {{
            background: {t["shell_bg"]};
            border: 1px solid {t["border"]};
            border-radius: 22px;
        }}

        QFrame#sidebar {{
            background: {t["sidebar_bg"]};
            border-right: 1px solid {t["border"]};
        }}

        QLabel#sidebarHint,
        QLabel#appSubtitle {{
            color: {t["text_weak"]};
        }}

        QPushButton#sidebarButton,
        QPushButton#playlistSidebarButton {{
            background: transparent;
            color: {t["text_muted"]};
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 9px 12px;
            text-align: left;
        }}

        QPushButton#sidebarButton:hover,
        QPushButton#playlistSidebarButton:hover {{
            background: {t["hover"]};
            color: {t["text"]};
            border: 1px solid {t["border"]};
        }}

        QPushButton#sidebarButton[active="true"],
        QPushButton#playlistSidebarButton[active="true"] {{
            background: {t["active"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
            border-left: 3px solid {t["accent"]};
            font-weight: 700;
        }}

        QPushButton#sidebarWideButton,
        QPushButton#sidebarMiniButton,
        QPushButton#playlistActionButton,
        QPushButton#secondaryButton,
        QPushButton#categoryFilterButton,
        QPushButton#nowPlayingActionButton {{
            background: rgba(255, 255, 255, 0.055);
            color: {t["text_muted"]};
            border: 1px solid {t["border"]};
            border-radius: 12px;
            padding: 9px 13px;
        }}

        QPushButton#sidebarWideButton:hover,
        QPushButton#sidebarMiniButton:hover,
        QPushButton#playlistActionButton:hover,
        QPushButton#secondaryButton:hover,
        QPushButton#categoryFilterButton:hover,
        QPushButton#nowPlayingActionButton:hover {{
            background: {t["hover"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
        }}

        QPushButton#categoryFilterButton[active="true"],
        QPushButton#secondaryButton[active="true"] {{
            background: {t["accent_soft"]};
            color: #ffffff;
            border: 1px solid rgba(59, 130, 246, 0.40);
        }}

        QPushButton#primaryButton {{
            background: {t["accent"]};
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 13px;
            padding: 10px 15px;
            font-weight: 700;
        }}

        QPushButton#primaryButton:hover {{
            background: #5594ff;
        }}

        QPushButton#dangerButton {{
            background: rgba(239, 68, 68, 0.14);
            color: #fecdd3;
            border: 1px solid rgba(239, 68, 68, 0.22);
            border-radius: 13px;
            padding: 10px 15px;
        }}

        QPushButton#dangerButton:hover {{
            background: rgba(239, 68, 68, 0.26);
            color: #ffffff;
        }}

        QFrame#libraryPanel,
        QFrame#fullLyricsPage,
        QFrame#pendingImportsPage {{
            background: {t["panel_bg"]};
            border: none;
        }}

        QLineEdit#searchInput,
        QLineEdit,
        QComboBox {{
            background: {t["sidebar_bg"]};
            color: {t["text"]};
            border: 1px solid {t["border"]};
            border-radius: 13px;
            padding: 9px 13px;
            selection-background-color: {t["accent"]};
            selection-color: #ffffff;
            placeholder-text-color: {t["placeholder"]};
        }}

        QLineEdit#searchInput:focus,
        QLineEdit:focus,
        QComboBox:focus {{
            background: #141823;
            border: 1px solid rgba(59, 130, 246, 0.55);
        }}

        QLineEdit:disabled,
        QComboBox:disabled {{
            background: {t["app_bg"]};
            color: {t["text_disabled"]};
            border-color: {t["border"]};
        }}

        QLineEdit[readOnly="true"] {{
            background: {t["app_bg"]};
            color: {t["text_muted"]};
        }}

        QLabel#categoryFilterLabel {{
            color: {t["text_muted"]};
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid {t["border"]};
            border-radius: 12px;
            padding: 7px 10px;
        }}

        QLabel#listEmptyHint,
        QLabel#pendingEmptyHint {{
            color: {t["text_muted"]};
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid {t["border"]};
            border-radius: 16px;
            padding: 18px 20px;
            line-height: 1.45;
        }}

        QListWidget#songList,
        QListWidget#pendingImportsList {{
            background: {t["sidebar_bg"]};
            color: #dfe5ef;
            border: 1px solid {t["border"]};
            border-radius: 18px;
            padding: 9px;
            outline: none;
            alternate-background-color: #141823;
        }}

        QListWidget#songList::item,
        QListWidget#pendingImportsList::item {{
            min-height: 50px;
            padding: 10px 13px;
            margin: 3px 2px;
            border-radius: 12px;
            border: 1px solid transparent;
        }}

        QListWidget#songList::item:hover,
        QListWidget#pendingImportsList::item:hover {{
            background: {t["hover"]};
            border: 1px solid {t["border"]};
            color: #ffffff;
        }}

        QListWidget#songList::item:selected,
        QListWidget#pendingImportsList::item:selected {{
            background: rgba(59, 130, 246, 0.18);
            border: 1px solid rgba(59, 130, 246, 0.42);
            color: #ffffff;
        }}

        QMenu,
        QMenu#songContextMenu {{
            background: {t["card_bg_alt"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
            border-radius: 12px;
            padding: 6px;
        }}

        QMenu::item,
        QMenu#songContextMenu::item {{
            padding: 8px 24px;
            border-radius: 8px;
        }}

        QMenu::item:selected,
        QMenu#songContextMenu::item:selected {{
            background: {t["accent_soft"]};
            color: #ffffff;
        }}

        QMenu::item:disabled,
        QMenu#songContextMenu::item:disabled {{
            background: transparent;
            color: {t["text_disabled"]};
        }}

        QMenu::separator,
        QMenu#songContextMenu::separator {{
            height: 1px;
            background: {t["border"]};
            margin: 6px 8px;
        }}

        QListWidget#songList:disabled,
        QListWidget#pendingImportsList:disabled {{
            background: {t["app_bg"]};
            color: {t["text_disabled"]};
            border-color: {t["border"]};
        }}

        QFrame#nowPlayingPanel {{
            background: {t["sidebar_bg"]};
            border-left: 1px solid {t["border"]};
        }}

        QFrame#nowInfoBox {{
            background: qlineargradient(
                x1: 0, y1: 0,
                x2: 1, y2: 1,
                stop: 0 rgba(255,255,255,0.070),
                stop: 1 rgba(255,255,255,0.036)
            );
            border: 1px solid {t["border"]};
            border-radius: 18px;
        }}

        QLabel#coverLabel {{
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #2a3244, stop: 1 #12151d);
            border: 1px solid {t["border"]};
            border-radius: 18px;
        }}

        QLabel#nowSongTitle {{
            color: {t["text"]};
            font-size: 21px;
            font-weight: 900;
        }}

        QLabel#nowArtist {{
            color: #b4bdce;
            font-size: 13px;
        }}

        QLabel#nowStats,
        QLabel#lyricsStatus,
        QLabel#sideInfoName {{
            color: {t["text_weak"]};
        }}

        QFrame#sideInfoPanel,
        QFrame#sideInfoRow {{
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid {t["border"]};
            border-radius: 14px;
        }}

        QLabel#sideInfoValue {{
            color: #dce3ee;
        }}

        QFrame#playerBar {{
            background: rgba(17, 19, 26, 0.96);
            border-top: 1px solid {t["border"]};
            border-bottom-left-radius: 22px;
            border-bottom-right-radius: 22px;
        }}

        QPushButton#playButton {{
            background: {t["accent"]};
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 16px;
            padding: 10px 15px;
            font-size: 13px;
            font-weight: 800;
        }}

        QPushButton#playButton:hover {{
            background: #5594ff;
        }}

        QPushButton#controlButton,
        QPushButton#likeButton,
        QPushButton#floatingLyricsToggleButton {{
            background: rgba(255, 255, 255, 0.055);
            color: #d9deea;
            border: 1px solid {t["border"]};
            border-radius: 13px;
            padding: 8px 11px;
        }}

        QPushButton#controlButton:hover,
        QPushButton#likeButton:hover,
        QPushButton#floatingLyricsToggleButton:hover {{
            background: {t["hover"]};
            color: #ffffff;
            border: 1px solid {t["border_strong"]};
        }}

        QSlider#progressSlider::groove:horizontal,
        QSlider#volumeSlider::groove:horizontal {{
            height: 6px;
            background: rgba(255, 255, 255, 0.12);
            border-radius: 3px;
        }}

        QSlider#progressSlider::sub-page:horizontal,
        QSlider#volumeSlider::sub-page:horizontal {{
            background: {t["accent"]};
            border-radius: 3px;
        }}

        QSlider#progressSlider::handle:horizontal,
        QSlider#volumeSlider::handle:horizontal {{
            width: 18px;
            height: 18px;
            margin: -7px 0;
            background: #f8fbff;
            border: 1px solid rgba(15, 17, 23, 0.36);
            border-radius: 9px;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 8px 2px 8px 2px;
        }}

        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.16);
            border-radius: 5px;
            min-height: 32px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: rgba(255, 255, 255, 0.25);
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
            height: 0px;
        }}

        QLabel#pageTitle {{
            color: {t["text"]};
            font-size: 24px;
            font-weight: 900;
        }}

        QLabel#pageSubtitle {{
            color: {t["text_weak"]};
            font-size: 12px;
        }}

        QPushButton#viewButton {{
            background: rgba(255, 255, 255, 0.045);
            color: {t["text_muted"]};
            border: 1px solid {t["border"]};
            border-radius: 12px;
            padding: 9px 13px;
            min-height: 18px;
        }}

        QPushButton#viewButton:hover {{
            background: {t["hover"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
        }}

        QPushButton#viewButton[active="true"] {{
            background: {t["accent_soft"]};
            color: #ffffff;
            border: 1px solid rgba(59, 130, 246, 0.40);
            font-weight: 700;
        }}

        QFrame#libraryPanel QPushButton#primaryButton,
        QFrame#libraryPanel QPushButton#secondaryButton,
        QFrame#libraryPanel QPushButton#dangerButton,
        QFrame#libraryPanel QPushButton#categoryFilterButton {{
            min-height: 20px;
            border-radius: 13px;
            padding: 9px 14px;
        }}

        QFrame#libraryPanel QPushButton#dangerButton {{
            background: rgba(239, 68, 68, 0.12);
            color: #fecdd3;
            border: 1px solid rgba(239, 68, 68, 0.24);
        }}

        QFrame#libraryPanel QPushButton#dangerButton:hover {{
            background: rgba(239, 68, 68, 0.22);
            color: #ffffff;
        }}

        QFrame#sidebarPlaylistBox {{
            background: transparent;
            border: none;
            padding: 0px;
        }}

        QPushButton#nowPlayingActionButton {{
            background: rgba(255, 255, 255, 0.040);
            color: {t["text_muted"]};
        }}
        QToolTip {{
            background: {t["card_bg_alt"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
            border-radius: 8px;
            padding: 6px 8px;
        }}

        QDialog,
        QMessageBox {{
            background: {t["app_bg"]};
            color: {t["text"]};
            font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
        }}

        QMessageBox QLabel {{
            color: {t["text"]};
        }}

        QMessageBox QPushButton {{
            background: rgba(255, 255, 255, 0.065);
            color: {t["text"]};
            border: 1px solid {t["border"]};
            border-radius: 11px;
            padding: 8px 14px;
            min-width: 72px;
        }}

        QMessageBox QPushButton:hover {{
            background: {t["hover"]};
            border: 1px solid {t["border_strong"]};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 26px;
        }}

        QComboBox QAbstractItemView,
        QAbstractItemView {{
            background: {t["card_bg_alt"]};
            color: {t["text"]};
            border: 1px solid {t["border_strong"]};
            border-radius: 10px;
            outline: none;
            selection-background-color: {t["accent_soft"]};
            selection-color: #ffffff;
        }}
        """
    def _style_sheet(self) -> str:
        return """
        QWidget#root {
            background: #0f1117;
            color: #f5f7fb;
            font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
        }

        QFrame#shell {
            background: #151821;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 22px;
        }

        QFrame#sidebar {
            background: #11131a;
            border-top-left-radius: 22px;
            border-bottom-left-radius: 22px;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }

        QScrollArea#sidebarScroll,
        QScrollArea#sidebarScroll > QWidget > QWidget#sidebarContent,
        QScrollArea#sidebarScroll QWidget#qt_scrollarea_viewport {
            background: transparent;
            border: none;
        }

        QSplitter#bodySplitter::handle {
            background: rgba(255, 255, 255, 0.035);
        }

        QLabel#appTitle {
            color: #ffffff;
            font-size: 25px;
            font-weight: 800;
        }

        QLabel#appSubtitle {
            color: #8f98aa;
            font-size: 12px;
        }

        QPushButton {
            border: none;
            outline: none;
        }

        QPushButton[active="true"] {
            background: rgba(78, 131, 255, 0.18);
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton[active="false"] {
            background: transparent;
            color: #b8bfcc;
        }

        QPushButton[active="false"]:hover {
            background: rgba(255, 255, 255, 0.07);
            color: #ffffff;
        }

        QPushButton[active="true"],
        QPushButton[active="false"] {
            text-align: left;
            padding: 11px 15px;
            border-radius: 12px;
            font-size: 14px;
        }

        QPushButton#sidebarButton {
            text-align: left;
            padding: 11px 15px;
            border-radius: 12px;
            border: 1px solid transparent;
            font-size: 14px;
        }

        QPushButton#sidebarButton[active="true"] {
            background: rgba(255, 255, 255, 0.14);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.12);
            font-weight: 700;
        }

        QPushButton#sidebarButton[active="false"] {
            background: transparent;
            color: rgba(255, 255, 255, 0.72);
            border: 1px solid transparent;
            font-weight: 500;
        }

        QPushButton#sidebarButton[active="false"]:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
        }

        QFrame#libraryPanel {
            background: #151821;
        }

        QFrame#fullLyricsPage {
            background: #151821;
        }

        QLabel#fullLyricsPageTitle {
            color: #ffffff;
            font-size: 29px;
            font-weight: 800;
        }

        QLabel#fullLyricsPageSubtitle {
            color: #8f98aa;
            font-size: 13px;
        }

        QLabel#fullLyricsSongTitle {
            color: #ffffff;
            font-size: 26px;
            font-weight: 800;
        }

        QLabel#fullLyricsArtist {
            color: #b8bfcc;
            font-size: 14px;
        }

        QLabel#fullLyricsStatus {
            color: #7f8898;
            font-size: 12px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine {
            font-size: 20px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine[lyricState="near"] {
            font-size: 24px;
        }

        QFrame#fullLyricsPage QLabel#lyricLine[lyricState="current"] {
            font-size: 34px;
            font-weight: 900;
        }

        QLabel#pageTitle {
            color: #ffffff;
            font-size: 29px;
            font-weight: 800;
        }

        QLabel#pageSubtitle {
            color: #8f98aa;
            font-size: 13px;
        }

        QLabel#listEmptyHint {
            background: rgba(255, 255, 255, 0.045);
            color: #9aa3b5;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 14px;
            padding: 12px 14px;
            font-size: 13px;
        }
        QPushButton#primaryButton {
            background: #3b82f6;
            color: #ffffff;
            border-radius: 12px;
            padding: 10px 18px;
            font-size: 14px;
            font-weight: 700;
        }

        QPushButton#primaryButton:hover {
            background: #5594ff;
        }

        QPushButton#secondaryButton {
            background: rgba(255, 255, 255, 0.07);
            color: #e5e9f2;
            border-radius: 12px;
            padding: 10px 16px;
            font-size: 13px;
        }

        QPushButton#secondaryButton:hover {
            background: rgba(255, 255, 255, 0.11);
            color: #ffffff;
        }

        QPushButton#nowPlayingActionButton {
            background: rgba(255, 255, 255, 0.065);
            color: #d9deea;
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 10px;
            padding: 7px 11px;
            font-size: 12px;
        }

        QPushButton#nowPlayingActionButton:hover {
            background: rgba(255, 255, 255, 0.11);
            color: #ffffff;
        }

        QPushButton#nowPlayingActionButton:disabled {
            background: rgba(255, 255, 255, 0.035);
            color: #7b8494;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }

        QLabel#pendingEmptyHint {
            background: rgba(255, 255, 255, 0.045);
            color: #9aa3b5;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 14px;
            padding: 12px 14px;
            font-size: 13px;
        }
        QPushButton#viewButton {
            background: rgba(255, 255, 255, 0.06);
            color: #b8bfcc;
            border-radius: 12px;
            padding: 8px 14px;
            font-size: 13px;
        }

        QPushButton#viewButton:hover {
            background: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }

        QPushButton#viewButton[active="true"] {
            background: #3b82f6;
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton#categoryFilterButton {
            background: rgba(255, 255, 255, 0.055);
            color: #cfd6e3;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 8px 12px;
            font-size: 13px;
        }

        QPushButton#categoryFilterButton:hover {
            background: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }

        QPushButton#categoryFilterButton[active="true"] {
            background: rgba(59, 130, 246, 0.22);
            color: #ffffff;
            border: 1px solid rgba(59, 130, 246, 0.42);
            font-weight: 700;
        }

        QLabel#categoryFilterLabel {
            color: #8f98aa;
            font-size: 12px;
            padding: 0 4px;
        }

        QLabel#sidebarSectionTitle {
            color: #737d90;
            font-size: 12px;
            font-weight: 700;
            padding: 8px 4px 2px 4px;
        }

        QFrame#sidebarPlaylistBox {
            background: transparent;
        }

        QPushButton#playlistSidebarButton {
            background: transparent;
            color: #b8bfcc;
            text-align: left;
            border-radius: 11px;
            padding: 9px 12px;
            font-size: 13px;
        }

        QPushButton#playlistSidebarButton:hover {
            background: rgba(255, 255, 255, 0.07);
            color: #ffffff;
        }

        QPushButton#playlistSidebarButton[active="true"] {
            background: rgba(59, 130, 246, 0.92);
            color: #ffffff;
            font-weight: 700;
        }

        QPushButton#sidebarWideButton {
            background: rgba(255, 255, 255, 0.06);
            color: #d7ddea;
            border-radius: 11px;
            padding: 9px 12px;
            font-size: 12px;
            text-align: left;
        }

        QPushButton#sidebarWideButton:hover {
            background: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }

        QPushButton#sidebarMiniButton {
            background: rgba(255, 255, 255, 0.06);
            color: #d7ddea;
            border-radius: 11px;
            padding: 8px 10px;
            font-size: 12px;
        }

        QPushButton#sidebarMiniButton:hover {
            background: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }

        QLabel#sidebarHint {
            color: #737d90;
            font-size: 11px;
            padding: 2px 4px;
        }

        QMenu#songContextMenu {
            background: #1a1e28;
            color: #e5e9f2;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            padding: 6px;
        }

        QMenu#songContextMenu::item {
            padding: 8px 24px;
            border-radius: 7px;
        }

        QMenu#songContextMenu::item:selected {
            background: #3b82f6;
            color: #ffffff;
        }

        QMenu#songContextMenu::separator {
            height: 1px;
            background: rgba(255, 255, 255, 0.08);
            margin: 6px 8px;
        }

        QPushButton#playlistActionButton {
            background: rgba(255, 255, 255, 0.06);
            color: #d7ddea;
            border-radius: 11px;
            padding: 8px 12px;
            font-size: 12px;
        }

        QPushButton#playlistActionButton:hover {
            background: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }

        QPushButton#dangerButton {
            background: rgba(239, 68, 68, 0.15);
            color: #ffd7dc;
            border-radius: 12px;
            padding: 10px 16px;
            font-size: 13px;
        }

        QPushButton#dangerButton:hover {
            background: rgba(239, 68, 68, 0.26);
            color: #ffffff;
        }

        QLineEdit#searchInput {
            background: #11131a;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 11px 15px;
            font-size: 14px;
            selection-background-color: #3b82f6;
        }

        QLineEdit#searchInput:focus {
            border: 1px solid #4c8dff;
            background: #141823;
        }

        QListWidget#songList {
            background: #11131a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 10px;
            color: #e5e9f2;
            font-size: 14px;
            outline: none;
        }

        QListWidget#songList::item {
            padding: 15px 14px;
            border-radius: 12px;
            margin: 3px;
        }

        QListWidget#songList::item:hover {
            background: rgba(255, 255, 255, 0.07);
        }

        QListWidget#songList::item:selected {
            background: rgba(59, 130, 246, 0.92);
            color: #ffffff;
        }

        QListWidget#pendingImportsList {
            background: #11131a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            padding: 10px;
            color: #e5e9f2;
            font-size: 13px;
            outline: none;
        }

        QListWidget#pendingImportsList::item {
            padding: 12px 14px;
            border-radius: 12px;
            margin: 4px;
        }

        QListWidget#pendingImportsList::item:hover {
            background: rgba(255, 255, 255, 0.07);
        }

        QListWidget#pendingImportsList::item:selected {
            background: rgba(59, 130, 246, 0.86);
            color: #ffffff;
        }

        QFrame#nowPlayingPanel {
            background: #11131a;
            border-left: 1px solid rgba(255, 255, 255, 0.06);
            border-top-right-radius: 22px;
        }

        QFrame#nowInfoBox {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
        }

        QLabel#sectionTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: 800;
        }

        QLabel#coverLabel {
            background: qlineargradient(
                x1: 0, y1: 0,
                x2: 1, y2: 1,
                stop: 0 #293142,
                stop: 1 #11131a
            );
            color: #ffffff;
            font-size: 36px;
            font-weight: 700;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 22px;
        }

        QLabel#nowSongTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: 800;
        }

        QLabel#nowArtist {
            color: #a5adbd;
            font-size: 13px;
        }

        QLabel#nowStats {
            color: #7f8898;
            font-size: 12px;
        }

        QLabel#lyricsStatus {
            color: #7f8898;
            font-size: 12px;
        }

        QFrame#sideInfoPanel {
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
        }

        QLabel#sideInfoTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: 800;
        }

        QLabel#sideInfoHint {
            color: #8f98aa;
            font-size: 12px;
        }

        QFrame#sideInfoRow {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
        }

        QLabel#sideInfoName {
            color: #7f8898;
            font-size: 11px;
            font-weight: 700;
        }

        QLabel#sideInfoValue {
            color: #e5e9f2;
            font-size: 13px;
        }

        QLabel#sideInfoFileValue {
            color: #9aa3b5;
            font-size: 11px;
        }

        QScrollArea#lyricsView {
            background: transparent;
            border: none;
        }

        QWidget#lyricsContent {
            background: transparent;
        }

        QLabel#lyricPlaceholderTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: 700;
        }

        QLabel#lyricPlaceholderSubtitle {
            color: #8f98aa;
            font-size: 13px;
        }

        QLabel#lyricLine {
            color: #687386;
            font-size: 15px;
            font-weight: 500;
            padding: 2px 4px;
        }

        QLabel#lyricLine[lyricState="near"] {
            color: #b8bfcc;
            font-size: 17px;
            font-weight: 600;
        }

        QLabel#lyricLine[lyricState="current"] {
            color: #ffffff;
            font-size: 22px;
            font-weight: 800;
        }

        QFrame#playerBar {
            background: #10131a;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom-left-radius: 22px;
            border-bottom-right-radius: 22px;
        }

        QFrame#playerLeft,
        QFrame#playerCenter,
        QFrame#playerRight {
            background: transparent;
        }

        QLabel#bottomSongTitle {
            color: #ffffff;
            font-size: 14px;
            font-weight: 700;
        }

        QLabel#bottomSongArtist {
            color: #8f98aa;
            font-size: 12px;
        }

        QLabel#volumeLabel {
            color: #8f98aa;
            font-size: 12px;
        }

        QPushButton#controlButton {
            background: rgba(255, 255, 255, 0.075);
            color: #ffffff;
            border-radius: 12px;
            padding: 10px 10px;
            font-size: 13px;
        }

        QPushButton#controlButton:hover {
            background: rgba(255, 255, 255, 0.13);
        }

        QPushButton#likeButton {
            background: rgba(255, 255, 255, 0.075);
            color: #ffffff;
            border-radius: 12px;
            padding: 10px 10px;
            font-size: 13px;
        }

        QPushButton#likeButton:hover {
            background: rgba(255, 255, 255, 0.13);
        }

        QPushButton#likeButton[liked="true"] {
            background: rgba(236, 72, 153, 0.20);
            color: #ff8fb3;
            font-weight: 700;
        }

        QPushButton#likeButton[liked="true"]:hover {
            background: rgba(236, 72, 153, 0.30);
            color: #ffffff;
        }

        QPushButton#likeButton:disabled {
            background: rgba(255, 255, 255, 0.045);
            color: #7b8494;
        }

        QSlider#progressSlider,
        QSlider#volumeSlider {
            background: transparent;
            min-height: 32px;
        }

        QSlider#progressSlider::groove:horizontal,
        QSlider#volumeSlider::groove:horizontal {
            height: 5px;
            background: rgba(255, 255, 255, 0.14);
            border-radius: 3px;
        }

        QSlider#progressSlider::handle:horizontal,
        QSlider#volumeSlider::handle:horizontal {
            width: 16px;
            height: 16px;
            margin: -6px 0;
            background: #ffffff;
            border-radius: 8px;
        }

        QSlider#progressSlider::sub-page:horizontal,
        QSlider#volumeSlider::sub-page:horizontal {
            background: #3b82f6;
            border-radius: 3px;
        }

        QToolTip {
            background: #1b1f2a;
            color: #f5f7fb;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 8px;
            padding: 6px 8px;
            font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
        }

        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 4px 2px 4px 2px;
        }

        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.16);
            border-radius: 5px;
            min-height: 32px;
        }

        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 0.24);
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
            border: none;
            height: 0px;
        }
        QPushButton#sidebarButton[active="true"] {
            background: rgba(255, 255, 255, 0.13);
            border-left: 3px solid #3b82f6;
            padding-left: 12px;
        }

        QPushButton#playlistSidebarButton[active="true"] {
            background: rgba(59, 130, 246, 0.18);
            border-left: 3px solid #3b82f6;
            padding-left: 9px;
        }

        QListWidget#songList {
            background: #10131a;
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 18px;
            padding: 8px;
            alternate-background-color: #141823;
        }

        QListWidget#songList::item {
            min-height: 48px;
            padding: 9px 12px;
            border-radius: 12px;
            margin: 3px 2px;
            color: #dfe4ee;
        }

        QListWidget#songList::item:hover {
            background: rgba(255, 255, 255, 0.07);
            color: #ffffff;
        }

        QListWidget#songList::item:selected {
            background: rgba(59, 130, 246, 0.20);
            color: #ffffff;
            border: 1px solid rgba(59, 130, 246, 0.42);
        }

        QFrame#nowPlayingPanel {
            background: #11131a;
        }

        QFrame#nowInfoBox {
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(255,255,255,0.065), stop: 1 rgba(255,255,255,0.035));
            border: 1px solid rgba(255, 255, 255, 0.065);
            border-radius: 18px;
        }

        QLabel#nowSongTitle {
            font-size: 20px;
            font-weight: 900;
        }

        QLabel#nowArtist {
            color: #b4bdce;
            font-size: 13px;
        }

        QLabel#nowStats,
        QLabel#lyricsStatus {
            color: #818b9d;
            font-size: 12px;
        }

        QPushButton#playButton {
            background: #3b82f6;
            color: #ffffff;
            border-radius: 15px;
            padding: 10px 14px;
            font-size: 13px;
            font-weight: 800;
        }

        QPushButton#playButton:hover {
            background: #5594ff;
        }

        QPushButton#controlButton {
            background: rgba(255, 255, 255, 0.06);
            color: #d9deea;
        }

        QPushButton#floatingLyricsToggleButton {
            background: rgba(255, 255, 255, 0.075);
            color: #ffffff;
            border-radius: 12px;
            padding: 8px 10px;
            font-size: 13px;
        }

        QPushButton#floatingLyricsToggleButton:hover {
            background: rgba(255, 255, 255, 0.13);
        }

        QSlider#progressSlider::groove:horizontal,
        QSlider#volumeSlider::groove:horizontal {
            height: 6px;
            background: rgba(255, 255, 255, 0.13);
            border-radius: 3px;
        }

        QSlider#progressSlider::handle:horizontal,
        QSlider#volumeSlider::handle:horizontal {
            width: 18px;
            height: 18px;
            margin: -7px 0;
            background: #f8fbff;
            border: 1px solid rgba(15, 17, 23, 0.32);
            border-radius: 9px;
        }        """
