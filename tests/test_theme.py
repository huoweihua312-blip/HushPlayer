"""R3-01 回归：字体必须落在整数像素并保留足够可读性。"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFont

from hushplayer.core.theme import theme


def test_font_pixel_sizes_are_integers(qapp) -> None:
    font = theme().font(9.4, 500)
    assert isinstance(font, QFont)
    assert font.pixelSize() > 0
    assert font.hintingPreference() == QFont.HintingPreference.PreferFullHinting
    assert font.kerning() is True


def test_small_text_gets_a_legibility_floor(qapp) -> None:
    theme().apply(font_scale=1.25)
    smallest = theme().font(7.4, 400)
    body = theme().font(10.5, 400)
    theme().apply(font_scale=1.0)
    assert smallest.pixelSize() >= 11
    assert body.pixelSize() > smallest.pixelSize()


def test_font_scale_is_monotonic(qapp) -> None:
    theme().apply(font_scale=0.8)
    small = theme().font(10.5).pixelSize()
    theme().apply(font_scale=1.8)
    large = theme().font(10.5).pixelSize()
    theme().apply(font_scale=1.0)
    assert large > small


def test_ui_scale_enlarges_type_without_changing_dpr(qapp) -> None:
    theme().apply(ui_scale=1.0, font_scale=1.0)
    base = theme().font(10.5).pixelSize()
    theme().apply(ui_scale=1.18)
    scaled = theme().font(10.5).pixelSize()
    theme().apply(ui_scale=1.0)
    assert scaled > base
    # QSS text (pt) and QPainter text (px) must resolve to the same pixel size,
    # otherwise the sidebar and the search field render at different weights.
    for size in (8.0, 9.0, 10.5, 13.0):
        assert theme().pt(size) * 96.0 / 72.0 == pytest.approx(theme().px(size), abs=0.51)
    assert theme().px(9) > 9
