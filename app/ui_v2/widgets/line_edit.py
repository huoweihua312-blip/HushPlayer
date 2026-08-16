"""Small input-field helpers shared by the V2 UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit


def apply_optical_vertical_center(line_edit: QLineEdit) -> QLineEdit:
    """Keep native text editing while correcting the font's visual baseline.

    Qt's native line-edit metrics leave the Chinese placeholder/text a little
    low inside the compact V2 controls.  A small asymmetric text margin moves
    the glyphs up without changing the widget geometry, cursor behavior, IME,
    selection, or horizontal padding supplied by the stylesheet.
    """

    line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    line_edit.setTextMargins(0, -2, 0, 2)
    return line_edit
