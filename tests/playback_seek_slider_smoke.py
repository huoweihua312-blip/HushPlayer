from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


activate_isolated_app_storage("hushplayer-click-seek-")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle

from app.ui.clickable_slider import ClickableSlider
from app.ui.main_window import MainWindow


def _geometry(slider: ClickableSlider):
    option = slider._style_option()
    style = slider.style()
    groove = style.subControlRect(
        QStyle.ComplexControl.CC_Slider,
        option,
        QStyle.SubControl.SC_SliderGroove,
        slider,
    )
    handle = style.subControlRect(
        QStyle.ComplexControl.CC_Slider,
        option,
        QStyle.SubControl.SC_SliderHandle,
        slider,
    )
    return groove, handle


def _click(slider: ClickableSlider, point: QPoint, button=Qt.MouseButton.LeftButton) -> None:
    QTest.mouseClick(slider, button, pos=point)
    QApplication.processEvents()


def _exercise_slider(app: QApplication, width: int) -> None:
    slider = ClickableSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.resize(width, 32)
    slider.show()
    app.processEvents()
    try:
        requested: list[int] = []
        slider.seekRequested.connect(requested.append)
        groove, _handle = _geometry(slider)
        y = groove.center().y()

        slider.setValue(100)
        _click(slider, QPoint(groove.left(), y))
        assert requested == [0]
        assert slider.value() == 0

        slider.setValue(0)
        quarter = QPoint(groove.left() + round(groove.width() * 0.25), y)
        _click(slider, quarter)
        assert len(requested) == 2
        assert 20 <= requested[-1] <= 30

        slider.setValue(0)
        midpoint = QPoint(groove.center().x(), y)
        _click(slider, midpoint)
        assert len(requested) == 3
        assert 45 <= requested[-1] <= 55
        assert slider.value() == requested[-1]

        slider.setValue(0)
        _click(slider, QPoint(groove.right(), y))
        assert requested[-1] == 100
        assert len(requested) == 4

        slider.setValue(50)
        _groove, handle = _geometry(slider)
        _click(slider, handle.center())
        assert len(requested) == 4

        _click(slider, midpoint, Qt.MouseButton.RightButton)
        _click(slider, midpoint, Qt.MouseButton.MiddleButton)
        assert len(requested) == 4
        assert slider.devicePixelRatioF() >= 1.0
    finally:
        slider.close()
        slider.deleteLater()
        app.processEvents()


def _exercise_window_seek_guards(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        window.current_duration = 100_000
        window.progress_slider.setRange(0, 100)
        assert window._can_seek_current_media() is False
        assert window._progress_value_to_position(-50) == 0
        assert window._progress_value_to_position(25) == 25_000
        assert window._progress_value_to_position(50) == 50_000
        assert window._progress_value_to_position(150) == 100_000

        state_before = {
            "queue": copy.deepcopy(window.play_queue),
            "volume": window.current_volume,
            "mode": window.play_mode,
            "liked": copy.deepcopy(window.playlists.get("liked", {})),
            "playback_state": window.media_player.playbackState(),
        }
        requested: list[int] = []
        original_submit = window._submit_progress_seek
        window._submit_progress_seek = lambda value: requested.append(value) or True
        try:
            window.on_progress_slider_seek_requested(50)
            assert requested == [50]
            window.is_seeking = True
            window.on_progress_slider_seek_requested(75)
            assert requested == [50]
        finally:
            window.is_seeking = False
            window._submit_progress_seek = original_submit

        window.current_duration = 0
        window.progress_slider.setValue(60)
        assert window._submit_progress_seek(60) is False
        assert window.progress_slider.value() == window.progress_slider.minimum()
        assert {
            "queue": window.play_queue,
            "volume": window.current_volume,
            "mode": window.play_mode,
            "liked": window.playlists.get("liked", {}),
            "playback_state": window.media_player.playbackState(),
        } == state_before
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def main() -> int:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        for width in (160, 320, 640):
            _exercise_slider(app, width)
        _exercise_window_seek_guards(app)
        print("playback seek slider smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
