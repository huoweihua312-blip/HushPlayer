from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, QPoint, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QPushButton

from app.models.media_item import MediaItem
from app.ui.main_window import ImmersiveLyricsWindow, LyricsView


class FakeMediaPlayer(QObject):
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playbackStateChanged = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._position = 0
        self._duration = 286_000
        self._state = QMediaPlayer.PlaybackState.PausedState

    def position(self) -> int:
        return self._position

    def duration(self) -> int:
        return self._duration

    def playbackState(self):
        return self._state

    def setPosition(self, value: int) -> None:
        self._position = max(0, min(self._duration, int(value)))
        self.positionChanged.emit(self._position)

    def set_duration(self, value: int) -> None:
        self._duration = max(0, int(value))
        self.durationChanged.emit(self._duration)

    def set_state(self, state) -> None:
        self._state = state
        self.playbackStateChanged.emit(state)


class StubMainWindow(QObject):
    liked_state_changed = Signal(str, bool)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.settings = {"immersive_auto_hide_ui": False}
        self.media_player = FakeMediaPlayer()
        self.current_volume = 72
        self.play_mode = "list_loop"
        self.current_song_path = str(root / "local-track.mp3")
        self.current_media_item = MediaItem.from_local(
            {
                "path": self.current_song_path,
                "title": "本地测试歌曲",
                "artist": "本地歌手",
                "album": "本地专辑",
            }
        )
        self._liked = False
        self.closed_count = 0
        self.previous_count = 0
        self.play_count = 0
        self.next_count = 0
        self.volume_changes: list[int] = []
        self.expected_immersive_track_key = ""

    def get_hush_settings(self) -> dict:
        return dict(self.settings)

    def get_user_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def save_hush_settings(self, updates: dict, *, immediate: bool = False) -> bool:
        _ = immediate
        self.settings.update(dict(updates))
        return True

    def current_track_identity(self) -> str:
        return self.current_media_item.stable_identity

    def get_immersive_track_key(self) -> str:
        return self.expected_immersive_track_key

    def is_media_item_liked(self, _item: MediaItem) -> bool:
        return self._liked

    def toggle_like_current_song(self) -> None:
        self._liked = not self._liked
        self.liked_state_changed.emit(self.current_track_identity(), self._liked)

    def play_previous_song(self) -> None:
        self.previous_count += 1

    def toggle_play(self) -> None:
        self.play_count += 1
        state = self.media_player.playbackState()
        next_state = (
            QMediaPlayer.PlaybackState.PausedState
            if state == QMediaPlayer.PlaybackState.PlayingState
            else QMediaPlayer.PlaybackState.PlayingState
        )
        self.media_player.set_state(next_state)

    def play_next_song(self) -> None:
        self.next_count += 1

    def toggle_play_mode(self) -> None:
        self.play_mode = "shuffle" if self.play_mode != "shuffle" else "sequence"

    def change_volume(self, value: int) -> None:
        self.current_volume = int(value)
        self.volume_changes.append(int(value))

    def on_immersive_lyrics_closed(self) -> None:
        self.closed_count += 1


