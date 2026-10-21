import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from hushplayer.core.theme import theme
q = theme().qss()
print("menu:", "QMenu::item:selected" in q, "combo:", "QComboBox QAbstractItemView::item" in q, "len:", len(q))
