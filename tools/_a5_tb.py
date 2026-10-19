import sys, ctypes, uuid
sys.path.insert(0, ".")
from hushplayer.services import taskbar as TB
ole32 = ctypes.windll.ole32
ole32.CoInitializeEx(None, 2)
clsid = TB._guid(TB.CLSID_TASKBAR)
for ctx in (1, 4, 5, 0x17):
    for name, iid_uuid in (("ITaskbarList", "{56FDF342-FD6D-11d0-958A-006097C9A090}"),
                           ("ITaskbarList2", "{602D4995-B13A-429b-ADB0-7A6B5E4B4A26}"),
                           ("ITaskbarList3", "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84}")):
        ptr = ctypes.c_void_p()
        iid = TB._guid(uuid.UUID(iid_uuid))
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, ctx, ctypes.byref(iid), ctypes.byref(ptr))
        print(ctx, name, hex(hr & 0xFFFFFFFF))
