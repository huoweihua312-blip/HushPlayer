"""Frameless window: rounded mask, edge handles, restore geometry."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from hushplayer.ui.widgets.frameless import FramelessWindow


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_round_mask_is_applied_and_edges_are_handles(app):
    window = FramelessWindow()
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    mask = window.mask()
    assert not mask.isEmpty()
    # The extreme corner is clipped away, a few pixels inside is not: that is
    # what makes Windows 10 show rounded corners too.
    assert not mask.contains(QPoint(0, 0))
    assert mask.contains(QPoint(12, 12))
    assert len(window._edge_handles) == 8
    assert all(handle.isVisible() for handle in window._edge_handles)
    window.close()


def test_maximized_window_is_square_and_has_no_handles(app):
    window = FramelessWindow()
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    window._maximized = True
    window._sync_maximized_ui()
    assert window.mask().isEmpty()
    assert not any(handle.isVisible() for handle in window._edge_handles)
    window.close()


def test_near_full_window_is_a_valid_restore_target(app):
    window = FramelessWindow()
    window.resize(1000, 700)
    assert window._usable_normal_geometry(QRect(0, 0, 1000, 700))
    assert not window._usable_normal_geometry(QRect(0, 0, 200, 120))
    window.close()
