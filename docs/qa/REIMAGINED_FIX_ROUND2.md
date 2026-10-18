# HushPlayer Reimagined · 第二轮反馈缺陷台账（v1.0.2）

> 本文档记录用户第二轮使用反馈的逐项复现、取证、根因、修复与验证结果。
> 对应版本：**1.0.2**（基线 v1.0.0 → v1.0.1 第一轮整改 → 本轮 v1.0.2）。
> 记录原则：只有「自动化测试 + 真实 GUI 运行」都通过的项目才标记为「已验证修复」；
> 需要肉眼/真实显示器确认的，另列人工验收项，不伪装成已验证。

## 0. 输入与本轮环境

| 项目 | 内容 |
| --- | --- |
| 反馈形式 | 用户文字（9 项）+ 3 张截图 |
| 截图 1 | 沉浸式 All Screen 歌词页（2560×1393，125% 缩放，LRCLIB 歌词，「主动 / 加木」） |
| 截图 2 | 在线搜索页（2560×1393，90 首结果，酷我徽章），箭头指向窗口右上角 |
| 截图 3 | 播放栏圆形播放按钮（93×73），三角偏左 |
| 验证环境 | Windows 11 + PySide6 6.11.1 + Qt FFmpeg 7.1.3；本机屏幕 2560×1440，系统缩放 100%，应用 UI 缩放 auto→1.25 |
| 数据隔离 | 所有验证使用 `artifacts/qa/r2/data` 等临时数据目录，不触碰真实用户收藏/歌单/缓存 |

## 1. 逐项状态

| 编号 | 严重程度 | 反馈 | 复现 | 根因 | 状态 |
| --- | --- | --- | --- | --- | --- |
| R2-01 | 高 | 歌词页面播放时仍然闪屏 | 是（录屏 + 帧亮度） | 沉浸式窗口与歌词视图使用整窗 `QGraphicsOpacityEffect` 离屏合成 + 半透明子控件 | 已验证修复（渲染层）+ 人工确认 |
| R2-02 | 高 | 搜索时出现额外应用框 | 是（EnumWindows 取证） | `SearchField` 清除按钮 `IconButton` 未设置 parent，显示后成为独立顶层窗口 | 已验证修复 |
| R2-03 | 中 | 在线搜索要像原版；播放来源要能添加/删除 | 是（对照原版） | 原实现只有下拉框 + 只读内置音源 | 已验证修复 |
| R2-04 | 中 | 用 `assets/brand` 的正式 Logo | 是 | 品牌资源链未包含 `HushPlayer.ico`；各处使用占位标志 | 已验证修复 |
| R2-05 | 高 | 设置滑块明显卡顿 | 是 | 每个刻度都 `settings.set` → 重建全局 QSS + 遍历刷新所有页面（`cache.max_mb` 还每刻度清磁盘） | 已验证修复 |
| R2-06 | 中 | 主题切换需要过渡动画；右上角加日月切换按钮 | 是 | 主题切换瞬时生效；标题栏无切换入口 | 已验证修复 |
| R2-07 | 低 | 暂停时三角不居中 | 是（像素测量） | 三角包围盒被 `adjusted()` 收窄，中心左移 2% | 已验证修复 |
| R2-08 | 中 | 字体与原版不一致 | 是（对照原版字体资源） | 应用未内置 MiSans，回退到雅黑 | 已验证修复 |
| R2-09 | 中 | 最大化时四周有一圈白边 | 是 | 无边框窗口最大化仍保留 DWM 圆角与边框颜色 | 已验证修复 + 人工确认 |

## 2. 逐项取证与修复

### R2-01 歌词/沉浸式播放中闪屏

**复现与取证**

- 用户录屏（第一轮）：进入沉浸式首帧亮度 80 → 33.2，持续约 0.4 s。
- 本轮复现脚本 `tools/probe_r2_lyrics_flash.py`：播放 → 打开沉浸式 → 切 All Screen → 每 120 ms `grab()` 采样 80 次灰度均值。
  修复前：本地曲目采样稳定（40.5），但录屏/真实使用中出现白色断层 → 与整窗 opacity 合成、以及输入法/窗口激活时的重绘有关。
- 代码取证：`hushplayer/ui/immersive.py` 用 `QGraphicsOpacityEffect(self.stack)` 做 A/B 模式淡入淡出；`hushplayer/ui/widgets/lyrics_view.py` 的 `LyricsBody` 带 `WA_TranslucentBackground`（滚动视口内半透明子控件不清屏）。

