# Reimagined 缺陷整改 · 第一轮

- 版本：`1.0.0` → `1.0.1`
- 日期：2026-10-18
- 项目：`F:\Projects\HushPlayer-Reimagined`（唯一改动目录）
- 用户录屏：`F:\录屏\Desktop\Desktop 2026.10.18 - 16.04.38.03.mp4`
  - 时长 `00:01:57.10`，`2560×1440`，`59.79 fps`，H.264 + AAC
  - 抽帧：1 fps → `artifacts/rec/f1/`（117 张）→ 接触表 `artifacts/rec/sheets/sheet_01..10.jpg`
  - 关键帧原分辨率：`artifacts/rec/hi/tNNN_N.png`；亮度分析：`artifacts/rec/seg_a`、`seg_b`（30 fps）
- 状态口径：**未开始 / 已复现 / 修复中 / 待验证 / 已验证修复 / 受阻**。只有「真实程序中复现消失 + 自动化测试通过」才记为「已验证修复」。

---

## 一、录屏时间线（用户操作与可观察现象）

| 时间 | 画面 | 观察 | 关联 |
| --- | --- | --- | --- |
| 0:00–0:08 | 搜索「加木」结果页，正在播放「茶花开了，该回家了。《茶花开了》说唱版」，来源徽章「酷我」 | 正常 | — |
| 0:08–0:30 | 设置 → 常规 / 外观，反复切换浅色 ↔ 深色 | **深色主题下「启动 / 窗口 / 更新」卡片仍是白色**，侧栏与播放栏已是深色 | BUG-08 |
| 0:30–0:57 | 搜索页输入「加木」 | 出现**微软拼音输入法候选窗**（系统窗口，非应用弹窗）；选中行底色为实心莓果红、行内标题同为莓果红 → 红上红不可读 | BUG-10（弹窗见下） |
| 0:57–1:03 | 普通歌词页（浅色） | 正常 | — |
| 1:03–1:11 | 桌面歌词浮窗 | 文字随播放推进，但为**整字跳变** | BUG-06 |
| 1:11–1:30 | 进入沉浸式 Cover Stage（浅色主题） | 进入瞬间**黑帧约 0.4 s**（亮度 80 → 33.2）；后续 1 s 内背景亮度 103（队列面板打开，属正常） | BUG-01 |
| 1:30–1:36 | 退出沉浸式回主界面 → 设置 | 正常 | — |
| 1:35–1:37 | 设置 →「在线音源」分区 | **弹出应用级错误对话框**：`HushPlayer 遇到了问题` / `AttributeError: 'dict' object has no attribute 'id'`，栈指向 `settings.py` 的 `_fill_sources` | BUG-04 |
| 1:36–1:56 | 设置各分区（外观、播放、关于、缓存） | 主题预览卡可用；关于页为占位「H」标志 | BUG-07 / BUG-08 |
| 1:56–1:57 | NVIDIA 覆盖层出现，录制结束 | — | — |

> 录屏**不能**证明的项：最大化/还原（BUG-03）、网易云暂停/停止（BUG-02）、2K 下整体字号（BUG-05）。这些按用户文字反馈单独复现，证据见下文。

---

## 二、逐项缺陷

