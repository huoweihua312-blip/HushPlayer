"""Theme switch animation + first-run close prompt defaults."""

from __future__ import annotations

import pytest

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from hushplayer.core.settings import Settings
from hushplayer.ui.widgets.transition import ThemeReveal


def test_close_action_asks_by_default(tmp_path, qapp):
    settings = Settings(tmp_path / "settings.json")
    assert settings.get("general.close_action") == "ask"
    assert settings.get("appearance.theme_animation", True) is True


def test_theme_reveal_progress_and_radius(qapp):
    host = QWidget()
    host.resize(400, 300)
    old = QPixmap(400, 300)
    new = QPixmap(400, 300)
    reveal = ThemeReveal(host, old, new, QPointF(380, 20), to_dark=False)
    assert reveal.revealProgress == 0.0
    reveal.set_reveal_progress(0.5)
    assert abs(reveal.revealProgress - 0.5) < 1e-6
    reveal.set_reveal_progress(2.0)
    assert reveal.revealProgress == 1.0
    reveal.set_reveal_progress(-1.0)
    assert reveal.revealProgress == 0.0
    # the wipe must be able to cover the far corner whatever the origin is
    assert reveal._radius_max() >= (380 ** 2 + 280 ** 2) ** 0.5 - 1


def test_reveal_finish_retires_overlay(qapp):
    host = QWidget()
    host.resize(300, 200)
    frame = QPixmap(300, 200)
    reveal = ThemeReveal(host, frame, frame, QPointF(280, 20), to_dark=True)
    reveal.freeze()
    assert reveal.revealProgress == 0.0
    reveal.finish()
    assert reveal.revealProgress == 1.0
    assert reveal.isVisible() is False


class _StubOverlay:
    def __init__(self) -> None:
        self.finished = 0

    def finish(self) -> None:
        self.finished += 1


def test_app_retires_previous_reveal_before_next(qapp):
    from hushplayer.app import HushApp

    app = HushApp(qapp)
    stub = _StubOverlay()
    app._theme_reveal = stub
    app._end_theme_transition()
    assert stub.finished == 1
    assert app._theme_reveal is None
    # a second call with nothing pending must stay a no-op
    app._end_theme_transition()
    assert stub.finished == 1


def test_animation_mode_default_and_legacy_migration(tmp_path, qapp):
    settings = Settings(tmp_path / "settings.json")
    assert settings.get("appearance.theme_animation_mode") == "reveal"

    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"appearance": {"theme_animation": false}}', encoding="utf-8")
    migrated = Settings(legacy)
    migrated.load()
    assert migrated.get("appearance.theme_animation_mode") == "off"
    assert "theme_animation" not in migrated.as_dict().get("appearance", {})

    legacy_on = tmp_path / "legacy_on.json"
    legacy_on.write_text('{"appearance": {"theme_animation": true}}', encoding="utf-8")
    legacy_on_settings = Settings(legacy_on)
    legacy_on_settings.load()
    assert legacy_on_settings.get("appearance.theme_animation_mode") == "reveal"


def test_sun_moon_reveal_pops_icon_then_fades(qapp):
    from hushplayer.ui.widgets.transition import SunMoonReveal

    host = QWidget()
    host.resize(600, 400)
    frame = QPixmap(600, 400)

    dawn = SunMoonReveal(host, frame, frame, QPointF(0, 0), to_dark=False)
    dawn.set_reveal_progress(0.0)
    assert dawn.icon_alpha() == 0.0
    assert dawn.new_frame_alpha() == 0.0
    dawn.set_reveal_progress(0.2)
    assert 0.0 < dawn.icon_alpha() <= 1.0
    assert 0.0 < dawn.icon_scale() <= 1.0
    dawn.set_reveal_progress(1.0)
    assert dawn.new_frame_alpha() == 1.0
    assert dawn.icon_alpha() == 0.0
    dawn.finish()
    assert dawn.isVisible() is False

    # The veil never blanks the window and always clears by the end.
    dusk = SunMoonReveal(host, frame, frame, QPointF(0, 0), to_dark=True)
    veils = []
    for step in range(21):
        dusk.set_reveal_progress(step / 20)
        veils.append(dusk.veil_alpha())
    assert max(veils) < 1.0, "veil must keep the interface visible"
    assert max(veils) > 0.5, "veil should still read as a black/white wash"
    assert veils[-1] == 0.0
    # Once the swap happens the new UI is fully drawn; the hold is visible.
    dusk.set_reveal_progress(0.55)
    assert dusk.new_frame_alpha() == 1.0
    assert dusk.icon_alpha() == 1.0


def test_sun_moon_timeline_honours_settings(qapp):
    from hushplayer.ui.widgets.transition import SunMoonReveal

    host = QWidget()
    host.resize(600, 400)
    frame = QPixmap(600, 400)

    slow = SunMoonReveal(
        host, frame, frame, QPointF(0, 0), to_dark=False, pop_ms=800, hold_ms=400, icon_scale=1.5
    )
    fast = SunMoonReveal(
        host, frame, frame, QPointF(0, 0), to_dark=False, pop_ms=200, hold_ms=100, icon_scale=0.8
    )
    assert slow.total_ms() > fast.total_ms()
    assert slow._icon_scale == 1.5 and fast._icon_scale == 0.8

    # The icon only holds full size once its own pop window has elapsed.
    slow.set_reveal_progress(0.2)  # 0.2 * 1770ms = 354ms < 800ms pop
    assert slow.stage() == "pop"
    assert slow.icon_scale() < 1.0
    slow.set_reveal_progress(0.5)  # past the pop, well inside the wash/hold
    assert slow.stage() in {"wash", "hold"}
    assert slow.icon_scale() == 1.0


def test_overlays_expose_animation_ms(qapp):
    """apply_theme divides by the animation length for the cooldown window; both
    overlays must answer it (a missing attribute crashed the theme toggle)."""
    from hushplayer.ui.widgets.transition import SunMoonReveal, ThemeReveal

    host = QWidget()
    host.resize(400, 300)
    frame = QPixmap(400, 300)
    reveal = ThemeReveal(host, frame, frame, QPointF(10, 10), to_dark=True)
    assert reveal.animation_ms() > 0

    sun = SunMoonReveal(host, frame, frame, QPointF(0, 0), to_dark=False, pop_ms=500, hold_ms=0)
    assert sun.animation_ms() == pytest.approx(sun.total_ms(), rel=0.02)
    assert sun.animation_ms() >= 500