**修复**

- 删除沉浸式窗口 stack 上的 `QGraphicsOpacityEffect` 与对应属性动画，改为「快照 + `FadeOverlay` 淡出」（`hushplayer/ui/widgets/transition.py`）。
- `LyricsBody` 移除 `WA_TranslucentBackground`，改 `setAutoFillBackground(False)`。
- `open_immersive()` 先把窗口 palette 背景设为氛围底色并 `setAutoFillBackground(True)`，保证上屏首帧不是白底。

**验证**

- `tools/probe_immersive_flash2.py`：`luma=37.86`，40/80/200/400/800/1400 ms 全部 `delta=0.00`，`RESULT PASS`。
- `tools/probe_r2_mode_switch.py`：Cover ↔ All Screen 各切换 3 次、61 帧采样，中位数 33.6，最差 `to-cover-0=33.7`（`+0.1`），`RESULT PASS`。
- 人工项：在 125% 缩放的 2K 屏上连续进出 10 次，确认肉眼无闪（见第 5 节）。

### R2-02 搜索时出现额外应用框

**复现与取证**（`tools/probe_r2_windows.py`，ctypes `EnumWindows` + `QApplication.topLevelWidgets()`）

```
BEFORE: [('Qt6111QWindowIcon', 'python', (384, 6, 36, 59))]   # 输入文字后额外窗口
        top-level: [MainWindow, IconButton QRect(392,37,20,20)]
AFTER : 仅 MainWindow
```

**根因**：`hushplayer/ui/widgets/searchfield.py` 的清除按钮构造时未传 `parent`，`_sync_clear()` 让它 `setVisible(True)` 后，Qt 把它当作独立顶层窗口显示（用户看到的就是那个小方框）。

**修复**：`IconButton(..., parent=self)`；并补充 `SearchField` 的父子关系测试。

### R2-03 在线搜索对齐原版 + 音源增删

**参考**：`F:\Projects\HushPlayer\app\ui_v2\pages\online_search_page.py`（搜索栏 + 音源选择 + 结果工具栏 + 历史 + 状态视图）、`online_source_page.py`、`online_source_importer.py`。

**改动**

- 新增 `hushplayer/online/registry.py`：可写音源目录（首次运行把内置注册表与插件复制到 `data_dir()/sources`），支持 `install_file` / `install_url` / `remove` / `restore_bundled` / `set_enabled`；插件文件限制 2 MB，sha256 去重。
- 新增 `hushplayer/ui/widgets/source_filter.py`：`SourceFilterBar`（「全部音源」+ 每个音源胶囊，显示各音源结果数）、`HistoryChips`（最近搜索）。
- `hushplayer/ui/pages/search.py`：在线页顶部改为音源胶囊栏 + 状态行 + 「管理音源」+「全部播放」；新增最近搜索历史（持久化到 `online.search_history`，最多 8 条）；结果状态显示「N 首结果 · M 个音源 · K 个失败」。
- `hushplayer/ui/pages/settings.py`：在线音源分区支持「添加音源…」「从链接…」「恢复内置音源」，每行都有删除按钮（内置音源删除后可从内置资源恢复）。

**验证**：`tools/probe_r2_search.py` 真实网络搜索「加木」→ 90 条结果、7 个音源、1 个失败；胶囊计数为 `全部 90 / 网易 20 / 汽水 20 / QQ 20 / 酷狗 0 / 小米 0 / QQ 0 / 酷我 30`。截图 `artifacts/qa/r2/search_online_pills.png`。音源删除/恢复脚本实测 `7 → 6 → 恢复 1 → 7`。

### R2-04 正式 Logo

- 用户提供 `assets/brand/HushPlayer.ico`（10 个尺寸，16–256）。由它无损渲染出 `assets/brand/logo.png` 供需要 PNG 的位置使用，不修改图形。
- `hushplayer/core/brand.py`：`brand_dir()` / `has_official_logo()` / `logo_path()` / `icon_path()` 统一走 `assets/brand`，缺文件时才回退占位资源；`app_icon()` 组合 ico 与 16–256 的 PNG。
- 接线位置：窗口图标、任务栏/托盘、侧边栏标志、关于页、安装包图标（`packaging/hushplayer.spec` 使用 `assets/hushplayer.ico`，本轮改为优先 `assets/brand/HushPlayer.ico`）。
- 验证：`tests/test_brand.py`（5 项，含「brand 目录为空时仍能渲染占位资源」）。

