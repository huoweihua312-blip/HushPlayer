"""生成 PyInstaller 的 Windows 版本资源文件。

用法：python tools/make_versioninfo.py [输出路径]
版本号来自 hushplayer/version.py，避免两处维护。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hushplayer.version import APP_NAME, VERSION  # noqa: E402

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '080404b0',
          [StringStruct('CompanyName', 'HushPlayer'),
           StringStruct('FileDescription', '{app}'),
           StringStruct('FileVersion', '{version}'),
           StringStruct('InternalName', '{app}'),
           StringStruct('LegalCopyright', 'Copyright (c) 2026 HushPlayer contributors'),
           StringStruct('OriginalFilename', '{app}.exe'),
           StringStruct('ProductName', '{app}'),
           StringStruct('ProductVersion', '{version}')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else ROOT / "packaging" / "version_info.txt"
    parts = [int(piece) for piece in VERSION.split(".")]
    while len(parts) < 4:
        parts.append(0)
    text = TEMPLATE.format(
        numbers=tuple(parts[:4]),
        app=APP_NAME,
        version=VERSION,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
