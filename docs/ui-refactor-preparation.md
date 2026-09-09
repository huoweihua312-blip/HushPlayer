# UI 重构准备阶段

本阶段基于已验收的 MiSans / FreeType 界面，保持像素值、业务、信号和旧入口。
选择兼容别名与单点接入，而非修改全部调用方或重写页面。主窗口、路由、歌词画布、
桌面歌词、沉浸核心、服务和持久化代码均不属于修改范围。

## Token 规范

仍以 `app/ui_v2/theme/tokens.py` 为唯一普通界面 Token 来源。
新增别名使用只读 property，引用既有字段，避免多份数值漂移；原 dataclass 构造参数、
`dataclasses.replace`、旧名字以及明暗主题具体值保持不变。新增别名不是构造参数。

| 语义 | 推荐字段 | 保留兼容名 / 来源 |
| --- | --- | --- |
| 应用、内容背景 | background、content_background | app_background、window_background |
| 表面 | surface、surface_secondary、surface_elevated | surface_primary、elevated_background |
| 导航 | sidebar | sidebar_background、navigation_background |
| 主要、次要文字 | text_primary、text_secondary | primary_text、secondary_text |
| 弱文字、禁用文字 | text_muted、text_disabled | text_tertiary、subtle_text、disabled_text |
| 强调 | accent、accent_hover、accent_pressed | 原值保留 |
| 分隔 | divider | border |
| 悬浮、选中 | surface_hover、surface_selected | hover_background、selected_background |
| 正在播放 | surface_playing | playing_background |
| 禁用表面 | surface_disabled | surface_secondary；不统一覆盖原透明禁用按钮 |
| 错误、警告 | error、warning | danger |
| 圆角 | radius_control、radius_card、radius_dialog | radius_sm/md/lg：8/10/16 |
| 间距 | spacing_xs/sm/md/lg/xl | 4/8/12/16/24 |
| 控件 | control_height_md | control_height：40 |
| 图标 | icon_sm/md/lg | 16/20/24；现有播放器特殊尺寸暂保留 |
| 字体角色 | label、title、subtitle | control/page_title/section_title：15/32/21 |
| 其余文字 | body、caption、track_title、metadata、player_title、player_meta | 原值不变 |

字体加载、FreeType、字号与字重没有调整。沉浸专属 Token 保持独立。

## 尺寸与响应式

所有值为 Qt 逻辑像素，不是截图物理像素。`LayoutWidths` 显式携带：

- window_width：主窗口完整客户区宽度。
- content_width：路由内容区实际宽度，不假设导航始终为 220。
- viewport_width：表格/滚动区域去除边框、滚动条之后的可用宽度。

宽度由拥有对应 QWidget 的调用方测量，基础组件不自行减去猜测的导航尺寸。
表格模式选取沿用窗口参考宽度，列分配使用 viewport_width。现阶段没有改动主窗口传参。

### 分类方案：按用途分档，不设一个全局判定

| 用途 | compact | medium | wide | extra-wide |
| --- | --- | --- | --- | --- |
| 主壳 | <=1080 | >1080 | 暂无独立档 | 暂无独立档 |
| 歌曲表 | <950 | 950–1219 | >=1220 | 暂无独立档 |
| 设置 | <1000 | >=1000 | 暂无独立档 | 暂无独立档 |
| 沉浸工作区 | <1100 | 1100–1399 | 1400–1699 | >=1700 |
| 浏览密度 | <=960，3列目标 | <1200，4列目标 | <1440，5列；<1600，6列 | >=1600，7列 |
| 信息侧栏 | 隐藏 | 隐藏 | >=1450 可显示 | 同 wide |

960 还用于沉浸控制条；1450 还用于实体网格。1440 是审计时发现的额外浏览断点，保留。
`ResponsiveThresholds` 为上述现有阈值命名；仅歌曲表的 950/1220 数字引用迁移，
原 narrow/standard/wide 字符串、边界比较符号和可见列不变。
其余页面及 NowPlaying 的 900 阈值保留原实现，下一阶段逐一明确消费的宽度来源。

## 基础组件单点迁移

| 新基础设施 | 本阶段使用点 | 保持的边界 |
| --- | --- | --- |
| ContentSurface | LibraryPage.view_host | 旧 view_stack 别名、内容/空状态、128px 配置值；启用样式背景绘制 |
| SearchField | EntityGridPage 的一个构造点 | 旧 objectName、输入控制器、Enter/清空/去抖语义 |
| CollectionActionBar | AllSongsPage | 继承旧 Row 的信号和动作，旧 Row 文件保留 |
| action_button_qss | CollectionActionBar | 两种主题下与旧按钮 QSS 完全相同 |
| TrackIdentity | PlayerBar.metadata | 只排列调用方传入的两个 Label，不读 Track、不绑定播放、不改文字更新 |