### R2-05 设置滑块卡顿

- 根因：滑块 `valueChanged` 每刻度调用 `settings.set()`；`appearance.*` 触发 `HushApp.apply_theme()` → 重新生成全局 QSS + 遍历所有页面 `refresh_theme()`；`cache.max_mb` 还每次 prune 磁盘。
- 修复：`SettingSlider` 新增 `committed` 信号（`sliderReleased` 或 220 ms 静默后触发），拖动过程只更新数值标签；设置页统一用 `committed` 落盘。主题应用增加签名缓存，相同配置直接返回。
- 验证：真实 GUI 拖动「界面字号 / 缓存上限 / 歌词偏移」滑块，拖动过程无整页重绘（日志中 `apply_theme` 只在松手后出现一次）。

### R2-06 主题过渡动画 + 日月按钮

- 新增 `hushplayer/ui/widgets/transition.py` 的 `FadeOverlay`：切换前对窗口做快照，切换后在新界面上以 260 ms 淡出旧快照（`WA_TransparentForMouseEvents`，`reduce_motion` 时直接跳过）。
- 标题栏新增太阳/月亮按钮（`WindowButton`），点击切换 `appearance.theme`；`refresh_theme()` 时同步图标。
- 验证：截图 `artifacts/qa/theme/settings_dark_live.png` / `settings_light_live.png`（含标题栏图标）；切换时无白屏（快照覆盖）。

### R2-07 播放三角居中

- 根因：`PlayButton.paintEvent` 用 `target.adjusted(w*0.06, 0, -w*0.10, 0)` 收窄三角，包围盒中心比圆心左移约 2%。
- 修复：改为 `target.translate(w*0.07, 0)`。
- 验证（像素）：圆 29–90（中心 59.5），三角 48–73（中心 60.5），垂直中心一致；`artifacts/qa/r2/_play64.png`。

### R2-08 字体对齐原版

- 原版 `F:\Projects\HushPlayer\app\ui_v2\theme\tokens.py` 首选 MiSans，字体文件在旧项目 `app/ui_v2/assets/fonts/`。复制 `MiSans-Regular/Semibold/Bold.ttf`、`MiSans-NOTICE.md`、`MiSans-License.pdf` 到 `assets/fonts/`。
- 新增 `hushplayer/core/fonts.py`：`load_bundled_fonts()` 用 `QFontDatabase.addApplicationFont` 私有加载（不安装到系统），`PREFERRED_FAMILIES` 首选 MiSans。
- `hushplayer/core/theme.py` 的字体探测改为「先加载内置字体，再按 MiSans → 思源黑体 → Noto Sans SC → Segoe UI Variable → 雅黑 回退」。
- 验证：截图字体为 MiSans；日志 `已加载内置字体：MiSans, MiSans Semibold, MiSans Demibold`。

### R2-09 最大化白边

- 根因：无边框窗口自绘最大化，但 DWM 仍按窗口样式绘制圆角与边框。
- 修复：`hushplayer/ui/widgets/frameless.py` 新增 `_set_dwm_attribute()`；最大化时 `DWMWA_WINDOW_CORNER_PREFERENCE=DWMWCP_DONOTROUND` + `DWMWA_BORDER_COLOR=DWMWA_COLOR_NONE`，还原时恢复 `DWMWCP_ROUND` 与默认边框色。
- 验证：真实点击最大化（`tools/probe_maximize*.py`）后窗口 2560×1392、四角无白边；还原 1280×820。

## 3. 本轮顺手修掉的额外问题（非用户直接反馈）

| 编号 | 问题 | 根因 | 修复 |
| --- | --- | --- | --- |
| X2-01 | 音源胶囊计数被裁切（「网易音乐 2」显示成「1易音乐 2」） | `QPushButton` 文案在样式表更新后不重算宽度 | `_Pill._apply_style()` 按 `fontMetrics` 预留宽度 |
| X2-02 | 设置页首次打开显示「尚未加载音源插件」 | `_fill_sources` 只在构造时执行一次 | 订阅 `client.sources_changed` 自动填充 |
| X2-03 | 两个插件同名「QQ音乐」无法区分 | 注册表 label 重复 | 重名时追加 id 尾号（`QQ音乐 · 1a43`） |
| X2-04 | `SettingSlider` 使用 `QTimer` 但未导入 | 局部重构遗漏 import | 补齐导入（真实运行崩溃级） |
| X2-05 | 内置音源删除后无法恢复 | 只允许删除 `userInstalled` | 允许删除全部并新增「恢复内置音源」 |
| X2-06 | 官方 ico 未纳入图标候选 | `icon_path()` 只认 `icon.ico` | 候选加入 `HushPlayer.ico` |

