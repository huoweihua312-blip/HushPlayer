# HushPlayer B2 Design Freeze

状态：主要视觉家族已获用户确认；冻结视觉方向，尚未授权 PySide6 迁移。核对日期：2026-09-10。源码基准：`design/ui-v2-real-playback`，`f342a86`。本规格不修改运行时 Token。

## 权威与适用边界

视觉来自 `build/ui-concepts/` 下已确认的 Shell、Playback、Collection、Online & Import、Settings & System；行为、入口、可用条件以当前正式源码为准。原型 mock 的能力不能成为产品需求。后出的 Collection Light 规格覆盖最初 Shell 浅色试稿；Settings/System 的通用焦点和反馈规格用于相应系统组件。保留家族例外，不通过统一 Token 把所有页面变成同一种容器。

设计资产与验证仍位于 Git 忽略的 build；本文件及关联文档保存可跟踪的交接规格。保留 MiSans 许可证及现有图标 MANIFEST。原型入口的审核下拉栏不是产品 UI。

交接文档：

- [组件映射](ui-v2-b2-component-map.md)
- [正式菜单映射](ui-v2-b2-menu-map.md)
- [Surface 覆盖矩阵](ui-v2-b2-surface-coverage.md)
- [状态映射](ui-v2-b2-state-map.md)
- [实施计划与视觉回归](ui-v2-b2-implementation-plan.md)
- [不可回归契约](ui-v2-b2-non-regression-contract.md)

## A. 颜色冻结

以下是原型实际 CSS 值，不是当前 Qt 值。CSS 八位十六进制是 RRGGBBAA；迁移 QColor 时须显式拆 alpha，不能误作 Qt ARGB。低透明背景以实际所在 Surface 合成。

| 语义 | Dark | Light | Qt 角色与例外 |
|---|---|---|---|
| App Background | #111111 | #f5f5f3 | app_background / window_background |
| Content Background | #111111 | #fafaf8 | content_background；普通页面开放背景 |
| Sidebar | #171717 | #eeeeec | sidebar_background / navigation_background |
| Surface | #1b1b1b | #f0f0ed | surface_primary；不是每行加容器 |
| Elevated / Dialog | #20211e | #f6f6f2 | surface_elevated / elevated_background，系统家族 |
| Input | #272823 | #eaeae4 | input_background |
| PlayerBar | #191919 | #f5f5f3 | playerbar_background；安静连续底栏 |
| Primary Text | #f2f1ee | #1d1d1f | primary_text / text_primary |
| Secondary Text | #c8c7c3 | #66666a | secondary_text / text_secondary |
| Muted Text | #858580 | #73736f | text_tertiary / subtle_text；只用于低权重说明 |
| Accent text / icon | #c9a86a | #876625 | accent；不改成红色 |
| Primary button fill | #c9a86a | #c4a363 | 与浅色文字 Accent 分离；System 按钮现稿 #c9a86a |
| Divider | #292925 | #deded9 | divider；细分隔，禁止普遍加边框 |
| Hover | #1c1c1b | #eeeeea | hover_background；Track 原始 Shell 存在 #1b1b1a 例外 |
| Selected | #292927 | #e2e2dd | selected_background；中性色 |
| Playing tint | #c9a86a06 | #98762e08 | playing_background；主要识别是金色标题与播放标记 |
| Disabled text | #70716b | #858580 | disabled_text；不靠降低整个父窗口 opacity 实现 |
| Error inline | #cf8d7e | #a6473d | 内容 error；系统 danger 使用下一行 |
| Destructive / System error | #dc9a8d | #9f493b | danger；确认按钮/行内错误 |
| Warning | #c9b37d | #826423 | warning |
| Success | #a2b898 | #52684b | success |
| Keyboard Focus | #c9a86a | #876625 | focus_ring；System 2px + offset 3px |
| Scrim | #080a0a99 | #20292245 | overlay；不把 alpha 应用于对话框文字 |

取值证据：Shell `style.css`；Collection `styles/collection.css`、`styles/light.css`；Online `styles/online.css`；System `styles/system.css`。CSS 存在具体 selector 覆盖，例如 Sidebar Selected 为 #292822 / #e2e1d9，TrackTitle Dark 为 #e1e0da；这些保留为角色变体，Phase 0 不用全局替换抹平。

沉浸背景保留封面衍生气氛及可读性保护，不能套用普通页面 bg。深色浮层 #1d2524ed；浅色浮层 #f5f5f0f7；桌面歌词是独立透明文字窗口，不继承 Surface。用户指定的歌词文字颜色/背景透明度优先于主窗口主题。

## B. Typography

