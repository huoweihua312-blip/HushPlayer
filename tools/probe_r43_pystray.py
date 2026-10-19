import sys, time
sys.path.insert(0, ".")
from PIL import Image
import pystray

img = Image.open("assets/hushplayer.png").convert("RGBA").resize((64, 64), Image.LANCZOS)
icon = pystray.Icon("hush-tray-probe", img, "HushPlayer tray probe")
try:
    icon.run_detached()
    time.sleep(1.5)
    print("visible", icon.visible, "backend", type(icon._manager).__name__ if hasattr(icon, "_manager") else "?", flush=True)
    if hasattr(icon, "_hwnd"):
        print("hwnd", icon._hwnd, flush=True)
except Exception as exc:
    print("error", type(exc).__name__, exc, flush=True)
finally:
    try:
        icon.stop()
    except Exception:
        pass
print("done", flush=True)