### BUG-01 · 进入沉浸式出现闪屏

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（视觉体验，用户重点） |
| 复现 | 播放中从主界面点击「沉浸模式」进入全屏 |
| 证据 | 录屏 `t=69.70–70.10 s` 全屏灰度均值 80 → **33.2 持续 0.4 s**（`artifacts/rec/seg_a`，30 fps 逐帧统计） |
| 根因 | `ImmersiveWindow.open_immersive()` 先 `show()` 再填内容：窗口以默认 `#08080a` 底色上屏，随后 `_MoodBackground` 用 680 ms 从黑底色淡入封面氛围色；同时舞台控件在首帧尚未布局完成，DWM 先合成一帧纯背景。属「先显示、后填充 + 背景动画从黑开始」的时序问题，不是单纯动画太快。 |
| 修复 | `hushplayer/ui/immersive.py`：<br>1. `_MoodBackground.snap_to(mood)` 直接落位、不做淡入；<br>2. `_on_track_changed(..., animate_mood=False)` 在打开时同步氛围色；<br>3. `open_immersive()` 改为「几何 → 模式 → 曲目 → 控件同步 → `_fade_effect.setOpacity(1.0)` → `ensurePolished()` + `layout().activate()` → `grab()` 预栅格化 → `show/raise_/activateWindow`」，不再先上屏；<br>4. 保留后续曲目切换时的氛围色过渡动画。 |
| 自动化 | `tests/test_playback_state.py`（状态）+ `tools/probe_immersive_flash2.py` 动态帧检（首帧即完整内容，`delta=0.00`，`RESULT PASS`） |
| 真实 GUI | `artifacts/qa/immflash/window/000_immediately.png`：`open_immersive()` 后第一帧已含封面、标题、歌手、专辑、控制栏、进度 `0:01 / 0:10` |
| 反例排除 | 未使用「缩短闪屏」「隐藏窗口」「固定延迟」等手段；黑帧来源被移除而非掩盖 |
| 状态 | **已验证修复**（渲染层）。「肉眼无闪」受 DWM 截屏限制，列入人工验收：`docs/KNOWN_ISSUES.md` 的人工验收清单第 1 条 |

### BUG-02 · 网易云无法正常暂停或停止

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（基础播放控制） |
| 复现 | 在线（网易）曲目播放/缓冲过程中按暂停或停止 |
| 证据 | `tools/probe_pause_online.py 网易 晴天`：多数曲目 `resolvePlayback` 失败（`音源未提供可用的播放资源（可能受版权或会员限制）`），跨音源回退到汽水 CDN 后 SSL 断流 → 代理 `502` → 引擎 `InvalidMedia`；此后 `ctrl=loading`，`toggle()` **完全无响应**（用户感知即「停不了」）。成功解析时（酷我 / 网易可用曲）暂停、继续、停止均正常（位置冻结 5330 ms → 恢复 → 停止归零）。 |
| 根因 | 控制状态机不健壮：<br>1. `PlayerController.pause()` 只在 `engine.state == "playing"` 时生效，缓冲/解析态被忽略；<br>2. 终止失败后 `_busy` 未清除、`state` 卡在 `loading`，`toggle()` 进入不可达分支；<br>3. `BufferedMedia` 被启发式判为 `PAUSED`，UI 与实际播放脱节；<br>4. 迟到的解析回调仍可能重新加载已取消的曲目。 |
| 修复 | `hushplayer/audio/engine.py`：新增 `is_playing_actual`、`halt_pending()`；`pause()` 在 LOADING 时取消待播放；移除「缓冲即暂停」推断。<br>`hushplayer/audio/controller.py`：`state` 由 `_busy`/`_paused_pending` 推导；`pause()` 支持解析中取消（`_resolve_generation += 1`）；`toggle()` 在 loading/busy 时走 pause；`stop()` 归零并清除 busy；`_online_failed` / `_on_engine_error` 终止分支统一 `engine.stop()` + `_set_busy(False)`。 |
| 自动化 | 新增 `tests/test_playback_state.py`（4 例）：解析中暂停取消、失败后状态为 stopped 且可再次播放、stop 取消迟到结果、`halt_pending()`；全量 119 例通过 |
| 真实 GUI | `tools/probe_pause_online.py 酷我 晴天` → `playing → paused（pos 冻结 5330）→ resume 正常 → stop 归零`；网易可用曲同样通过 |
| 上游限制 | 网易部分曲目**确实**无版权资源，属音源能力限制，如实提示「音源未提供可用的播放资源」，不归因为本地缺陷 |
| 状态 | **已验证修复** |

