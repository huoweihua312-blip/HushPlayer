"""普通歌词页（Apple Music 风格：左侧信息 + 右侧同步歌词）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.logging_setup import log_exception
from ...core.theme import Metrics, rgba, theme
from ...lyrics.service import STATUS_ERROR, STATUS_INSTRUMENTAL, STATUS_NONE, STATUS_OK, LyricsResult
from ...model.track import Track
from ..context import ctx
from ..widgets.common import IconButton, TextButton
from ..widgets.cover import CoverWidget
from ..widgets.lyrics_view import LyricsView
from .page import Page

MAX_COVER = 288

PROVIDER_LABELS = {
    "local": "本地文件",
    "embedded": "内嵌标签",
    "lrclib": "LRCLIB",
    "manual": "手动绑定",
    "cache": "本地缓存",
    "online": "在线音源",
}


class LyricsPage(Page):
    route = "lyrics"
    title = "歌词"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._track: Track | None = None
        self._result: LyricsResult | None = None
        self._offset = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setSingleShot(True)
        self._loading_timer.setInterval(250)
        self._loading_timer.timeout.connect(self._show_loading)

        self.content_layout.setContentsMargins(Metrics.page_pad, 16, Metrics.page_pad - 6, 8)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(30)
        root.addWidget(self._build_side(), 0)
        root.addWidget(self._build_stage(), 1)
        self.content_layout.addLayout(root, 1)

        player = ctx().player
        player.track_changed.connect(self._on_track_changed)
        player.position_changed.connect(self._on_position)
        player.state_changed.connect(self._on_state)
        ctx().lyrics.resolved.connect(self._on_resolved)
        ctx().settings.changed.connect(self._on_setting)
        self.refresh_theme()

    # ------------------------------------------------------------------ 布局
    def _build_side(self) -> QWidget:
        panel = QWidget(self)
        panel.setFixedWidth(MAX_COVER)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 4, 0, 0)
        box.setSpacing(14)

        self.cover = CoverWidget(MAX_COVER, radius=18, shadow=True, parent=panel)
        box.addWidget(self.cover, 0, Qt.AlignHCenter)

        self.title_label = QLabel("未在播放", panel)
        self.title_label.setWordWrap(True)
        self.artist_label = QLabel("", panel)
        self.album_label = QLabel("", panel)
        box.addWidget(self.title_label)
        box.addWidget(self.artist_label)
        box.addWidget(self.album_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)
        self.favorite_button = IconButton("heart", size=34, icon_size=18, tooltip="添加到我喜欢")
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.desktop_button = IconButton("monitor", size=34, icon_size=18, tooltip="桌面歌词")
        self.desktop_button.clicked.connect(self._toggle_desktop_lyrics)
        self.immersive_button = TextButton("沉浸模式", icon_name="immersive", size=34, accent=True)
        self.immersive_button.clicked.connect(self._open_immersive)
        actions.addWidget(self.favorite_button)
        actions.addWidget(self.desktop_button)
        actions.addWidget(self.immersive_button)
        actions.addStretch(1)
        box.addLayout(actions)

        box.addSpacing(6)
        self.provider_label = QLabel("", panel)
        self.provider_label.setWordWrap(True)
        box.addWidget(self.provider_label)

        offset_row = QHBoxLayout()
        offset_row.setContentsMargins(0, 0, 0, 0)
        offset_row.setSpacing(6)
        self._offset_minus = IconButton("minus", size=28, icon_size=14, tooltip="歌词提前 0.5 秒")
        self._offset_minus.clicked.connect(lambda: self.shift_offset(-500))
        self._offset_plus = IconButton("plus", size=28, icon_size=14, tooltip="歌词延后 0.5 秒")
        self._offset_plus.clicked.connect(lambda: self.shift_offset(500))
        self.offset_label = QLabel("偏移 0.0s", panel)
        self._offset_reset = TextButton("重置", size=26)
        self._offset_reset.clicked.connect(lambda: self.set_offset(0))
        offset_row.addWidget(self._offset_minus)
        offset_row.addWidget(self._offset_plus)
        offset_row.addWidget(self.offset_label, 1)
        offset_row.addWidget(self._offset_reset)
        box.addLayout(offset_row)
        box.addStretch(1)
        return panel

    def _build_stage(self) -> QWidget:
        stage = QWidget(self)
        box = QVBoxLayout(stage)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        self.hint_label = QLabel("", stage)
        toolbar.addWidget(self.hint_label, 1)
        self.translate_button = IconButton("translate", size=32, icon_size=17, tooltip="显示翻译", checkable=True)
        self.translate_button.toggled.connect(self._toggle_translation)
        self.smaller_button = IconButton("minus_circle", size=30, icon_size=16, tooltip="缩小歌词")
        self.smaller_button.clicked.connect(lambda: self.scale_font(-0.1))
        self.larger_button = IconButton("plus", size=30, icon_size=16, tooltip="放大歌词")
        self.larger_button.clicked.connect(lambda: self.scale_font(0.1))
        self.refresh_button = IconButton("refresh", size=32, icon_size=17, tooltip="重新获取歌词")
        self.refresh_button.clicked.connect(self._reload_lyrics)
        for button in (
            self.translate_button,
            self.smaller_button,
            self.larger_button,
            self.refresh_button,
        ):
            toolbar.addWidget(button)
        box.addLayout(toolbar)

        self.view = LyricsView(stage)
        self.view.seek_requested.connect(self._seek)
        box.addWidget(self.view, 1)
        return stage

    # ------------------------------------------------------------------ 主题
    def refresh_theme(self) -> None:
        palette = theme().palette
        self.title_label.setStyleSheet(
            f"color:{palette.text};font-size:{17 * theme().font_scale:.1f}pt;font-weight:700;"
        )
        self.artist_label.setStyleSheet(
            f"color:{palette.text_secondary};"
            f"font-size:{11.4 * theme().font_scale:.1f}pt;"
        )
        self.album_label.setStyleSheet(
            f"color:{palette.text_tertiary};"
            f"font-size:{9.6 * theme().font_scale:.1f}pt;"
        )
        self.provider_label.setStyleSheet(
            f"color:{palette.text_tertiary};font-size:{8.8 * theme().font_scale:.1f}pt;"
        )
        self.offset_label.setStyleSheet(
            f"color:{palette.text_secondary};font-size:{9 * theme().font_scale:.1f}pt;"
        )
        self.hint_label.setStyleSheet(
            f"color:{palette.text_tertiary};font-size:{9 * theme().font_scale:.1f}pt;"
        )
        self.view.refresh_theme()

    # ------------------------------------------------------------------ 数据
    def on_show(self, payload: object = None) -> None:
        track = ctx().player.current if not isinstance(payload, Track) else payload
        if track is not self._track:
            self._on_track_changed(track)
        elif track is not None and self._result is None:
            self._request_lyrics(track)

    def _on_track_changed(self, track: Track | None) -> None:
        self._track = track
        self._result = None
        if track is None:
            self.cover.set_track(None)
            self.title_label.setText("未在播放")
            self.artist_label.setText("")
            self.album_label.setText("")
            self.provider_label.setText("")
            self.view.set_document(None)
            self.view.set_empty_text("未在播放", "选择一首歌曲，歌词会显示在这里")
            self.hint_label.setText("")
            self._update_translate_button(False)
            return
        self.cover.set_track(track)
        self.title_label.setText(track.title or "未知歌曲")
        self.artist_label.setText(track.artist or "未知艺术家")
        album = track.album or ""
        self.album_label.setText(album)
        self._offset = ctx().lyrics.offset_for(track)
        self._offset_label()
        self._sync_favorite()
        self._request_lyrics(track)
        self._update_translate_button(False)

    def _request_lyrics(self, track: Track, *, force: bool = False) -> None:
        self.view.set_empty_text("正在加载歌词…", "")
        self._loading_timer.start()
        try:
            result = ctx().lyrics.request(track, force=force)
        except Exception as exc:  # noqa: BLE001
            log_exception("获取歌词失败", exc)
            self.view.set_empty_text("歌词加载失败", "请检查网络连接后重试")
            return
        if result is not None and result.track_id == getattr(track, "id", ""):
            self._apply_result(result)

    def _show_loading(self) -> None:
        if self._result is None:
            self.view.set_empty_text("正在加载歌词…", "")

    def _on_resolved(self, result: LyricsResult) -> None:
        if self._track is None or result.track_id != self._track.id:
            return
        self._loading_timer.stop()
        self._apply_result(result)

    def _apply_result(self, result: LyricsResult) -> None:
        # Re-parsing the *same* track (offset calibration, translation, font
        # change) must not reset the scroll position to the first line.
        same_track = self._result is not None and self._result.track_id == result.track_id
        self._result = result
        document = result.document
        provider = PROVIDER_LABELS.get(result.provider, result.provider or result.status)
        self.provider_label.setText(f"歌词来源 · {provider}" if result.status == STATUS_OK else "")
        if result.status == STATUS_OK and document is not None and not document.is_empty():
            self.view.set_document(document, keep_position=same_track)
            self._update_translate_button(document.has_translation)
            self.translate_button.setChecked(
                bool(ctx().settings.get("lyrics.translate", True)) and document.has_translation
            )
            self.view.set_show_translation(self.translate_button.isChecked())
            self.view.set_font_scale(float(ctx().settings.get("lyrics.font_scale", 1.0)))
            kind = document.kind
            if kind == "plain":
                self.hint_label.setText("逐行歌词 · 无时间轴")
            elif document.has_word_timing:
                self.hint_label.setText("逐字歌词")
            else:
                self.hint_label.setText("逐行歌词")
            self.view.set_position(ctx().player.position)
            return

        self.view.set_document(None)
        self._update_translate_button(False)
        if result.status == STATUS_INSTRUMENTAL:
            self.view.set_empty_text("纯音乐", "这首歌没有歌词，请静候")
            self.hint_label.setText("纯音乐")
        elif result.status == STATUS_NONE:
            message = result.message or "没有找到这首歌的歌词"
            self.view.set_empty_text("暂无歌词", message)
            self.hint_label.setText("")
        elif result.status == STATUS_ERROR:
            self.view.set_empty_text("歌词加载失败", result.message or "请稍后重试")
            self.hint_label.setText("")
        else:
            self.view.set_empty_text("暂无歌词", "")
            self.hint_label.setText("")

    def _sync_favorite(self) -> None:
        if self._track is None:
            return
        favorite = ctx().library.is_favorite(self._track)
        self.favorite_button.set_icon("heart_fill" if favorite else "heart")
        self.favorite_button.setToolTip("从我喜欢中移除" if favorite else "添加到我喜欢")

    def _update_translate_button(self, available: bool) -> None:
        self.translate_button.setEnabled(bool(available))

    def _offset_label(self) -> None:
        if not hasattr(self, "offset_label"):
            return
        self.offset_label.setText(f"偏移 {self._offset / 1000:+.1f}s")

    # ------------------------------------------------------------------ 播放同步
    def _on_position(self, position: int) -> None:
        self.view.set_position(position)

    def _on_state(self, state: str) -> None:
        if state in ("paused", "stopped"):
            self.view.set_position(ctx().player.position)

    def _seek(self, position_ms: int) -> None:
        ctx().player.seek(position_ms)

    # ------------------------------------------------------------------ 操作
    def _toggle_favorite(self) -> None:
        if self._track is None:
            return
        favorite = ctx().library.toggle_favorite(self._track)
        self._sync_favorite()
        ctx().window.toast("已添加到我喜欢" if favorite else "已从我喜欢中移除")

    def _toggle_desktop_lyrics(self) -> None:
        from ..desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            ctx().window.toast("桌面歌词暂时不可用", "warning")
            return
        window.toggle()

    def _open_immersive(self) -> None:
        ctx().window.open_immersive()

    def _toggle_translation(self, checked: bool) -> None:
        self.view.set_show_translation(bool(checked))
        ctx().settings.set("lyrics.translate", bool(checked), save=True)

    def _reload_lyrics(self) -> None:
        if self._track is None:
            return
        ctx().lyrics.invalidate(self._track.id)
        self._request_lyrics(self._track, force=True)

    def shift_offset(self, delta_ms: int) -> None:
        self.set_offset(self._offset + delta_ms)

    def set_offset(self, offset_ms: int) -> None:
        if self._track is None:
            return
        offset_ms = max(-60_000, min(60_000, int(offset_ms)))
        self._offset = offset_ms
        document = ctx().lyrics.set_offset(self._track, offset_ms)
        self._offset_label()
        if document is not None and self._result is not None:
            self._result.document = document
            self.view.set_document(document, keep_position=True)
            self.view.set_position(ctx().player.position)

    def scale_font(self, delta: float) -> None:
        current = float(ctx().settings.get("lyrics.font_scale", 1.0))
        value = max(0.7, min(1.8, current + delta))
        ctx().settings.set("lyrics.font_scale", value)
        self.view.set_font_scale(value)

    def _on_setting(self, key: str, value: object) -> None:
        if key == "lyrics.font_scale":
            self.view.set_font_scale(float(value or 1.0))
        elif key == "lyrics.translate":
            self.translate_button.setChecked(bool(value))