def wait_until(app: QApplication, predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def make_cover(color: str) -> QPixmap:
    image = QImage(720, 720, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(color))
    return QPixmap.fromImage(image)


def send_wheel(widget, *, touchpad: bool = False) -> None:
    event = QWheelEvent(
        QPointF(20, 20),
        QPointF(20, 20),
        QPoint(0, -28) if touchpad else QPoint(),
        QPoint() if touchpad else QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate if touchpad else Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def send_drag(widget) -> None:
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(24, 220),
        QPointF(124, 320),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(24, 130),
        QPointF(124, 230),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(24, 130),
        QPointF(124, 230),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, press)
    QApplication.sendEvent(widget, move)
    QApplication.sendEvent(widget, release)


def run_test(app: QApplication, root: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    opened_at = time.perf_counter()
    main = StubMainWindow(root)
    window = ImmersiveLyricsWindow(main)
    main.immersive_lyrics_window = window
    window.resize(1400, 900)
    window.show()
    assert wait_until(app, lambda: window.isVisible())
    metrics["first_open_ms"] = (time.perf_counter() - opened_at) * 1000

    assert window._responsive_mode == "wide"
    assert window.body_layout.direction() == QBoxLayout.Direction.LeftToRight
    assert window.cover_label.isVisible()
    header_buttons = window.control_header.findChildren(QPushButton)
    header_texts = [button.text() for button in header_buttons]
    assert header_texts == ["进入全屏", "显示设置", "退出沉浸"]
    assert "窗口模式" not in header_texts
    assert "退出全屏" not in header_texts
    assert sum(
        button.text() == "退出沉浸"
        for button in window.findChildren(QPushButton)
    ) == 1
    assert not any(
        button.text() == "退出沉浸"
        for button in window.footer.findChildren(QPushButton)
    )
    assert window.cover_label.parentWidget() is window.artwork_content
    assert window.track_info.parentWidget() is window.artwork_content
    assert window.artwork_layout.itemAt(0).spacerItem() is not None
    assert (
        window.artwork_layout.itemAt(window.artwork_layout.count() - 1).spacerItem()
        is not None
    )
    assert window.artwork_content.y() > 0
    assert (
        window.artwork_panel.height()
        - window.artwork_content.geometry().bottom()
        > window.artwork_content.y()
    )
    assert window._resize_edges_at(window.mapToGlobal(QPoint(1, 1))) == (
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge
    )
    assert not window._resize_edges_at(
        window.mapToGlobal(QPoint(window.width() // 2, window.height() // 2))
    )
    assert window.lyrics_view.target_position_ratio == 0.46
    assert window.lyrics_view.scroll_animation.duration() == 240
    assert window.lyrics_view.auto_resume_timer.interval() == 6000
    connection_count = len(window._external_connections)
    window.connect_main_window_signals()
    assert len(window._external_connections) == connection_count

    window.auto_hide_enabled = True
    window.lyrics_view.setFocus()
    window.hide_controls_if_needed()
    assert not window.ui_visible
    window.fullscreen_btn.setFocus()
    app.processEvents()
    assert window.ui_visible
    window.lyrics_view.setFocus()
    window.hide_controls_if_needed()
    assert not window.ui_visible
    window.show_controls_temporarily()
    assert window.ui_visible
    window.auto_hide_enabled = False
    window.hide_ui_timer.stop()
    window.set_controls_visible(True, animate=False)

    assert window.progress_layout.itemAt(0).widget() is window.immersive_current_time
    assert window.progress_layout.itemAt(2).widget() is window.immersive_total_time
    main.media_player.set_duration(286_000)
    main.media_player.setPosition(0)
    app.processEvents()
    assert window.immersive_current_time.text() == "0:00"
    assert window.immersive_total_time.text() == "4:46"

    local_identity = main.current_track_identity()
    lyrics = [(index * 1000, f"第 {index + 1} 行歌词 mixed English 123") for index in range(30)]
    window.update_track_timing(local_identity, 0)
    window.update_song_info(
        "本地测试歌曲",
        "本地歌手 · 本地专辑 · 本地",
        "已加载本地歌词",
        local_identity,
    )
    window.set_lyrics(lyrics, local_identity)
    window.update_position(15_500, lyrics, local_identity)
    assert wait_until(app, lambda: window.lyrics_view.current_index == 15)
    assert window.lyrics_view.labels[15].property("lyricState") == "current"
    assert window.lyrics_view.labels[14].property("lyricState") == "near"
    assert window.lyrics_view.labels[12].property("lyricState") == "context"
    assert len(window.lyrics_view.labels[15].findChildren(type(window.lyrics_view.labels[15]))) == 0

    assert wait_until(app, lambda: not window.responsive_layout_timer.isActive())
    window.lyrics_view.scroll_animation.stop()
    window.lyrics_view.scroll_to_index(15, animate=False)
    app.processEvents()
    label_center = (
        window.lyrics_view.labels[15].y()
        + window.lyrics_view.labels[15].height() // 2
        - window.lyrics_view.verticalScrollBar().value()
    )
    expected_center = round(window.lyrics_view.viewport().height() * 0.46)
    assert abs(label_center - expected_center) <= 3

    animation_id = id(window.lyrics_view.scroll_animation)
    window.update_position(16_100, lyrics, local_identity)
    window.update_position(17_100, lyrics, local_identity)
    window.update_position(18_100, lyrics, local_identity)
    assert id(window.lyrics_view.scroll_animation) == animation_id
    assert window.lyrics_view.current_index == 18
    assert window.lyrics_view.scroll_animation.state() == QAbstractAnimation.State.Running

    send_wheel(window.lyrics_view.viewport())
    app.processEvents()
    assert not window.lyrics_view.auto_follow
    assert window.return_current_btn.isVisible()
    assert window.lyrics_view.auto_resume_timer.isActive()
    remaining_before = window.lyrics_view.auto_resume_timer.remainingTime()
    QTest.qWait(35)
    send_wheel(window.lyrics_view.viewport(), touchpad=True)
    app.processEvents()
    remaining_after = window.lyrics_view.auto_resume_timer.remainingTime()
    assert remaining_after > remaining_before - 20
    window.lyrics_view._manual_pointer_active = True
    window.lyrics_view.resume_auto_follow()
    assert not window.lyrics_view.auto_follow
    assert window.lyrics_view.auto_resume_timer.isActive()
    window.lyrics_view._manual_pointer_active = False

    scroll_before = window.lyrics_view.verticalScrollBar().value()
    window.update_position(19_100, lyrics, local_identity)
    app.processEvents()
    assert window.lyrics_view.current_index == 19
    assert window.lyrics_view.verticalScrollBar().value() == scroll_before

    send_drag(window.lyrics_view.viewport())
    app.processEvents()
    assert not window.lyrics_view.auto_follow
    assert window.lyrics_view.auto_resume_timer.isActive()
    QTest.mouseClick(window.return_current_btn, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert window.lyrics_view.auto_follow
    assert not window.return_current_btn.isVisible()
    assert not window.lyrics_view.auto_resume_timer.isActive()

    window.lyrics_view.auto_resume_timer.setInterval(60)
    window.lyrics_view.note_manual_browse_activity()
    assert wait_until(app, lambda: window.lyrics_view.auto_follow, timeout=1.0)
    assert not window.return_current_btn.isVisible()
    window.lyrics_view.auto_resume_timer.setInterval(6000)

    rebuild_count = window.lyrics_view.content_rebuild_count
    label_ids = [id(label) for label in window.lyrics_view.labels]
    repaint_started = time.perf_counter()
    for position in range(19_100, 20_000, 20):
        window.update_position(position, lyrics, local_identity)
    metrics["position_update_avg_us"] = (
        (time.perf_counter() - repaint_started) * 1_000_000 / 45
    )
    assert window.lyrics_view.content_rebuild_count == rebuild_count
    assert [id(label) for label in window.lyrics_view.labels] == label_ids

    main.current_media_item = MediaItem.from_online(
        {
            "sourceId": "test-source",
            "sourceName": "测试来源",
            "id": "online-track",
            "title": "在线测试歌曲",
            "artist": "在线歌手",
            "album": "在线专辑",
        }
    )
    online_identity = main.current_track_identity()
    online_lyrics = [(0, "在线歌词 A"), (1000, "在线歌词 B")]
    window.update_track_timing(online_identity, 0)
    assert not window.lyrics_view.auto_resume_timer.isActive()
    assert window.lyrics_view.scroll_animation.state() == QAbstractAnimation.State.Stopped
    main.current_online_lyrics_state = "loading"
    window.set_lyrics([], online_identity)
    app.processEvents()
    assert "正在加载歌词" in {
        label.text()
        for label in window.lyrics_view.findChildren(QLabel, "lyricPlaceholderTitle")
    }
    main.current_online_lyrics_state = "error"
    window.set_lyrics([], online_identity)
    app.processEvents()
    assert "歌词加载失败" in {
        label.text()
        for label in window.lyrics_view.findChildren(QLabel, "lyricPlaceholderTitle")
    }
    window.update_song_info(
        "在线测试歌曲",
        "在线歌手 · 在线专辑 · 测试来源",
        "在线歌词已加载",
        online_identity,
    )
    window.set_lyrics(online_lyrics, online_identity)
    window.update_song_info("过期歌曲", "过期歌手", "过期状态", local_identity)
    window.set_lyrics([(0, "过期歌词")], local_identity)
    window.update_position(10_000, [(0, "过期歌词")], local_identity)
    assert window.song_title.full_text == "在线测试歌曲"
    assert window.lyrics_view.current_index == -1
    assert [label.text() for label in window.lyrics_view.labels] == [
        "在线歌词 A",
        "在线歌词 B",
    ]

    red = make_cover("#8d423d")
    blue = make_cover("#365f91")
    background_started = time.perf_counter()
    window.update_background_cover("local:background-a", red)
    assert wait_until(
        app,
        lambda: "background-a" in window.background_view.rendered_source_key,
    )
    metrics["background_prepare_ms"] = (
        time.perf_counter() - background_started
    ) * 1000
    cached_started = time.perf_counter()
    background_tasks = window.background_view.task_start_count
    window.update_background_cover("local:background-a", red)
    app.processEvents()
    metrics["cached_background_ms"] = (
        time.perf_counter() - cached_started
    ) * 1000
    assert window.background_view.task_start_count == background_tasks
    window.update_background_cover("local:background-b", blue)
    assert "background-a" in window.background_view.rendered_source_key
    window.update_background_cover("local:background-final", red)
    assert wait_until(
        app,
        lambda: "background-final" in window.background_view.rendered_source_key
        and not window.background_view.task_running,
    )
    main.expected_immersive_track_key = "local:background-final"
    cover_cache_key = window.cover_label.pixmap().cacheKey()
    window.update_background_cover("local:stale-background", blue)
    assert window.cover_label.pixmap().cacheKey() == cover_cache_key
    assert "background-final" in window.background_view.rendered_source_key
    main.expected_immersive_track_key = ""
    window.update_background_cover("local:no-cover", None)
    assert not window.background_view.fallback_active
    assert "background-final" in window.background_view.rendered_source_key
    assert "继续显示上一首背景" in window.background_view.status_text
    window.mark_background_cover_unavailable("local:no-cover")
    assert window.background_view.fallback_active
    assert window.cover_label.pixmap().isNull()
    window.update_background_cover("local:late-cover", make_cover("#634b82"))
    assert wait_until(app, lambda: window.background_view.task_running)
    window.mark_background_cover_unavailable("local:new-track-without-cover")
    assert wait_until(app, lambda: not window.background_view.task_running)
    assert window.background_view.fallback_active
    assert not window.background_view.rendered_source_key

    window.set_lyrics([], online_identity)
    assert not window.lyrics_view.labels
    assert window.lyrics_view.findChild(QLabel, "lyricPlaceholderTitle") is not None

    stable_ids: list[int] = []
    window.set_lyrics(lyrics, online_identity)
    stable_ids = [id(label) for label in window.lyrics_view.labels]
    window.resize(900, 720)
    app.processEvents()
    assert window._responsive_mode == "compact"
    assert window.body_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert window.cover_label.isVisible()
    assert [id(label) for label in window.lyrics_view.labels] == stable_ids
    window.resize(760, 700)
    app.processEvents()
    assert window._responsive_mode == "narrow"
    assert not window.cover_label.isVisible()
    assert [id(label) for label in window.lyrics_view.labels] == stable_ids

    for width, height, expected_mode in (
        (900, 720, "compact"),
        (1100, 720, "compact"),
        (1450, 850, "wide"),
        (1600, 900, "wide"),
        (1920, 1080, "wide"),
        (2560, 1440, "wide"),
        (2200, 900, "wide"),
        (900, 1400, "compact"),
        (720, 900, "narrow"),
    ):
        window.resize(width, height)
        app.processEvents()
        assert window._responsive_mode == expected_mode
        assert [id(label) for label in window.lyrics_view.labels] == stable_ids
        assert window.footer.geometry().right() <= window.background_panel.rect().right()
        assert window.lyrics_panel.geometry().bottom() <= window.footer.geometry().top()
        if expected_mode != "wide":
            assert (
                window.lyrics_view.reserved_bottom_space
                >= window.footer.sizeHint().height() + 12
            )

    window.resize(720, 900)
    app.processEvents()
    window.lyrics_view.scroll_to_index(len(window.lyrics_view.labels) - 1, animate=False)
    app.processEvents()
    last_label = window.lyrics_view.labels[-1]
    last_label_bottom = (
        last_label.y()
        + last_label.height()
        - window.lyrics_view.verticalScrollBar().value()
    )
    assert last_label_bottom < window.lyrics_view.viewport().height()
    body_geometry = window.body.geometry()
    lyrics_geometry = window.lyrics_panel.geometry()
    window.set_controls_visible(False, animate=False)
    app.processEvents()
    assert window.body.geometry() == body_geometry
    assert window.lyrics_panel.geometry() == lyrics_geometry
    window.set_controls_visible(True, animate=False)

    window.resize(1100, 720)
    app.processEvents()
    window.setGeometry(34, 46, 1030, 680)
    app.processEvents()
    original_geometry = window.geometry()
    assert original_geometry.size() == QSize(1030, 680)
    assert window.maximumWidth() > original_geometry.width()
    assert window.maximumHeight() > original_geometry.height()
    window.show_on_best_screen()
    app.processEvents()
    assert window.isFullScreen()
    assert window.fullscreen_btn.text() == "退出全屏"
    assert "进入全屏" not in [
        button.text() for button in window.control_header.findChildren(QPushButton)
    ]
    window.show_windowed()
    app.processEvents()
    assert not window.isFullScreen()
    assert window.geometry() == original_geometry
    assert window.fullscreen_btn.text() == "进入全屏"

    mini_view = LyricsView()
    mini_view.set_lyrics(lyrics[:4])
    mini_view.update_by_position(1500, lyrics[:4])
    assert mini_view.current_index == 1
    assert not mini_view.manual_browse_enabled
    assert mini_view.target_position_ratio == 0.5
    mini_view.deleteLater()

    long_view = LyricsView()
    long_lyrics = [(index * 500, f"长歌词性能测试第 {index + 1} 行") for index in range(500)]
    long_started = time.perf_counter()
    long_view.set_lyrics(long_lyrics)
    app.processEvents()
    metrics["long_lyrics_500_load_ms"] = (
        time.perf_counter() - long_started
    ) * 1000
    assert len(long_view.labels) == 500
    long_view.deleteLater()

    screenshot_path = str(os.environ.get("HUSHPLAYER_IMMERSIVE_SCREENSHOT") or "").strip()
    if screenshot_path:
        screenshot_width = int(
            os.environ.get("HUSHPLAYER_IMMERSIVE_SCREENSHOT_WIDTH", "1600")
        )
        screenshot_height = int(
            os.environ.get("HUSHPLAYER_IMMERSIVE_SCREENSHOT_HEIGHT", "900")
        )
        window.resize(screenshot_width, screenshot_height)
        window.set_lyrics(lyrics, online_identity)
        window.update_position(15_500, lyrics, online_identity)
        window.update_background_cover("local:screenshot", make_cover("#365f91"))
        assert wait_until(
            app,
            lambda: "screenshot" in window.background_view.rendered_source_key,
        )
        app.processEvents()
        target = Path(screenshot_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(target))
        window.setGeometry(original_geometry)
        app.processEvents()

    window.close()
    assert wait_until(app, lambda: not window.isVisible())
    assert window._external_connections == []
    assert not window.hide_ui_timer.isActive()
    assert not window.font_scale_timer.isActive()
    assert not window.responsive_layout_timer.isActive()
    assert not window.lyrics_view.auto_resume_timer.isActive()
    assert window.lyrics_view.scroll_animation.state() == QAbstractAnimation.State.Stopped
    assert window.header_opacity_animation.state() == QAbstractAnimation.State.Stopped
    assert window.footer_opacity_animation.state() == QAbstractAnimation.State.Stopped
    assert window.background_view._closed
    assert not window.background_view.task_running
    assert main.closed_count == 1
    saved_geometry = main.settings.get("immersive_window_geometry")
    assert saved_geometry == {
        "x": original_geometry.x(),
        "y": original_geometry.y(),
        "width": original_geometry.width(),
        "height": original_geometry.height(),
    }

    restored_main = StubMainWindow(root)
    restored_main.settings.update(main.settings)
    restored = ImmersiveLyricsWindow(restored_main)
    restored_main.immersive_lyrics_window = restored
    restored.show_windowed()
    app.processEvents()
    assert restored.geometry() == original_geometry
    QTest.keyClick(restored, Qt.Key.Key_F11)
    app.processEvents()
    assert restored.isFullScreen()
    QTest.keyClick(restored, Qt.Key.Key_Escape)
    app.processEvents()
    assert restored.isVisible()
    assert not restored.isFullScreen()
    QTest.keyClick(restored, Qt.Key.Key_Escape)
    assert wait_until(app, lambda: not restored.isVisible())

    invalid_main = StubMainWindow(root)
    invalid_main.settings["immersive_window_geometry"] = {
        "x": "bad",
        "y": 0,
        "width": 100,
        "height": 100,
    }
    invalid_window = ImmersiveLyricsWindow(invalid_main)
    assert invalid_window._windowed_geometry is None
    invalid_window.close()

    disconnected_main = StubMainWindow(root)
    disconnected_main.settings["immersive_window_geometry"] = {
        "x": 500_000,
        "y": 500_000,
        "width": 960,
        "height": 640,
    }
    disconnected_window = ImmersiveLyricsWindow(disconnected_main)
    restored_rect = disconnected_window._windowed_geometry
    assert restored_rect is not None
    assert any(
        screen.availableGeometry().contains(restored_rect.center())
        for screen in QApplication.screens()
    )
    disconnected_window.close()
    return metrics


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="hushplayer_immersive_ui_") as temp_dir:
        metrics = run_test(app, Path(temp_dir))
    print(
        "immersive lyrics UI smoke: OK",
        f"scale={os.environ.get('QT_SCALE_FACTOR', '1')}",
        " ".join(f"{key}={value:.2f}" for key, value in metrics.items()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
