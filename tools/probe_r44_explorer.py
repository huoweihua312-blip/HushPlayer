import sys, time
sys.path.insert(0, r"F:\Projects\HushPlayer-Reimagined")
from PIL import Image
import pystray
out = r"F:\Projects\HushPlayer-Reimagined\artifacts\qa\r44\probe_result.txt"
try:
    img = Image.open(r"F:\Projects\HushPlayer-Reimagined\assets\brand\logo.png").convert("RGBA").resize((64,64), Image.LANCZOS)
    icon = pystray.Icon("hush-explorer-probe", img, "HushPlayer explorer probe")
    icon.run_detached(); time.sleep(1.5)
    open(out,"w",encoding="utf-8").write(f"OK visible={icon.visible}\n")
    time.sleep(3); icon.stop()
except Exception as exc:
    open(out,"w",encoding="utf-8").write(f"ERR {type(exc).__name__}: {exc}\n")
