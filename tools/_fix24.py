import pathlib
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")
t = t.replace("from PySide6.QtWidgets import QApplication  # noqa: E402",
              "from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402\nfrom PySide6.QtWidgets import QApplication  # noqa: E402")
p.write_text(t, encoding="utf-8")
print("ok")