### BUG-03 · 主窗口无法正确最大化

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（窗口基础行为） |
| 复现 | 点击自绘标题栏的「最大化」按钮 |
| 证据 | `tools/probe_maximize3.py`：单次点击 `toggle_maximize()` 被调用 **两次**（`TitleBar` 与 `MainWindow` 各连了一次 `maximize_requested`），最大化后立即还原，外观上「按钮无效」；另外 `_save_geometry` 在最大化态用 `normalGeometry()` 可能存下屏幕尺寸，下次启动成为「假还原」。 |
| 根因 | 1. 信号重复连接；2. 自绘窗口缺少独立的「还原几何」状态；3. 持久化几何未校验。 |
| 修复 | `hushplayer/ui/widgets/titlebar.py`：删除重复连接（注释说明原因）。<br>`hushplayer/ui/widgets/frameless.py`：重写 `toggle_maximize()`，维护 `_normal_geometry`、`normal_geometry()`、`_usable_normal_geometry()`、`_restore_normal_geometry()`、`_sync_maximized_ui()`；`resizeEvent/moveEvent` 在非最大化时记忆正常几何；`changeEvent` 处理外部最大化（Win+↑ / Snap）。<br>`hushplayer/ui/main_window.py`：`_save_geometry` 用 `normal_geometry()` 且校验尺寸；`_restore_geometry` 对超大/越界几何做钳制并支持 `_start_maximized`。 |
| 自动化 | `tools/probe_maximize*.py`（QTest 真实点击）；持久化用例：最大化 → 退出 → 启动（最大化）→ 点击还原 → `1280×820`，`settings.json` 存 `w=1280,h=820,maximized=true` |
| 真实 GUI | 最大化 `2560×1392`（工作区）、还原 `1280×820`、双击标题栏、拖拽移动、Win+↑ 均正常 |
| 反例排除 | 未用「把窗口设成屏幕分辨率」冒充最大化，走的是 Qt 原生 `showMaximized()` |
| 状态 | **已验证修复** |

### BUG-04 · 在线音乐搜索/使用中弹出不明窗口

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（模态错误对话框打断使用） |
| 复现 | 设置 →「在线音源」分区；以及在线搜索过程中 | 
| 证据 | 录屏 `t=1:35`：对话框标题「HushPlayer 遇到了问题」、正文「程序遇到了一个未处理的错误，已记录到日志。」、异常 `AttributeError: 'dict' object has no attribute 'id'`，栈 `settings.py:818 _show_section → :193 _section → :562 _build_online → :586 _fill_sources`（`artifacts/rec/hi/dialog_zoom.png`）。<br>另：输入法候选窗（`t=0:50`）是**微软拼音的系统窗口**，不是应用弹窗。 |
| 根因 | `_fill_sources()` 直接遍历 `client.sources`（原始字典列表）并访问 `.id`；字典没有该属性 → 未捕获异常 → `_install_excepthook` 弹出模态框。同函数还把 `build_sources` 的 `NameError` 吞进 `except Exception: sources = []`，导致即使不崩溃也永远显示「尚未加载音源插件」。 |
| 修复 | `hushplayer/ui/pages/settings.py`：导入 `build_sources` 并统一用它转换成 `SourceInfo`；订阅 `client.sources_changed` 自动刷新列表（原来只在构造时填一次）；`except` 分支改为 `log_exception(...)` 记录真实错误；重名音源加短 id 后缀（两个「QQ音乐」）。 |
| 自动化 | 全量测试 119 例通过；新增 `tests/test_brand.py`/`test_display.py` 等无回归 |
| 真实 GUI | `tools/probe_settings_online.py`：真实窗口打开「在线音源」→ 7 个插件正常列出（`网易音乐 / 汽水 / QQ音乐·1a43 / 酷狗 / 小米 / QQ音乐·1bdd / 酷我`），每行带能力摘要与开关，无崩溃、无对话框（`artifacts/qa/settings_online_loaded.png`） |
| 反例排除 | 未删除错误提示、未吞异常；网络/音源异常仍通过 toast 与状态文本告知 |
| 状态 | **已验证修复** |