这里的一个使用点按源代码构造点计数；EntityGridPage 已被歌手与专辑列表共用。
SearchField 暂保留与旧 SearchBox 的兼容实现，CollectionActionBar 暂复用旧 Row 构造与布局。
这是分阶段入口，不宣称已消除所有重复；后续验证新入口后才考虑让旧入口委托新实现。

## 两处布局疑点：运行证据

正式启动初始化 + 隔离 mock 数据 + Windows FreeType，窗口高 800，DPR 1：

| 窗口宽 | 内容宽 | 表格 viewport 宽 | body 底部 | PlayerBar 顶部 |
| --- | --- | --- | --- | --- |
| 900 | 824 | 754 | 697 | 698 |
| 1080 | 1004 | 934 | 697 | 698 |
| 1450 | 1230 | 1160 | 697 | 698 |

A：播放器确实独立占位，内部 QStackedLayout 的配置底边距为 128。
但表格实测占满 420 高的容器，底坐标 419，实际剩余底空隙为 0；截图也未显示 128px 空白。
因此只能确认配置层存在重复预留意图，不能确认可见重复留白，不修改它。

B：正确解析的歌手详情，在窗口 1450、页面 1230 时，用 `_set_info_rail` 的页面宽判定隐藏，
用 `_update_info_rail_visibility(1450)` 判定显示；两张截图可对照。
测试注入固定介绍文案，不修改真实歌手数据。此问题复现但未修正。

## 截图基线

脚本：`tools/ui_baseline.py`。运行真实 QApplication 初始化及 MainWindow 的 mock 模式，
临时目录隔离设置、缓存、歌曲；不是实际音频播放验收，不访问用户音乐库。

```powershell
.\.venv\Scripts\python.exe tools/ui_baseline.py --output build/ui-baseline/my-new-run
```

输出目录必须不存在，避免覆盖基线。每次输出 PNG 与 manifest.json，记录平台、Python、
DPR、窗口和视口尺寸、布局疑点。`build/` 已被 Git 忽略，不进入正式资源或提交。

- preparation-before-verified：组件迁移前有效基线，32 张；Token 别名和等值断点引用已加入，无视觉变化。
- preparation-final：最终基线，34 张；增加明暗歌手列表 SearchField 页面。
- preparation-before：初次探测，歌手样本无效，不作歌手验收依据。
- preparation-after：中间诊断，发现 ContentSurface 样式背景问题，不作最终验收依据。

覆盖明暗各 900/1080/1450 宽：长歌名、播放中和另一行选中、设置、普通歌词、沉浸歌词、空状态。
另有歌手栏两种宽度判断、明暗歌手列表截图。高 800，DPR 1，其他 DPI 仍待人工验收。
动态歌词高亮与背景动画不保证逐像素重现，比较时必须区分静态页面与动画帧。

## 检查与回退

定向测试：`tests.test_ui_foundations`；新增每个接入点之后运行，再继续下一点。
旧内容测试行高断言 48 已过时（当前 HEAD 的 Token 为 60），改为检查实际行高与主题 Token 一致，
保留原可见列、滚动策略和模型不重建断言。

每次只迁移一个源构造点，旧实现保留。最终用一个独立本地提交收束，不推送。
回退时对本阶段提交执行普通 revert；基线保留供比较，不重置其他工作或用户数据。

下一阶段先统一歌手栏宽度来源及补齐 DPI 基线，再逐个让旧兼容入口委托基础组件。
不建议此时处理主窗口拆分、路由机制、歌词画布或播放信号重接。

### 本次执行结果

环境：Python 3.12.14，现有项目虚拟环境；未安装依赖，不代表 CPython 3.13 打包验收。

- `python -m unittest tests.test_ui_foundations`：逐步接入后最终 6 项通过。
- `python -m unittest tests.test_ui_v2_content_pages tests.test_ui_v2_q3_content_contract tests.test_ui_v2_artist_page tests.test_ui_v2_responsiveness tests.test_ui_v2_main_window`：67 项中 66 项通过，唯一失败是旧 48px 行高断言。
- 修正断言后执行 `python -m unittest tests.test_ui_foundations tests.test_ui_v2_content_pages -v`：19 项通过。其余 54 项已在上一轮通过；本阶段共覆盖 73 个不同测试。
- 对全部新增/修改 Python 文件及 main.py、MainWindow 执行 `py_compile`：17 个文件通过；UTF-8 解码通过。
- PlayerBar 的 AST 对比只有 `_build_layout` 改变，播放状态和信号处理方法不变。
- `git diff --check` 通过。
- 改前有效基线与最终基线的 26 张静态截图逐像素相同。6 张沉浸截图只在当前歌词高亮边缘存在 25–378 个像素差异（动态取帧）。
- 未改用户可见功能，不把纯内部准备工作写成更新日志功能条目。

未完成：实际音频播放人工验收、其他 DPI/屏幕上的验证、两项布局疑点的正式修复、其他调用点迁移。
