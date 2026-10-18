"""Interpolated playback clock (BUG-06 regression guard)."""

from __future__ import annotations

import time

from hushplayer.audio.clock import TICK_INTERVAL_MS, PlaybackClock


def _pump(qapp, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.004)
    qapp.processEvents()


def test_clock_ticks_only_while_playing(qapp):
    clock = PlaybackClock()
    ticks: list[int] = []
    clock.tick.connect(ticks.append)

    clock.set_position(1000)
    clock.set_playing(False)
    _pump(qapp, 0.1)
    assert ticks == [1000]  # a paused seek still reports its position once

    ticks.clear()
    clock.set_playing(True)
    _pump(qapp, 0.16)
    assert len(ticks) >= 3, ticks
    assert ticks == sorted(ticks)
    assert TICK_INTERVAL_MS <= 20
    clock.shutdown()


def test_position_interpolates_between_authoritative_updates(qapp):
    clock = PlaybackClock()
    clock.set_position(0)
    clock.set_playing(True)
    _pump(qapp, 0.12)
    interpolated = clock.position()
    assert 60 <= interpolated < 400, interpolated

    # An authoritative update snaps the estimate back to the engine value.
    clock.set_position(5000)
    assert clock.position() == 5000
    clock.shutdown()


def test_pause_freezes_position(qapp):
    clock = PlaybackClock()
    clock.set_position(2000)
    clock.set_playing(True)
    _pump(qapp, 0.08)
    clock.set_playing(False)
    frozen = clock.position()
    _pump(qapp, 0.1)
    assert clock.position() == frozen
    assert clock.playing is False
    clock.shutdown()


def test_position_is_clamped_to_duration(qapp):
    clock = PlaybackClock()
    clock.set_duration(3000)
    clock.set_position(2950)
    clock.set_playing(True)
    _pump(qapp, 0.12)
    assert clock.position() <= 3000
    clock.shutdown()


def test_reset_clears_state(qapp):
    clock = PlaybackClock()
    clock.set_position(4000)
    clock.set_duration(9000)
    clock.set_playing(True)
    clock.reset()
    assert clock.position() == 0
    assert clock.duration == 0
    assert clock.playing is False
    clock.shutdown()
