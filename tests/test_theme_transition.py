"""Theme switch animation + first-run close prompt defaults."""

from __future__ import annotations

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
