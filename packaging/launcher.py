"""PyInstaller 入口：打包后的 HushPlayer.exe 从这里启动。"""

from __future__ import annotations

import sys

from hushplayer.app import main

if __name__ == "__main__":
    sys.exit(main())
