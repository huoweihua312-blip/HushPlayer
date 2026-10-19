import sys, ctypes, uuid
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QWidget
from hushplayer.services import taskbar as TB
app = QApplication(sys.argv)
w = QWidget(); w.show()
ole32 = ctypes.windll.ole32
print("CoInitializeEx", ole32.CoInitializeEx(None, 2))  # STA
ptr = ctypes.c_void_p()
clsid = TB._guid(TB.CLSID_TASKBAR); iid = TB._guid(TB.IID_TASKBAR3)
hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(ptr))
print("hr", hex(hr & 0xFFFFFFFF), "ptr", bool(ptr))
if hr == 0:
    vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[3])
    print("init hr", hex(init(ptr) & 0xFFFFFFFF))
    sv = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_ulonglong)(vt[9])
    print("setvalue hr", hex(sv(ptr, ctypes.c_void_p(int(w.winId())), 500, 1000) & 0xFFFFFFFF))
