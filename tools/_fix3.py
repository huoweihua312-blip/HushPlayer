import pathlib
p = pathlib.Path("hushplayer/ui/pages/settings.py")
t = p.read_text(encoding="utf-8")
t = t.replace('from PySide6.QtCore import QSize, Qt\n', 'from PySide6.QtCore import QSize, Qt, Signal\n')
t = t.replace('    changed = __import__("PySide6.QtCore", fromlist=["Signal"]).Signal(int)\n', '    changed = Signal(int)\n')
t = t.replace('        column.add_widget = None  # guard against accidental misuse\n', '')
t = t.replace('            row = SettingsCard()\n            card.add(self._shortcut_row(keys, text))', '            card.add(self._shortcut_row(keys, text))')
p.write_text(t, encoding="utf-8")
print("patched")