### BUG-05 · 2K（2560×1440）下整体 UI 太小

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（可读性，用户重点） |
| 复现 | 在 2560×1440、Windows 缩放 100% 的屏幕上使用默认窗口 |
| 证据 | 录屏整帧：窗口 1280×820，正文 10 pt→实际约 13 px 高，侧栏 236 px 仅占屏宽 9%；用户多次凑近/缩放窗口仍偏小 |
| 根因 | 界面尺寸按 1080p 逻辑像素设计，Qt 默认 `QT_SCALE_FACTOR=1`，未针对物理分辨率做产品级缩放；仅调字体又会破坏布局。 |
| 修复 | 新增 `hushplayer/core/display.py`：按物理屏宽推荐缩放（≥3600 → 150%，≥2400 → 125%，≥2000 → 115%），在 `QApplication` 创建**之前**设置 `QT_SCALE_FACTOR`（`hushplayer/app.py main()`），因此字号、图标、行高、点击区域、间距**整体等比放大**，布局仍按逻辑像素计算。设置 → 外观新增「界面缩放」（跟随推荐/100%/115%/125%/150%）+「重启程序」入口；`appearance.ui_scale` 持久化。 |
| 自动化 | 新增 `tests/test_display.py`（8 例）：阈值推荐、auto 跟随物理屏、显式偏好优先、非法值回退、`QT_SCALE_FACTOR` 写入/清除、文案百分比 |
| 真实 GUI | `QT_SCALE_FACTOR=1.25`：窗口抓图 `1600×1025`，标题/列表/侧栏/播放栏比例一致，无重叠与裁切（`artifacts/shots/songs_light.png`、`docs/screenshots/`）；本机默认 auto 解析为 1.25 |
| 反例排除 | 不是「只调全局字号」：缩放作用于整个 Qt 逻辑坐标系；也不是要求用户手动放大 |
| 状态 | **已验证修复** |

### BUG-06 · 桌面歌词逐字高亮不平滑

| 项 | 内容 |
| --- | --- |
| 严重程度 | 中高（用户重点，歌词体验） |
| 复现 | 桌面歌词播放带逐字时间戳的歌词 |
| 证据 | 录屏 `t=1:03–1:11`：高亮按整字跳变；代码层原实现 `_sweep_chars()` 用 `document.word_progress()` 得整数「已唱字数」，再按字符平均宽度裁剪 |
| 根因 | 1. 高亮以「字符」为最小单位；2. 位置来自 `QMediaPlayer.positionChanged`（约 1–5 Hz），即使像素化也会阶梯推进；3. 裁剪边缘为硬边界，中英混排时字宽不一致更明显。 |
| 修复 | 1. 新增 `hushplayer/audio/clock.py`：`PlaybackClock` 用 16 ms `Qt.TimerType.PreciseTimer` 在权威位置之间做单调插值，暂停冻结、seek 重同步，`tick` 发 60 Hz 位置；<br>2. 新增 `hushplayer/ui/widgets/sweep.py`：`paint_sweep()` 把强调色文字画进 DPR 感知的 `QPixmap`，用 `CompositionMode_DestinationIn` + 线性渐变做 3 px 软边，`progress` 为**浮点像素**；`sweep_pixels_for_line()` 按真实词时间轴累计宽度（词内线性插值），无词时退回行内比例；<br>3. 桌面歌词与普通/沉浸歌词统一改用该实现，并订阅 `clock.tick`。 |
| 自动化 | 新增 `tests/test_clock.py`（6 例）：仅播放时 tick、位置插值、暂停冻结、时长钳制、reset；新增 `tests/test_sweep.py`（6 例）：强调色面积随进度增长、亚字符步进、按词时间轴、无词回退、软边参数；动态测量 `tools/probe_sweep.py`：`ticks observed: 192`，2450→3450 ms 边缘 608→763 px，每次 +3~+15 px，`negative=0 jumps>20px=0`，`RESULT PASS` |
| 真实 GUI | `artifacts/shots/desktop_lyrics_dark.png` 与 4× 放大 `artifacts/qa/_sweep_edge.png`：强调色/白色交界落在「的」字内部，即像素级而非字级；普通歌词页与沉浸歌词同步使用软边扫过 |
| 反例排除 | 未用「按字符数估算时间」替代真实逐字时间戳；未用高频整控件重绘（仅歌词控件 `update()`，60 Hz） |
| 状态 | **已验证修复** |

