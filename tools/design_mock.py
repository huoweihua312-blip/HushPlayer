"""Design mock renderer (throwaway): draws the four proposed surfaces.

Not wired into the app - the output PNGs in docs/design/ are review material.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from hushplayer.core import icons
from hushplayer.core.fonts import load_bundled_fonts
from hushplayer.core.theme import Theme

LIGHT = dict(
    window="#F4F4F6", surface="#FFFFFF", elevated="#FFFFFF", text="#1C1B1D",
    muted="#8A8A92", border="#E4E4E9", accent="#C95770", accent_text="#FFFFFF",
    hover="#F1E7EA", stage=None,
)
DARK = dict(
    window="#15151A", surface="#1C1C21", elevated="#26262C", text="#F3F3F5",
    muted="#9A9AA3", border="#33333B", accent="#C95770", accent_text="#FFFFFF",
    hover="#3A2A30", stage="#3A1D22",
)


def hexc(value: str, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    c.setAlphaF(alpha)
    return c


def font(size: float, weight: int = 400) -> QFont:
    f = QFont("MiSans")
    f.setPixelSize(int(round(size)))
    f.setWeight(QFont.Weight(weight))
    return f


def rounded(p: QPainter, rect: QRectF, radius: float, fill: QColor, border: QColor | None = None):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, fill)
    if border is not None:
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


def label(p: QPainter, rect: QRectF, text: str, size: float, color: QColor,
          weight: int = 400, align=Qt.AlignLeft | Qt.AlignVCenter):
    p.setFont(font(size, weight))
    p.setPen(QPen(color))
    p.drawText(rect, int(align), text)


def icon(p: QPainter, name: str, rect: QRectF, color: QColor):
    icons.draw(p, name, rect, color)


def slider(p: QPainter, rect: QRectF, ratio: float, c: dict):
    track = QRectF(rect.left(), rect.center().y() - 2, rect.width(), 4)
    rounded(p, track, 2, hexc(c["text"], 0.16))
    done = QRectF(track.left(), track.top(), track.width() * ratio, track.height())
    rounded(p, done, 2, QColor(c["accent"]))
    knob = QPointF(track.left() + track.width() * ratio, track.center().y())
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c["accent_text"]))
    p.drawEllipse(knob, 7, 7)
    p.setBrush(QColor(c["accent"]))
    p.drawEllipse(knob, 5.5, 5.5)


def toggle(p: QPainter, rect: QRectF, on: bool, c: dict):
    track = QRectF(rect.left(), rect.center().y() - 11, 40, 22)
    rounded(p, track, 11, QColor(c["accent"]) if on else hexc(c["text"], 0.18))
    x = track.right() - 11 if on else track.left() + 11
    p.setPen(Qt.NoPen)
    p.setBrush(hexc(c["accent_text"], 0.98) if on else QColor(c["surface"]))
    p.drawEllipse(QPointF(x, track.center().y()), 8.5, 8.5)


def segmented(p: QPainter, rect: QRectF, items, active: int, c: dict):
    rounded(p, rect, rect.height() / 2, hexc(c["text"], 0.06))
    seg_w = (rect.width() - 8) / len(items)
    for i, text in enumerate(items):
        seg = QRectF(rect.left() + 4 + seg_w * i, rect.top() + 4, seg_w, rect.height() - 8)
        if i == active:
            rounded(p, seg, seg.height() / 2, QColor(c["surface"]))
            p.setPen(QPen(hexc(c["text"], 0.06), 1))
            p.drawPath(_path(seg, seg.height() / 2))
        label(p, seg, text, 12, QColor(c["text"]) if i == active else hexc(c["text"], 0.55), 600 if i == active else 400,
              Qt.AlignCenter)


def _path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def swatches(p: QPainter, rect: QRectF, colors, selected: int, c: dict):
    step = rect.width() / len(colors)
    for i, color in enumerate(colors):
        center = QPointF(rect.left() + step * (i + 0.5), rect.center().y())
        p.setPen(QPen(hexc(c["text"], 0.12), 1))
        p.setBrush(QColor(color))
        p.drawEllipse(center, 9, 9)
        if i == selected:
            p.setPen(QPen(QColor(c["accent"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center, 13, 13)
            mark = QColor("#1C1B1D") if QColor(color).lightnessF() > 0.62 else QColor("#FFFFFF")
            icon(p, "check", QRectF(center.x() - 5, center.y() - 5, 10, 10), mark)


def row(p: QPainter, rect: QRectF, title: str, hint: str, c: dict, control_w: float = 220):
    label(p, QRectF(rect.left(), rect.top(), rect.width() - control_w - 24, 20), title, 13, QColor(c["text"]), 600)
    label(p, QRectF(rect.left(), rect.top() + 20, rect.width() - control_w - 24, 18), hint, 11, QColor(c["muted"]))
    return QRectF(rect.right() - control_w, rect.center().y() - 12, control_w, 24)


def lyrics_settings(p: QPainter, rect: QRectF, c: dict):
    rounded(p, rect, 14, QColor(c["surface"]), hexc(c["text"], 0.06))
    label(p, QRectF(rect.left() + 24, rect.top() + 18, 300, 26), "桌面歌词", 16, QColor(c["text"]), 700)
    label(p, QRectF(rect.left() + 24, rect.top() + 44, 400, 20), "字体、颜色与透明度", 11, QColor(c["muted"]))
    seg = QRectF(rect.left() + 24, rect.top() + 76, 168, 32)
    segmented(p, seg, ["单行", "双行"], 1, c)

    y = rect.top() + 132
    knob = row(p, QRectF(rect.left() + 24, y, rect.width() - 48, 44), "字号", "歌词文字的像素高度", c, 250)
    slider(p, QRectF(knob.left(), knob.center().y(), 170, 24), 0.55, c)
    label(p, QRectF(knob.right() - 60, knob.center().y() - 10, 60, 20), "32 px", 12, QColor(c["text"]), 600,
          Qt.AlignRight | Qt.AlignVCenter)

    y += 60
    knob = row(p, QRectF(rect.left() + 24, y, rect.width() - 48, 44), "不透明度", "越低越容易读桌面内容", c, 250)
    slider(p, QRectF(knob.left(), knob.center().y(), 170, 24), 0.88, c)
    label(p, QRectF(knob.right() - 60, knob.center().y() - 10, 60, 20), "94%", 12, QColor(c["text"]), 600,
          Qt.AlignRight | Qt.AlignVCenter)

    y += 62
    knob = row(p, QRectF(rect.left() + 24, y, rect.width() - 48, 40), "描边", "在亮色桌面上加一圈暗边", c, 250)
    toggle(p, QRectF(knob.right() - 40, knob.center().y() - 11, 40, 22), True, c)

    y += 62
    label(p, QRectF(rect.left() + 24, y, 200, 20), "文字颜色", 12, QColor(c["text"]), 600)
    swatches(p, QRectF(rect.left() + 24, y + 26, 220, 34), ["#FFFFFF", "#F2C078", "#8FD3B6", "#C95770"], 0, c)

    y += 76
    label(p, QRectF(rect.left() + 24, y, 200, 20), "高亮颜色", 12, QColor(c["text"]), 600)
    swatches(p, QRectF(rect.left() + 24, y + 26, 220, 34), ["#C95770", "#F2C078", "#7FB6E8", "#B79BE8"], 0, c)


def context_menu(p: QPainter, rect: QRectF, c: dict, hover: int = 2):
    rounded(p, rect, 12, QColor(c["elevated"]), hexc(c["text"], 0.10))
    items = [
        ("lyrics", "显示 / 隐藏歌词", "Ctrl+Shift+L"),
        ("lock", "锁定位置", ""),
        ("settings", "桌面歌词设置…", ""),
        None,
        ("download", "调整偏移", ""),
        None,
        ("close", "退出桌面歌词", ""),
    ]
    y = rect.top() + 8
    for index, item in enumerate(items):
        if item is None:
            p.setPen(QPen(hexc(c["text"], 0.08), 1))
            p.drawLine(QPointF(rect.left() + 10, y + 3), QPointF(rect.right() - 10, y + 3))
            y += 13
            continue
        row = QRectF(rect.left() + 6, y, rect.width() - 12, 34)
        if index == hover:
            rounded(p, row, 8, hexc(QColor(c["accent"]).name(), 0.14))
        danger = item[1].startswith("退出")
        color = QColor("#D8546B") if danger else QColor(c["text"])
        icon(p, item[0], QRectF(row.left() + 8, row.center().y() - 9, 18, 18),
             color if danger else hexc(c["text"], 0.62))
        label(p, QRectF(row.left() + 34, row.top(), row.width() - 120, row.height()), item[1], 12.5, color, 500)
        if item[2]:
            label(p, QRectF(row.right() - 110, row.top(), 100, row.height()), item[2], 10.5, hexc(c["text"], 0.4),
                 400, Qt.AlignRight | Qt.AlignVCenter)
        y += 34


def player_bar(p: QPainter, rect: QRectF, c: dict, on: bool, repeat_on: bool):
    rounded(p, rect, 12, QColor(c["surface"]), hexc(c["text"], 0.06))
    y = rect.center().y() - 40
    # cover + text
    rounded(p, QRectF(rect.left() + 16, y + 6, 48, 48), 8, hexc(c["text"], 0.10))
    icon(p, "music_note", QRectF(rect.left() + 30, y + 20, 20, 20), hexc(c["text"], 0.5))
    label(p, QRectF(rect.left() + 76, y + 8, 240, 22), "家书", 13, QColor(c["text"]), 600)
    label(p, QRectF(rect.left() + 76, y + 30, 240, 18), "加木 · 网易音乐", 11, QColor(c["muted"]))

    cx = rect.center().x()
    cy = y + 30
    items = [("shuffle", on), ("prev", False), ("play", False), ("next", False), ("repeat", repeat_on)]
    gap = 46
    start = cx - gap * 2
    for i, (name, active) in enumerate(items):
        x = start + gap * i
        if name == "play":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["accent"]))
            p.drawEllipse(QPointF(x, cy), 20, 20)
            icon(p, "play", QRectF(x - 8, cy - 9, 18, 18), QColor(c["accent_text"]))
        else:
            icon(p, name, QRectF(x - 10, cy - 10, 20, 20),
                 QColor(c["accent"]) if active else hexc(c["text"], 0.78))
            if active:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c["accent"]))
                p.drawEllipse(QPointF(x + 10, cy + 10), 3.0, 3.0)

    # progress line under the controls
    bar = QRectF(rect.left() + 120, rect.bottom() - 26, rect.width() - 240, 4)
    rounded(p, bar, 2, hexc(c["text"], 0.14))
    rounded(p, QRectF(bar.left(), bar.top(), bar.width() * 0.34, 4), 2, QColor(c["accent"]))
    label(p, QRectF(bar.left() - 44, bar.center().y() - 9, 40, 18), "1:21", 10, QColor(c["muted"]), 400,
          Qt.AlignRight | Qt.AlignVCenter)
    label(p, QRectF(bar.right() + 6, bar.center().y() - 9, 44, 18), "4:02", 10, QColor(c["muted"]))


def source_actions_cards(p: QPainter, rect: QRectF, c: dict):
    label(p, QRectF(rect.left(), rect.top(), rect.width(), 22), "音源管理", 13, QColor(c["text"]), 600)
    cards = [
        ("plus", "添加音源", "安装 MusicFree 兼容插件（.js）"),
        ("cloud", "从链接添加", "粘贴插件地址，自动下载校验"),
        ("download", "导入订阅", "一次导入订阅里的全部音源"),
        ("folder", "批量导入", "选择文件夹，批量安装"),
    ]
    y = rect.top() + 34
    for index, (name, title, hint) in enumerate(cards):
        card = QRectF(rect.left(), y, rect.width(), 56)
        hovered = index == 1
        rounded(p, card, 10, hexc(c["text"], 0.055 if hovered else 0.03),
                hexc(c["text"], 0.12 if hovered else 0.07))
        icon(p, name, QRectF(card.left() + 14, card.center().y() - 10, 20, 20), hexc(c["text"], 0.62))
        label(p, QRectF(card.left() + 46, card.top() + 9, card.width() - 80, 20), title, 12.5, QColor(c["text"]), 600)
        label(p, QRectF(card.left() + 46, card.top() + 29, card.width() - 80, 18), hint, 10.5, QColor(c["muted"]))
        y += 64
    link = QRectF(rect.left(), y + 2, rect.width(), 26)
    label(p, link, "恢复内置音源", 11.5, hexc(c["text"], 0.5), 500)


def source_actions_menu(p: QPainter, rect: QRectF, c: dict):
    label(p, QRectF(rect.left(), rect.top(), rect.width(), 22), "音源管理", 13, QColor(c["text"]), 600)
    buttons = [
        ("添加音源", True, "chevron_down"),
        ("导入订阅", False, "chevron_down"),
        ("批量导入", False, None),
    ]
    y = rect.top() + 34
    for title, primary, chevron in buttons:
        b = QRectF(rect.left(), y, rect.width(), 38)
        if primary:
            rounded(p, b, 10, QColor(c["accent"]))
            fg = QColor(c["accent_text"])
        else:
            rounded(p, b, 10, hexc(c["text"], 0.04), hexc(c["text"], 0.09))
            fg = QColor(c["text"])
        text_w = QFontMetrics(font(12.5, 600 if primary else 500)).horizontalAdvance(title)
        gap = 6 if chevron else 0
        chev_w = 12 if chevron else 0
        left = b.center().x() - (text_w + gap + chev_w) / 2
        label(p, QRectF(left, b.top(), text_w + 2, b.height()), title, 12.5, fg,
              600 if primary else 500)
        if chevron:
            icon(p, chevron, QRectF(left + text_w + gap, b.center().y() - 6, 12, 12),
                 fg if primary else hexc(c["text"], 0.5))
        y += 46
    label(p, QRectF(rect.left(), y + 8, rect.width(), 22), "恢复内置音源", 11.5, hexc(c["text"], 0.45), 500,
          Qt.AlignCenter)


def render(path: Path, width: int, height: int, painter_fn, dark: bool):
    pixmap = QPixmap(int(width * 2), int(height * 2))
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(QColor(DARK["window"] if dark else LIGHT["window"]))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    painter_fn(p, DARK if dark else LIGHT)

    p.end()
    pixmap.save(str(path))


def mock_lyrics(p, c):
    lyrics_settings(p, QRectF(40, 24, 620, 486), c)


def mock_menu(p, c):
    # a hint of the desktop behind the menu, to show the elevation
    p.setPen(Qt.NoPen)
    p.setBrush(hexc(c["accent"], 0.10))
    p.drawEllipse(QPointF(300, 260), 180, 180)
    context_menu(p, QRectF(150, 70, 300, 214), c)


def mock_player(p, c):
    player_bar(p, QRectF(20, 20, 760, 118), c, on=True, repeat_on=False)
    player_bar(p, QRectF(20, 156, 760, 118), c, on=False, repeat_on=True)


def mock_sources(p, c):
    label(p, QRectF(40, 20, 700, 24), "方案 A · 动作卡", 12, hexc(c["text"], 0.5), 600)
    source_actions_cards(p, QRectF(40, 52, 330, 400), c)
    label(p, QRectF(410, 20, 700, 24), "方案 B · 主次按钮", 12, hexc(c["text"], 0.5), 600)
    source_actions_menu(p, QRectF(410, 52, 300, 260), c)


def main():
    app = QApplication(sys.argv)
    try:
        load_bundled_fonts()
    except Exception:
        pass
    out = Path("docs/design")
    out.mkdir(parents=True, exist_ok=True)
    for dark in (False, True):
        tag = "dark" if dark else "light"
        render(out / f"01_lyrics_settings_{tag}.png", 700, 540, mock_lyrics, dark)
        render(out / f"02_context_menu_{tag}.png", 600, 420, mock_menu, dark)
        render(out / f"03_player_bar_{tag}.png", 800, 300, mock_player, dark)
        render(out / f"04_sources_{tag}.png", 760, 470, mock_sources, dark)
    print("mocks written")


if __name__ == "__main__":
    main()
