import sys, ctypes, uuid
sys.path.insert(0, ".")
from hushplayer.services import taskbar as TB
ole32 = ctypes.windll.ole32
ole32.CoInitializeEx(None, 2)
clsid = TB._guid(TB.CLSID_TASKBAR)
iid1 = TB._guid(uuid.UUID("{56FDF342-FD6D-11d0-958A-006097C9A090}"))
ptr = ctypes.c_void_p()
hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid1), ctypes.byref(ptr))
print("create v1", hex(hr & 0xFFFFFFFF))
if hr == 0:
    vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    qi = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(vt[0])
    for name, s in (("v2","{602D4995-B13A-429b-ADB0-7A6B5E4B4A26}"), ("v3","{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84}")):
        iid = TB._guid(uuid.UUID(s)); out = ctypes.c_void_p()
        print(name, hex(qi(ptr, ctypes.byref(iid), ctypes.byref(out)) & 0xFFFFFFFF))