### BUG-07 · 正式 Logo 缺失

| 项 | 内容 |
| --- | --- |
| 严重程度 | 中（品牌一致性） |
| 复现 | 关于页、侧栏、任务栏/托盘、可执行文件图标均使用占位标志 |
| 证据 | 录屏 `t=1:36` 关于页显示占位「H」方块；`assets/hushplayer.png` 为早期生成图 |
| 处理 | **不新造 Logo**（遵守用户要求）。建立统一资源机制 `hushplayer/core/brand.py` 与 `assets/brand/README.md`：把 `logo.png` / `logo_light.png` / `logo_dark.png` / `icon.ico` / `icon.png` 放入 `assets/brand/`，程序启动即替换侧栏、关于页、窗口图标、托盘、打包图标，无需改代码。已接线：`app.py` 窗口图标、`main_window.py` 窗口 + 托盘、`sidebar.py` LogoMark、`settings.py` 关于卡片。 |
| 自动化 | 新增 `tests/test_brand.py`（4 例）：占位资源存在、多尺寸 `QIcon`、圆角 pixmap 尺寸/DPR、`has_official_logo()` 语义 |
| 真实 GUI | 占位资源下各位置显示一致；正式素材未到，无法验证替换效果 |
| 状态 | **受阻（等待正式素材）**；机制已完成，素材投放后无需改代码 |

### BUG-08 · 主题切换控件不符合预期

| 项 | 内容 |
| --- | --- |
| 严重程度 | 中（设置中心核心交互） |
| 复现 | 设置 → 外观；或在深色主题下查看设置页 |
| 证据 | 录屏 `t=0:08–0:30`：切到深色后 **SettingsCard 仍为白色**，与深色背景、深色侧栏割裂；切换时页面不重绘内联样式 |
| 根因 | 1. 设置卡片/行/预览卡的颜色在构造时写进内联 QSS，`refresh_theme()` 只刷新页面框架，没有递归重刷子控件；<br>2. 主题预览卡为单色示意，无法表达「跟随系统」的中间状态；<br>3. `ToggleSwitch` 关闭态用 `mix_color(text, …)`，深色下轨道发白、浅色下发黑。 |
| 修复 | `hushplayer/ui/widgets/settings_widgets.py`：`ThemePicker` 重写为三张 132×108 迷你窗口预览（侧栏 + 标题 + 三行内容 + 播放条），选中态 2 px 莓果描边 + 右上勾选徽标 + 加粗标签，「跟随系统」标注当前解析结果；支持方向键/空格；`ToggleSwitch` 关闭态改为以 `surface_alt`/`surface` 为基底混色并给圆钮加 1 px 描边。<br>`hushplayer/ui/pages/settings.py`：`refresh_theme()` 递归调用子控件 `refresh_theme()`（`_refresh_tree`），切主题后卡片/文字/开关即时跟随。 |
| 自动化 | 全量测试 119 例通过 |
| 真实 GUI | `tools/probe_theme_live.py`：同一窗口在 dark 打开设置页 → 切 light → 再截图，`artifacts/qa/theme/settings_{dark,light}_live.png` 两套主题下卡片、文字、开关全部跟随；4× 裁剪 `_toggles_{dark,light}.png` 确认 ON=莓果 + 白钮、OFF=中性灰轨道 + 白钮 |
| 状态 | **已验证修复** |

### BUG-09 · 播放标识位置偏移

