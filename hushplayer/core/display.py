"""High-DPI / 2K 显示器上的界面缩放（BUG-05）。

问题背景：HushPlayer 运行在 2560×1440 显示器、Windows 缩放 100% 时，所有尺寸
都按 CSS 逻辑像素绘制，于是同一个窗口在 2K 屏上只占屏幕的一小块，文字与点击
区域都显得偏小。

这里不逐个控件放大，而是完整地放大 Qt 的逻辑像素：
在创建 QApplication 之前设置 ``QT_SCALE_FACTOR``，之后所有自绘尺寸、字号、
行高、图标都会按同一比例放大，布局关系保持不变（不会出现"只放大字体导致重叠"）。

由于缩放因子必须在 QApplication 构造前生效，切换后需要重启程序。
"""

from __future__ import annotations

import json
import os

from . import paths
from .logging_setup import get_logger

log = get_logger(__name__)

SCALE_AUTO = "auto"
SCALE_CHOICES = (SCALE_AUTO, "1.0", "1.15", "1.25", "1.5")
SCALE_LABELS = {
    SCALE_AUTO: "自动（按屏幕分辨率）",
    "1.0": "100%",
    "1.15": "115%",
    "1.25": "125%（2K 推荐）",
    "1.5": "150%（4K 推荐）",
}
_APPLIED_ENV = "HUSHPLAYER_UI_SCALE"


def physical_screen_size() -> tuple[int, int]:
    """Physical pixels of the primary display (DPI-aware values on Windows)."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:  # pragma: no cover - 非 Windows 或受限环境
        return 0, 0


def recommended_type_scale(physical_width: int, physical_height: int = 0, dpr: float = 1.0) -> float:
    """Type enlargement so the UI looks the same size on different panels.

    What matters is the *apparent* size: the physical pixel height of a glyph
    relative to the screen. Windows already enlarges everything through its
    scale factor (``dpr``), so the extra type scale has to compensate for the
    remaining difference in physical height:

        apparent ≈ base_px × type_scale × dpr  ∝  physical_height

    A 2560×1440 panel at 100% (the configuration HushPlayer was tuned on)
    therefore maps to 1.5×, while the same panel at 150% maps to 1.0× and
    1920×1080 at 100% maps to ~1.13×. Without the ``height``/``dpr``
    arguments the old width-only thresholds are kept for callers that have
    no screen information.
    """
    if physical_height > 0 and dpr > 0:
        ratio = (physical_height / 1440.0) / dpr
        scale = 1.5 * ratio
        scale = max(1.0, min(1.6, scale))
        return round(scale * 20) / 20  # 0.05 steps keep metrics stable
    if physical_width >= 3200:
        return 1.0  # 4K normally runs at DPR 1.5
    if physical_width >= 2400:
        return 1.5
    if physical_width >= 2000:
        return 1.2
    return 1.0


def recommended_scale(physical_width: int) -> str:
    """Pick a comfortable UI scale for the given physical width.

    Everything up to 2560x1440 stays at 100%: fractional scale factors make
    text noticeably softer (glyphs land on half pixels), and users who want a
    larger UI can raise "appearance.ui_scale" explicitly. 4K gets 150%.
    The values are product decisions, not a generic DPI formula: the goal is
    "comfortable to read at normal viewing distance", which we validated on a
    2560×1440 panel.
    """
    if physical_width >= 3600:
        return "1.5"
    if physical_width >= 3200:
        return "1.25"
    return "1.0"


def read_ui_scale_preference() -> str:
    """Read ``appearance.ui_scale`` without constructing QApplication."""
    try:
        path = paths.settings_file()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            value = str((data.get("appearance") or {}).get("ui_scale") or SCALE_AUTO)
            if value in SCALE_CHOICES:
                return value
    except Exception:
        log.debug("cannot read ui scale preference", exc_info=True)
    return SCALE_AUTO


def scale_preference() -> str:
    """The user's explicit choice, or ``auto`` when the app should decide."""
    return read_ui_scale_preference()


def resolve_scale(preference: str | None = None) -> float:
    preference = preference or read_ui_scale_preference()
    if preference == SCALE_AUTO:
        width, _ = physical_screen_size()
        preference = recommended_scale(width)
    try:
        scale = float(preference)
    except (TypeError, ValueError):
        scale = 1.0
    return max(0.8, min(2.0, scale))


def apply_scale_environment(preference: str | None = None) -> float:
    """Set ``QT_SCALE_FACTOR``; must run before QApplication is created."""
    scale = resolve_scale(preference)
    if abs(scale - 1.0) > 0.001:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"
    else:
        os.environ.pop("QT_SCALE_FACTOR", None)
    os.environ[_APPLIED_ENV] = f"{scale:.2f}"
    return scale


def current_scale() -> float:
    value = os.environ.get(_APPLIED_ENV) or os.environ.get("QT_SCALE_FACTOR") or "1.0"
    try:
        return float(value)
    except ValueError:
        return 1.0


def scale_text() -> str:
    scale = current_scale()
    if abs(scale - 1.0) < 0.001:
        return "100%"
    return f"{round(scale * 100)}%"


__all__ = [
    "SCALE_AUTO",
    "SCALE_CHOICES",
    "SCALE_LABELS",
    "apply_scale_environment",
    "current_scale",
    "physical_screen_size",
    "read_ui_scale_preference",
    "recommended_scale",
    "scale_preference",
    "resolve_scale",
    "scale_text",
]
