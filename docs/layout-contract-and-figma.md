# 布局契约收尾与 Figma 概念设计

日期：2026-09-09。概念设计未实施到 Python。

## 布局修复

ArtistDetailPage 的介绍文本更新和响应式更新统一读取 `self.window().width()`：1450 是 Qt logical window_width 阈值，不是减去导航后的 content_width，也不是表格 viewport_width。阈值仍为 1450；介绍栏宽度仍为 260。无介绍内容或无歌手时隐藏。保留旧方法参数以兼容现有调用；其他断点、主窗口协调和业务行为不变。

测试覆盖窗口 1449、1450、1451、1080，混入不同内容宽度参数，以及空介绍。17 项歌手页面测试通过。

## DPI 基线

截图位于忽略目录 `build/ui-baseline/dpi-1`、`dpi-1.25`、`dpi-1.5`，各 34 张，共 102 张；每组包含 manifest.json 与 dpi-details.json。这些基线在本次介绍栏修复前采集；修复后另存 `build/ui-baseline/layout-contract-fixed`。

| 缩放 / DPR | logical 900×800 | logical 1080×800 | logical 1450×800 |
| --- | --- | --- | --- |
| 100% / 1 | 900×800 | 1080×800 | 1450×800 |
| 125% / 1.25 | 1125×1000 | 1350×1000 | 1813×1000 |
| 150% / 1.5 | 1350×1200 | 1620×1200 | 2175×1200 |

表内是 Qt 窗口抓图像素尺寸，不含系统外部阴影。使用独立进程 QT_SCALE_FACTOR 验证，未修改 Windows 系统缩放；不代表多显示器跨屏 DPI 验收。正式启动入口、临时隔离数据和 mock 播放用于截图，不访问用户音乐库。

覆盖浅色/深色、Sidebar、TrackList、PlayerBar、SettingsOverlay、LyricsPage、ImmersiveLyricsPage、长标题、空状态、播放与选中。记录的侧栏、表格 QWidget、播放器标题基础字体为 MiSans Regular，16 logical px，12 pt，weight 400；该记录不是逐个歌词绘制字符的实际字体枚举。Qt 6.11.1，Python 3.12.14。

抽查 125% 设置和 150% 列表截图：整体尺寸符合 DPR；播放器超长文字仍存在直接裁切，后续应检查省略显示。列表滚动状态可出现顶部半行，不能当作静止顶部布局缺陷。未修改这些行为。

## Figma

文件：https://www.figma.com/design/LVoYsfCQnr8YBO9VQREXCY

| 方向 | 1450×900 node | 1080×900 node | 优点 | 代价 |
| --- | --- | --- | --- | --- |
| A Minimal Dark | 2:14 | 2:15 | 安静、列表优先、视觉负担小 | 封面与品牌表现较弱 |
| B Fluent Modern | 2:27 | 2:28 | 封面突出、状态清楚、适合 Windows | 页首卡片占用更多高度 |
| C Linear / Editorial | 2:40 | 2:41 | 排版识别度强、暖色克制 | 大标题占高度，直角风格更挑偏好 |

每张包含 Shell、标题栏、导航、TrackList、PlayerBar。第一行为 Playing，第二行为 Hover，第三行为 Selected；普通行包含本地组件实例。设计使用独立颜色变量、Noto Sans SC 字体与原生矢量封面占位，未引入商业封面素材。字体选择只用于 Figma，不更换程序字体。

保留左侧导航和底部播放器；右栏仍由具体页面按需提供，典型曲目列表不增加常驻歌词栏。未设计设置、歌词、沉浸、在线搜索或桌面歌词页面。导航保留在线搜索入口不代表设计该页面。

推荐 B，后续先确认视觉方向，再逐个组件实施；应进一步验证长文本、键盘焦点、实际鼠标命中和更矮窗口。概念稿是静态设计，不表示交互已实现。

## 验证及回退

执行 `.venv/Scripts/python.exe -m unittest tests.test_ui_v2_artist_page -v`：17 项通过。

执行 `.venv/Scripts/python.exe -m py_compile main.py app/ui_v2/shell/main_window.py app/ui_v2/pages/artist_detail_page.py tests/test_ui_v2_artist_page.py`：通过。

执行 `.venv/Scripts/python.exe tools/ui_baseline.py --output build/ui-baseline/layout-contract-fixed` 生成修复后截图。截图不纳入 Git。人工验收：进入有介绍的歌手详情，在窗口宽度 1449/1450 附近调整，验证介绍栏显示稳定；播放与页面切换仍需用户实测。

修改范围仅介绍栏显示判断、对应测试、未发布日志和本记录。没有改变播放、队列、歌词、持久化 JSON、依赖或 signal/slot 语义。需要回退时可以对本次独立提交做反向提交，不重置其他历史。