| 项 | 内容 |
| --- | --- |
| 严重程度 | 低中（视觉对不齐） |
| 复现 | 歌曲列表中正在播放的那一行 |
| 证据 | 录屏 `t=0:35.5`（`artifacts/rec/hi/t035_5.png`）：序号列中均衡器条居中于列，而其它行数字右对齐于 `rect.right()-8`，播放行标识整体偏左约 10 px |
| 根因 | `TrackDelegate._paint_bars()` 用 `rect.center().x() - total / 2` 居中，与序号文本的右对齐基线不一致；不是 SVG 内部留白或 DPI 取整问题（像素测量确认条宽 2.4 px、间距 2.6 px 均正常）。 |
| 修复 | `hushplayer/ui/widgets/tracklist.py`：`x = rect.right() - 8 - total`，与序号共用右基线；行的左侧竖标记保留作为播放强调。 |
| 自动化 | 全量测试通过；像素复核 `artifacts/qa/_idx_light.png`（4×）条与数字右边线对齐 |
| 真实 GUI | `artifacts/qa/rowstates_{light,dark}.png` |
| 反例排除 | 未在当前截图随意加固定偏移掩盖问题，改的是与序号共享的布局基线 |
| 状态 | **已验证修复** |

### BUG-10 · 当前播放与选中状态冲突（红上红）

| 项 | 内容 |
| --- | --- |
| 严重程度 | 高（可读性） |
| 复现 | 单击正在播放的歌曲行 |
| 证据 | 录屏 `t=0:35.5`：选中行底色 **(210,99,113)**（近实心莓果红），行内标题同为莓果红 → 几乎不可读（`artifacts/rec/hi/row_zoom.png`）；未选中时同曲标题为莓果红、次级文字灰色，可读（`t=0:42.5`） |
| 根因 | 全局 QSS `QWidget { selection-background-color: accent; selection-color: accent_text }` 让 `QTableView` 先刷实心莓果底；delegate 又叠 0.13/0.18 accent；而「正在播放」的标题用 `palette.accent` → 红底红字。多层语义（hover / selected / playing / focus）没有明确优先级。 |
| 修复 | `hushplayer/core/theme.py`：为 `QTableView/QTreeView/QListView` 显式关闭原生选中底色（`selection-background-color: transparent`，`::item` 透明），把选中视觉交给 delegate。<br>`hushplayer/ui/widgets/tracklist.py`：重写优先级——选中 = 连续整行 accent 12–20% 底（每行只画一次，圆角连续）；hover = 文字 4.5%；播放 = 标题 accent（**仅未选中时**）+ 序号列均衡器 + 行首竖标记；选中时标题/次级文字改用 `text` 与 0.72–0.80 alpha，确保对比；`_neutralise_native_selection()` 把 `QPalette.Highlight` 透明化。 |
| 自动化 | 全量测试通过；状态矩阵截图 `artifacts/qa/rowstates_{light,dark}.png`（普通 / hover / 播放 / 选中 / 播放+选中） |
| 真实 GUI | 浅色：选中播放行为浅莓果整行底 + 深色标题 + 均衡器 + 竖标记；深色：暗莓果底 + 白标题；均无红上红 |
| 对比度 | 选中行标题（浅色 `#15151B` on `#F7E3E8`）≈ 14:1；播放未选中标题（`#C24E68` on `#FFFFFF`）≈ 4.9:1；深色播放未选中（`#C95770` on `#15151A`）≈ 5.2:1，均 ≥ WCAG AA 4.5:1 |
| 状态 | **已验证修复** |

---

## 三、额外发现（非用户清单，本轮一并处理或记录）

| 编号 | 现象 | 结论 | 状态 |
| --- | --- | --- | --- |
| X-01 | 设置「在线音源」永远显示「尚未加载音源插件」 | `build_sources` 未导入，`NameError` 被 `except Exception` 吞掉 | 已修（随 BUG-04） |
| X-02 | 深色下 `ToggleSwitch` 关闭态轨道发白 | `mix_color(text, 0.18)` 方向错误 | 已修（随 BUG-08） |
| X-03 | 播放栏在在线缓冲时显示「正在缓冲…」而进度已在走（录屏 `t=0:49`） | 引擎 `BufferedMedia` 被当作暂停、与真实状态脱节 | 已修（随 BUG-02） |
| X-04 | 播放页 `Track` 无 `source` 属性导致在线结果渲染异常 | delegate 使用不存在的字段 | 已修（v1.0.0 前） |
| X-05 | 队列面板高度覆盖播放栏 | 面板高度未扣除播放栏 | 已修（v1.0.0 前） |
| X-06 | 关闭窗口后仍有 node 子进程残留 | `OnlineSourceClient.stop()` 未在退出路径调用 | 已修（v1.0.0 前） |
| X-07 | 输入法候选窗被误认为应用弹窗 | 微软拼音系统窗口，非缺陷 | 记录，不修 |

