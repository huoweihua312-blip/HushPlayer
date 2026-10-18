"""Brand asset resolution (BUG-07 / R2-04).

The user supplied the official artwork in ``assets/brand``; these tests lock in
that it is picked up everywhere, and that the fallback chain still renders
something sane if the folder is ever empty.
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


def test_official_logo_is_used():
    assert brand.has_official_logo() is True
    assert brand.brand_dir().name == "brand"
    logo = brand.logo_path("dark")
    assert logo is not None
    assert logo.parent == brand.brand_dir()
    icon = brand.icon_path()
    assert icon is not None
    assert icon.suffix.lower() == ".ico"


def test_falls_back_when_brand_folder_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(brand, "brand_dir", lambda: tmp_path)
    assert brand.has_official_logo() is False
    assert brand.logo_path("dark") is not None  # bundled placeholder still renders
