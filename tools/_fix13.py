import pathlib
p = pathlib.Path("hushplayer/ui/widgets/common.py")
t = p.read_text(encoding="utf-8")
old = '''        painter.setClipPath(path)
        scaled = pixmap
        if pixmap.width() != int(rect.width()) or pixmap.height() != int(rect.height()):
            scaled = pixmap.scaled(
                int(rect.width()),
                int(rect.height()),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        x = rect.x() + (rect.width() - scaled.width() * (1.0 / (scaled.devicePixelRatio() or 1.0))) / 2
        y = rect.y() + (rect.height() - scaled.height() * (1.0 / (scaled.devicePixelRatio() or 1.0))) / 2
        painter.drawPixmap(QPointF(x, y), scaled)'''
new = '''        painter.setClipPath(path)
        dpr = pixmap.devicePixelRatio() or 1.0
        target_w = max(1, int(round(rect.width() * dpr)))
        target_h = max(1, int(round(rect.height() * dpr)))
        scaled = pixmap
        if pixmap.width() != target_w or pixmap.height() != target_h:
            scaled = pixmap.scaled(
                target_w,
                target_h,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
        logical_w = scaled.width() / (scaled.devicePixelRatio() or 1.0)
        logical_h = scaled.height() / (scaled.devicePixelRatio() or 1.0)
        x = rect.x() + (rect.width() - logical_w) / 2
        y = rect.y() + (rect.height() - logical_h) / 2
        painter.drawPixmap(QPointF(x, y), scaled)'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("ok")