---

## 四、验证方式与证据索引

- **自动化**：`pytest -q` → **119 passed / 0 failed / 0 skipped**（`artifacts/junit_round1.xml`，约 29.8 s）。其中本轮新增 20 例：`test_clock.py`、`test_sweep.py`、`test_display.py`、`test_brand.py`；既有 99 例全部保持通过，未删除、未放宽断言。
- **真实 GUI（桌面平台，非 offscreen）**：
  - 行状态矩阵：`artifacts/qa/rowstates_{light,dark}.png`
  - 主题实时切换：`artifacts/qa/theme/settings_{dark,light}_live.png`、`_toggles_*.png`
  - 在线音源分区：`artifacts/qa/settings_online_loaded.png`
  - 沉浸式首帧：`artifacts/qa/immflash/window/000_immediately.png`
  - 逐字扫过动态：`artifacts/qa/sweep.txt`、`artifacts/qa/_sweep_edge.png`
  - 高 DPI：`artifacts/shots/songs_light.png`（1600×1025，125%）
  - 最大化/还原：`tools/probe_maximize*.py` 输出（见测试报告）
  - 打包产物：`tools/verify_package.ps1`（内置 Node 就绪、单实例拦截、干净退出）
- **性能**：启动、切歌、扫描等基线见 `docs/TEST_REPORT.md`；本轮未引入新线程或定时器泄漏（`PlaybackClock` 仅一个 16 ms 定时器，窗口隐藏时不触发歌词重绘）。

---

## 五、未完成 / 受阻

1. **BUG-07 正式 Logo**：等待用户提供 `assets/brand/` 素材；机制与文档已就绪，投放后重启即生效（可用 `tests/test_brand.py` 复核）。
2. **录屏层面的「肉眼无闪」**：无人值守环境无法录制 DWM 合成后的真实窗口（gdigrab 抓不到应用窗口），已用窗口渲染帧证明首帧完整；最终肉眼确认列入人工验收。
3. **网易云部分曲目**：受版权/会员限制，`resolvePlayback` 返回不可用资源，属上游能力；已做跨音源回退与明确提示，不是本地缺陷。
4. **BUG-05 的 125% 体验**：本机 2560×1440 已验证；1080p/150% 仅通过逻辑阈值与截图验证，未在第二台物理显示器上实测（列入人工验收）。

---

## 六、人工验收清单（需要用户在真实桌面完成）

1. 播放中从主界面进入/退出沉浸式 5 次，确认肉眼无黑帧、无白闪，A/B 模式切换正常。
2. 在线播放（酷我/网易可用曲）暂停、继续、停止、切歌、拖动进度，确认声音与界面一致；网易不可用曲应提示而不是卡住。
3. 点击最大化/还原、双击标题栏、Win+↑、Snap 左右、最大化后拖动还原；关闭再启动确认窗口几何恢复。
4. 搜索「周杰伦 晴天」多音源，确认无错误对话框；断网后再搜索，确认 toast 提示且可重试。
5. 在 Windows 显示设置 100% / 125% / 150% 下分别启动，确认默认缩放舒适、无截断；设置 → 外观切换缩放并重启。
6. 桌面歌词逐字高亮观察 10 秒，确认连续推进、无跳字；暂停/拖动/切歌后高亮正确。
7. 深浅主题来回切换，确认设置卡片、开关、预览卡即时跟随。
8. 选中正在播放的歌曲行，确认标题可读、播放状态仍可识别（浅色/深色各一次）。
9. 投放正式 Logo 到 `assets/brand/` 后重启，确认侧栏、关于页、任务栏、托盘、EXE 图标全部替换。