随包 MiSans Regular 400 / Semibold 600；正式字体注册与 FreeType 设置继续沿用。不能依赖用户在线下载字体、不能为了匹配浏览器改回 Windows 默认字体引擎。下表 CSS px 是设计参考；Qt 中使用逻辑像素角色，经 DPR/实际中文字形验收，不直接复制成 pt。使用 `setPixelSize` 时不得再乘 DPR；如使用 pt，须明确按 logical DPI 换算。

| 角色 | 原型参考 | Qt 语义 |
|---|---|---|
| Page Title | Shell 36/600；Collection 34/600；System 场景 31；Settings 标题 25 | page_title / hero_title，页面层级，不要求所有标题同大 |
| Section Title | Collection 19/600；Settings 20 左右；Dialog 21 | section_title，分组标题 |
| Track Title | 14/400；队列 13/400 | track_title；可省略、全文 Tooltip；Playing 改色而非增粗 |
| Body / Control | 13–14/400；设置标签 14 | body / control，不随 compact 整体缩放 |
| Metadata | 11–13/400 | metadata / player_meta；与标题分离 |
| Caption / numeric | 10–12/400 | caption / numeric；时间等宽数字布局 |
| Normal Lyrics | 当前 32（1080 为30）；周边27/25；翻译14 | Canvas active / normal / translation，仍由响应式歌词度量计算 |
| Immersive Lyrics | 当前36（1080为30；1700+为42）；翻译16/14 | 沉浸 active 角色，保留用户 font scale 与同步算法 |
| Desktop Lyrics | 当前38；长文34；翻译18；弹层演示当前30 | 独立窗口用户字号、换行与屏幕 fit，不能硬编码成主窗字体 |

当前 Qt `ThemeFonts` 常规正文16、track_title17、metadata14 等较 CSS 大。迁移须保留中文清晰度验收，不把这些数值一次性降到浏览器大小。长说明允许换行，短按钮禁止中文逐字换行。

## C. Spacing / Geometry

基础间距 4 / 8 / 12 / 16 / 24 / 32。保留实际特殊值：页面左右42（compact30）、Shell 标题栏60、Sidebar224/76、PlayerBar108、TrackRow59、行内 gap14/16、底栏 gap26/20、Artwork42/54。它们是目标几何角色，不是要替换所有当前 Qt 数值的全局常量。

设置：1450 时 overlay 最大1120×748，导航202；1080 时左右各24、导航160、高度 viewport−100；头82、底66，控件220/190。外层不滚，右内容滚动。主窗当前最小900×600另做专项验收，不照搬 HTML 的 min-height780。

## D. Radius

| 角色 | 冻结参考 |
|---|---|
| Control / row | 3–5px，开关为胶囊 |
| Artwork | 小图3、底栏4、沉浸大图6 |
| Surface | 开放内容不需要圆角；只在实际容器保留小圆角 |
| Floating Panel | 沉浸11、桌面设置9 |
| Dialog | 11；Settings overlay 另按已确认外框保留 |
| 特殊形状 | 播放圆形、色板圆形；回到当前歌词按钮20px 是局部例外 |

## E. Icon 与 Hit Area

| 角色 | 图形视觉尺寸 | 点击区域/布局 |
|---|---|---|
| Small | 14–16 | 原型通常32×32；文字按钮由padding提供区域 |
| Normal | 18–20 | 普通图标按钮32×32；导航整行39高 |
| Previous / Next | 21 | 保留32×32以上目标与相邻间距 |
| Primary Playback | 图形19，圆37；沉浸圆48 | 圆形整面可点击，不能只点 glyph |
| Track/Queue artwork | 42/43；Player54 | artwork 与整行选择行为分离 |
| Settings switch | 小轨道/滑块 | 整个轨道响应，沿用 SettingsToggle.hitButton |

正式已有更大的命中区域不得缩小；滑块 handle、轨道点击/拖动语义保留。Fluent 图标复用 `theme/icons.py` 和现有 assets MANIFEST，不增加平行图标库。

## F. Motion

| 类别 | 现稿 / 迁移契约 |
|---|---|
| Hover | Playback按钮颜色/背景150ms，其他家族可即时；不移动几何 |
| Selection | 即时状态反馈；不能延迟播放/选择更新 |
| Theme | 原型 applyTheme 即时换色；正式 ThemeRevealOverlay 保留既有首帧/半径修复，不强制套新统一时长 |
| Overlay | 原型主要即时出现；不凭设计补一套新动画框架 |
| Immersive controls | CSS opacity350ms；自动隐藏时机由正式控制器负责 |
| Lyrics | 原型 color200ms 只是示意；不能改变解析、position、segment、高亮时钟或滚动同步 |
| Reduce Motion | 移除非必要过渡，保留正确终态、控件唤醒与即时反馈；正式已有偏好继续生效 |

## 冻结结论

冻结的是视觉方向、层级、状态语义和家族范围；不是批准重写协调器、移植 DOM、统一所有断点或将 mock 路由当业务。本轮不进入 Phase 0，不提交 Git。
