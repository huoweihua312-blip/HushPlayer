"""播放链路：真实音频引擎、控制器队列行为、会话恢复与音量/进度。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine

pytestmark = pytest.mark.integration


def wait_until(predicate, timeout: float = 8.0, interval: float = 0.02) -> bool:
    """等待条件成立，同时驱动 Qt 事件循环（否则 QMediaPlayer 信号永远送不到）。"""
    from PySide6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture()
def wav_path(loaded_library) -> str:
    track = loaded_library.search_local("Static Bloom")[0]
    assert Path(track.path).exists()
    return track.path


def test_engine_plays_and_reports_position(qapp, wav_path) -> None:
    engine = PlaybackEngine()
    if not engine.available():
        pytest.skip("当前环境没有可用的音频输出设备")
    states: list[str] = []
    ended: list[bool] = []
    engine.state_changed.connect(states.append)
    engine.end_of_media.connect(lambda: ended.append(True))
    engine.set_volume(0.1)
    engine.load(wav_path)
    assert wait_until(lambda: "playing" in states), states
    assert wait_until(lambda: engine.position() > 0, timeout=5.0)
    assert engine.duration() >= 6000

    engine.seek(3000)
    assert wait_until(lambda: engine.position() >= 2900)
    engine.pause()
    paused_at = engine.position()
    wait_until(lambda: False, timeout=0.4)
    assert abs(engine.position() - paused_at) < 400, "暂停后位置不应继续前进"
    engine.play()
    assert wait_until(lambda: engine.position() > paused_at)

    engine.set_volume(0.0)
    assert float(engine.volume) == pytest.approx(0.0, abs=1e-6)
    engine.shutdown()


def test_engine_end_of_media(qapp) -> None:
    engine = PlaybackEngine()
    if not engine.available():
        pytest.skip("当前环境没有可用的音频输出设备")
    from hushplayer.core import paths

    fixture = Path("tests/fixtures/audio/夜航信号/03 - Static Bloom.wav")
    assert fixture.exists(), fixture
    ended: list[bool] = []
    engine.end_of_media.connect(lambda: ended.append(True))
    engine.load(str(fixture), autoplay=True)
    engine.seek(6600)
    assert wait_until(lambda: ended, timeout=10.0), "播放到结尾应发出 end_of_media"
    engine.shutdown()


def test_controller_queue_and_controls(loaded_library, qapp) -> None:
    tracks = loaded_library.tracks_page(__import__("hushplayer.services.library", fromlist=["LibraryQuery"]).LibraryQuery(sort="title", limit=100))
    assert len(tracks) >= 3
    controller = PlayerController()
    controller.set_volume(0.2)
    controller.play_tracks(tracks[:3], 0, context="测试")
    assert controller.current is not None
    assert controller.current.id == tracks[0].id
    assert controller.queue.count == 3

    controller.next()
    assert controller.current.id == tracks[1].id
    controller.previous()
    assert controller.current.id == tracks[0].id

    controller.toggle_shuffle()
    assert controller.shuffle is True
    controller.cycle_repeat()
    assert controller.repeat in {"all", "one"}
    controller.set_muted(True)
    assert controller.muted is True
    controller.shutdown()


def test_controller_reports_missing_file(loaded_library, qapp, tmp_path) -> None:
    track = loaded_library.search_local("无题")[0]
    Path(track.path).unlink()
    controller = PlayerController()
    messages: list[str] = []
    controller.error_message.connect(messages.append)
    controller.play_track(track)
    assert wait_until(lambda: messages), "文件已被删除时应给出错误提示"
    assert "不存在" in messages[0] or "文件" in messages[0]
    controller.shutdown()


def test_session_keeper_roundtrip(loaded_library, qapp, data_dir) -> None:
    from hushplayer.services.state import PlaybackKeeper, queue_file

    tracks = loaded_library.tracks_page(__import__("hushplayer.services.library", fromlist=["LibraryQuery"]).LibraryQuery(sort="title", limit=100))
    controller = PlayerController()
    controller.play_tracks(tracks[:2], 0, context="专辑 · 测试")
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    keeper.save_now()
    path = Path(queue_file())
    assert path.exists()

    controller.clear_queue()
    assert controller.queue.count == 0
    position = keeper.restore()
    assert controller.queue.count == 2
    assert controller.queue.context == "专辑 · 测试"
    assert isinstance(position, int)
    keeper.flush()
    controller.shutdown()
