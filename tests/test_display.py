"""UI scale resolution (BUG-05 regression guard).

2K screens used to look tiny because the whole UI only ever rendered at 10pt on
a 2560x1440 panel. The scale is resolved *before* QApplication exists, so these
tests read the settings JSON directly and stub the physical screen size.
"""

from __future__ import annotations

import json

import pytest

from hushplayer.core import display


@pytest.fixture()
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(display.paths, "settings_file", lambda: path)
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    monkeypatch.delenv("HUSHPLAYER_UI_SCALE", raising=False)

    def write(value: str) -> None:
        path.write_text(json.dumps({"appearance": {"ui_scale": value}}), encoding="utf-8")

    return write


def test_recommended_scale_thresholds():
    assert display.recommended_scale(1920) == "1.0"
    assert display.recommended_scale(2560) == "1.0"
    assert display.recommended_scale(3440) == "1.25"
    assert display.recommended_scale(3840) == "1.5"


def test_auto_follows_physical_screen(settings_file, monkeypatch):
    settings_file("auto")
    monkeypatch.setattr(display, "physical_screen_size", lambda: (2560, 1440))
    assert display.resolve_scale() == pytest.approx(1.0)

    monkeypatch.setattr(display, "physical_screen_size", lambda: (3840, 2160))
    assert display.resolve_scale() == pytest.approx(1.5)

    monkeypatch.setattr(display, "physical_screen_size", lambda: (1920, 1080))
    assert display.resolve_scale() == pytest.approx(1.0)


def test_explicit_preference_wins(settings_file, monkeypatch):
    settings_file("1.5")
    monkeypatch.setattr(display, "physical_screen_size", lambda: (1920, 1080))
    assert display.resolve_scale() == pytest.approx(1.5)


def test_invalid_preference_falls_back_to_auto(settings_file, monkeypatch):
    settings_file("banana")
    monkeypatch.setattr(display, "physical_screen_size", lambda: (2560, 1440))
    assert display.resolve_scale() == pytest.approx(1.0)


def test_apply_scale_environment_sets_qt_factor(settings_file, monkeypatch):
    import os

    settings_file("1.15")
    value = display.apply_scale_environment()
    assert value == pytest.approx(1.15)
    assert os.environ["QT_SCALE_FACTOR"] == "1.15"
    assert display.current_scale() == pytest.approx(1.15)

    settings_file("1.0")
    display.apply_scale_environment()
    assert "QT_SCALE_FACTOR" not in os.environ
    assert display.current_scale() == pytest.approx(1.0)


def test_scale_text_mentions_percentage(settings_file):
    # scale_text() reports the scale actually applied to this process, so the
    # environment has to be (re)applied first -- exactly like start-up does.
    settings_file("1.25")
    display.apply_scale_environment()
    assert "125" in display.scale_text()
