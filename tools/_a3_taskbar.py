import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QWidget
from hushplayer.services.taskbar import TaskbarProgress
app = QApplication(sys.argv)
w = QWidget(); w.resize(400, 300); w.show()
tb = TaskbarProgress()
print("available", tb.available)
hwnd = int(w.winId())
print("hwnd", hwnd)
tb.set_progress(hwnd, 0.45)
tb.set_tooltip(hwnd, "HushPlayer 测试")
print("called")
