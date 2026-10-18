"""生成 HushPlayer 品牌图标（assets/hushplayer.ico 与 PNG）。

品牌元素：炭黑圆角方块 + 莓果红波形（呼应主界面 LogoMark）。
用法：python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ACCENT = (201, 87, 112, 255)
ACCENT_DARK = (152, 56, 78, 255)
INK = (18, 18, 22, 255)
INK_SOFT = (32, 30, 36, 255)
SIZE = 1024


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def build() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = int(SIZE * 0.055)
    _rounded(draw, (margin, margin, SIZE - margin, SIZE - margin), int(SIZE * 0.235), INK)

    # 内层柔和渐变：用多条横线模拟自上而下的微光
    inner = (margin + 18, margin + 18, SIZE - margin - 18, SIZE - margin - 18)
    for index in range(96):
        ratio = index / 95
        y0 = inner[1] + (inner[3] - inner[1]) * ratio
        y1 = inner[1] + (inner[3] - inner[1]) * (ratio + 1 / 96) + 1
        alpha = int(26 * (1 - ratio) + 6)
        draw.rectangle((inner[0], y0, inner[2], y1), fill=(255, 255, 255, alpha))

    # 波形：五根圆头竖条，居中高度递变（低调的声波）
    bars = (0.30, 0.52, 0.78, 0.52, 0.30)
    width = int(SIZE * 0.072)
    gap = int(SIZE * 0.052)
    total = width * len(bars) + gap * (len(bars) - 1)
    left = (SIZE - total) / 2
    for index, scale in enumerate(bars):
        height = SIZE * 0.46 * scale
        x0 = left + index * (width + gap)
        y0 = (SIZE - height) / 2
        color = ACCENT if index % 2 == 0 else ACCENT_DARK
        if index == 2:
            color = ACCENT
        _rounded(draw, (x0, y0, x0 + width, y0 + height), width // 2, color)

    # 中心高光点，增加一点精致感
    dot_r = int(SIZE * 0.028)
    cx, cy = SIZE / 2, SIZE / 2
    draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=(255, 255, 255, 210))
    return image


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    image = build()
    image.save(ASSETS / "hushplayer.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(ASSETS / "hushplayer.ico", sizes=sizes)
    print("saved", ASSETS / "hushplayer.png")
    print("saved", ASSETS / "hushplayer.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
