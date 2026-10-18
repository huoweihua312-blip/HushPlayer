"""Brand asset resolution (BUG-07).

The official logo is still user-supplied artwork, so the only thing to lock in
is the fallback chain: every surface must render something sane, and dropping a
file into ``assets/brand`` must be enough to replace it everywhere.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from hushplayer.core import brand


def test_placeholder_assets_exist():
    assert brand.logo_path("dark") is not None
    assert brand.logo_path("light") is not None
    assert brand.icon_path() is not None


def test_app_icon_has_multiple_sizes(qapp):
    icon = brand.app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert (16, 16) in sizes
    assert (256, 256) in sizes


def test_rounded_logo_pixmap_matches_requested_size(qapp):
    pixmap = brand.rounded_logo_pixmap(56, "dark")
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.devicePixelRatio() == 2.0
    assert pixmap.width() == 112


def test_official_logo_flag_tracks_files():
    assert brand.has_official_logo() is False  # no assets/brand/logo*.png in the repo
    assert brand.brand_dir().name == "brand"
