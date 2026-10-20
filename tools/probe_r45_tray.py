import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication(sys.argv)
w = QWidget(); w.show()
from hushplayer.services.tray_probe import probe_registration, describe
from hushplayer.core.brand import tray_icon_path
ok, err = probe_registration(int(w.winId()), tray_icon_path())
print("probe", ok, err, describe(err), flush=True)
