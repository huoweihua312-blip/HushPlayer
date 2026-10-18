# Brand assets (official logo goes here)

HushPlayer 的正式 Logo 由项目作者提供。本目录是**唯一**的品牌资源入口：
把下列文件放到这里，重新启动程序（或重新打包）即可全局生效，无需改代码。

| 文件 | 用途 | 规格 |
| --- | --- | --- |
| `logo.png` | 通用标志（浅色/深色共用） | 正方形，建议 1024×1024，透明背景 |
| `logo_light.png` | 浅色主题专用 | 同上；深色底上不可用时才需要 |
| `logo_dark.png` | 深色主题专用 | 同上 |
| `icon.ico` | Windows 可执行文件 / 窗口 / 托盘图标 | 多尺寸 16/24/32/48/64/128/256 |
| `icon.png` | 单尺寸备用图标 | 512×512 或 1024×1024 |

约定：

- 使用透明背景、正方形画布，Logo 图形四周留 6%–10% 安全边距。
- 不要自带圆角或阴影，程序会按界面需要裁切圆角。
- 深色主题标志请保证在 `#15151A` 背景上可辨识；浅色主题在 `#FFFFFF` 上可辨识。
- 未提供上述文件时，程序使用 `assets/hushplayer.png`（占位图标）并在关于页标注「占位标志」。

生成 `icon.ico` 可以用 Pillow：

```python
from PIL import Image

image = Image.open("assets/brand/logo.png")
image.save("assets/brand/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
```