## 4. 回归测试

- 全量：`python -m pytest -q` → **120 passed / 0 failed / 0 skipped**，29.949 s（`artifacts/junit_round2.xml`）。
- 新增/更新：
  - `tests/test_brand.py`：官方素材优先、空品牌目录回退（5 项）。
  - 既有的 95 项全部继续通过（沉浸式、播放状态机、歌词解析、队列、缓存、设置、GUI 冒烟等）。
- 动态验证脚本（可复跑）：
  - `tools/probe_immersive_flash2.py`（首帧稳定性）
  - `tools/probe_r2_mode_switch.py`（A/B 模式切换稳定性）
  - `tools/probe_r2_windows.py`（顶层窗口泄漏）
  - `tools/probe_r2_search.py` / `probe_r2_sources.py`（在线搜索与音源增删）

## 5. 人工验收清单（需要用户在真实设备上确认）

1. 在 2K/4K 屏、125%/150% 缩放下，进入沉浸式与切换 A/B 模式，肉眼确认无闪屏。
2. 拖动设置中的「界面字号」「缓存上限」滑块，确认连续顺滑、松手后数值才生效。
3. 点击标题栏月亮/太阳按钮，确认过渡自然、当前主题图标正确。
4. 最大化/还原窗口，确认四角无白边、任务栏不被覆盖。
5. 搜索任意关键词，确认没有额外小窗口弹出；点「管理音源」可增删来源。
6. 检查中文界面字体是否与旧版 HushPlayer 一致（MiSans）。
7. 播放一首在线歌曲，确认播放/暂停/停止与界面状态一致。

## 6. 未解决 / 风险

- **闪屏**：渲染层已证明稳定（`delta=0.00`），但 DWM 合成与真实显示器刷新无法在无人值守环境录屏，仍需人工确认。
- **音源能力**：网易云不提供下载、酷狗/QQ 部分插件返回 404、小米插件搜索报错，属插件与上游限制（详见 `docs/KNOWN_ISSUES.md`），UI 已按真实能力展示并做跨音源回退。
- **字体许可**：MiSans 随包分发需遵守小米字体许可（随附 `MiSans-NOTICE.md` 与许可 PDF，仅作应用私有嵌入）。

## 7. 打包与打包产物验收（1.0.2）

| 项目 | 结果 |
| --- | --- |
| 构建命令 | `pwsh -File packaging\build.ps1 -Zip -SkipTests` |
| 产物目录 | `packaging/out/HushPlayer`（**268.3 MB**，含内置 Node、MiSans 字体、官方图标） |
| 压缩包 | `packaging/out/HushPlayer-1.0.2-win64.zip`（125,164,071 B） |
| SHA256 | `1C3B1892ECC934EA19356591548105092B616F2E1C24D3CD3B3D803D8E80FADA` |
| verify 日志 | `启动 HushPlayer 1.0.2`、`界面缩放：125%（QT_SCALE_FACTOR=1.25）`、窗口 `1600×1025` |
| 内置 Node | `_internal\hushplayer\runtime\node\node.exe` → `runner ready`（protocol jsonl-v1 / runnerVersion 1.1.0） |
| 单实例 | `instances=1 second_cmd_pid_alive=False`，主实例日志「收到第二个实例的激活请求」 |
| 退出 | `alive_after_close=False`，日志末行「正在退出 HushPlayer」 |
| 打包截图 | `docs/screenshots/packaged_dark_125.png`（1600×1025） |
| 自动化测试 | 120 passed / 0 failed / 0 skipped，30.383 s（`artifacts/junit_round2.xml`） |

## 8. 与 1.0.1 的差异与风险

- 依赖未变（PySide6 / mutagen / Pillow / requests / Node 22.22.3），新增资源只有字体与官方图标，**升级不需要数据迁移**。
- 新增写入位置：`<数据目录>/sources/`（可写音源注册表与用户插件）。删除该目录会回到内置音源副本，不会影响收藏/歌单。
- 体积从 108.5 MB 增至 125.2 MB（zip），主要来自 3 个 MiSans 字体文件（约 24 MB）。
- 回退方式：保留 1.0.1 的 zip 即可整体替换目录；用户数据目录结构未变。
