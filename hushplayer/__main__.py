"""允许使用 ``python -m hushplayer`` 启动。"""

from __future__ import annotations

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
