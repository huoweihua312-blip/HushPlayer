"""界面缩放偏好与「重启程序」的契约。"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from hushplayer.app import HushApp, _wait_for_pid_exit
from hushplayer.core import display


def test_scale_preference_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSHPLAYER_DATA_DIR", str(tmp_path))
    from hushplayer.core.paths import ensure_dirs

    ensure_dirs()
    from hushplayer.core.settings import Settings

    settings = Settings()
    settings.set("appearance.ui_scale", "1.5")
    settings.flush()

    assert display.read_ui_scale_preference() == "1.5"
    assert display.scale_preference() == "1.5"
    assert display.resolve_scale() == pytest.approx(1.5)
    assert display.apply_scale_environment() == pytest.approx(1.5)
    # Crispness contract: scaling must not introduce a fractional device pixel ratio.
    assert os.environ.get("QT_SCALE_FACTOR") is None


def test_explicit_scale_suppresses_automatic_type_scale(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSHPLAYER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HUSHPLAYER_TYPE_SCALE", raising=False)
    from hushplayer.core.paths import ensure_dirs

    ensure_dirs()
    from hushplayer.core.settings import Settings

    settings = Settings()
    settings.set("appearance.ui_scale", "1.25")
    settings.flush()

    # The explicit choice becomes the type scale (DPR stays 1.0).
    assert HushApp._ui_type_scale(object()) == pytest.approx(1.25)


def test_env_type_scale_still_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("HUSHPLAYER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HUSHPLAYER_TYPE_SCALE", "1.3")
    assert HushApp._ui_type_scale(object()) == pytest.approx(1.3)


def test_wait_for_pid_exit_returns_quickly_for_dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=20)
    started = time.monotonic()
    waited = _wait_for_pid_exit(proc.pid, timeout_s=4.0)
    assert waited < 1.5
    assert time.monotonic() - started < 2.5


def test_scale_combo_values_are_keys(qapp):
    from hushplayer.core.display import SCALE_LABELS
    from hushplayer.ui.widgets.settings_widgets import SettingCombo

    items = [(label, key) for key, label in SCALE_LABELS.items()]
    combo = SettingCombo(items)
    combo.set_value("1.5")
    assert combo.value() == "1.5"
    assert combo.currentText() == SCALE_LABELS["1.5"]


def test_scale_change_updates_hint_without_nameerror(qapp):
    """Regression: the hint handler used a function-local import and crashed."""
    from hushplayer.ui.pages.settings import SettingsPage

    page = SettingsPage()
    page.resize(900, 700)
    page._show_section(1)
    page._on_scale_changed("1.5")
    hint = page._scale_hint.text()
    assert "150%" in hint
    assert "重启后生效" in hint
