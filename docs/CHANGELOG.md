# Changelog

## v1.0.9 — 2026-10-19

新增：批量导入音源插件。

### 新增
- 设置 → 在线音源 → 「添加音源…」现在支持**多选** `.js / .json` 插件。
- 新增「批量导入 / 选择文件夹…」：扫描所选文件夹（不递归子目录，自动跳过 `node_modules`），一次性安装全部插件。
- `SourceRegistry.install_many()` + `InstallReport`：逐个安装、重复与失败分别统计，单个文件出错不会中断整批。
- 导入结束后提示「已安装 N 个音源，跳过 M 个重复，失败 K 个」；有失败时用对话框列出文件名与原因。

### 验证
- `tests/test_source_registry.py` 新增：`collect_plugin_files`、批量安装（含重复与坏文件）。
- 真实 GUI：`tools/probe_r9_batch.py` 扫描含 3 个插件 + 1 个 txt 的文件夹，安装 2 个、跳过 1 个重复；
  截图 `docs/screenshots/settings_batch_import.png`。
- 打包 1.0.9：`packaging/out/HushPlayer-1.0.9-win64.zip`。

## v1.0.8 — 2026-10-19

第七轮反馈：设置 → 在线音源 → 「添加音源…」报错。

### 修复
- `hushplayer/ui/pages/settings.py` 使用了 `QFileDialog` 却没有导入，点击「添加音源…」直接
  `NameError: name 'QFileDialog' is not defined`（异常在按钮槽中，被 excepthook 弹窗）。
  现在统一在文件顶部导入 `QFileDialog / QInputDialog / QMessageBox`。
- 安装逻辑抽成 `_install_source_file(path)`，文件选择与「从链接添加」共用同一套错误处理与刷新流程。
- `hushplayer/online/registry.py`：新增 `peek_plugin_metadata()`，安装 MusicFree 插件时**不执行插件代码**，
  只从文件头部解析 `platform / version / author` 字面量，用它作为显示名与版本；解析不到时回退文件名。
- 安装后会立即刷新音源列表并提示「已安装音源：<名称>」。

### 验证
- 新增 `tests/test_source_registry.py`（元数据解析、安装/去重/删除、拒绝错误类型与超大文件）。
- 真实 GUI 探针 `tools/probe_r8_source.py`：安装一个 MusicFree 风格插件 → 列表出现「本地测试源」→
  通过运行时 `search()` 返回 1 条结果，`errors 0`，截图 `docs/screenshots/settings_installed_source.png`。
- 打包 1.0.8：`packaging/out/HushPlayer-1.0.8-win64.zip`。

## v1.0.7 — 2026-10-19

第六轮反馈：点击「喜欢」按钮弹出未处理异常。

### 修复
- `TrackListWidget`（页面实际嵌入的复合控件）缺少 `ensure_current_visible` 透传方法，`FavoritesPage._sync_current()` 在**播放中**刷新时会抛 `AttributeError`；异常发生在 Qt 定时器槽里，于是表现为「点喜欢弹出 HushPlayer 遇到了问题」。
- 补齐透传，并审计了所有页面对 `self.list.*` 的调用，确认没有其它缺失方法。
- 新增 `tests/test_gui_smoke.py::test_favorite_heart_does_not_break_favorites_page`：导入夹具、播放、切换到「我喜欢」、点喜欢并强制同步，断言没有经 `sys.excepthook` 泄漏的异常且列表出现该曲目。
- 单实例测试改为按 `HUSHPLAYER_MUTEX_SUFFIX` 隔离互斥体：用户开着正式版时跑测试不再互相干扰；`tools/verify_package.ps1` 同样使用隔离后缀，并且只操作自己启动的进程（不再结束用户正在运行的窗口）。

## v1.0.6 — 2026-10-19

第五轮反馈：歌词偏移调整时，歌词会先跳到顶端再回到当前行。

### 修复
- `LyricsView.set_document(..., keep_position=True)`：同一首歌重新解析（偏移校准、翻译开关、字号变化）时保留当前播放位置与滚动偏移，不再把滚动条重置为 0。
- 重建文档时暂存旧的滚动范围与偏移，避免 Qt 在新内容尚未布局完成时把值钳到 0（这正是「跳到顶端」的直接原因）。
- 偏移校准后 1.5 秒内不自动重新居中，`set_position()` 与 `resizeEvent()` 都遵守这个窗口——用户在校准时间轴时，视口保持不动，只有高亮行变化。
- 切歌仍从第一行开始（`keep_position=False` 路径不变）。

### 测试
- 新增 `tests/test_lyrics_view_scroll.py`：偏移重建后滚动值必须保持不变；切歌仍归零。

## v1.0.5 — 2026-10-18

第四轮反馈的后续修正：播放栏控件必须始终居中，同时尽量完整显示歌曲信息。

### 修复
- 播放栏改为三列网格（左信息 / 中控制 / 右工具），两外侧列等宽，**播放按钮与进度条严格居中于窗口**；
  此前是 HBox + stretch，左侧比右侧宽，控制区整体右偏约 190px。
- 中列宽度随窗口自适应（≥900px：30% 宽，300–560px；窄窗：28%，240–320px），左右列对称取值，
  信息区在剩余宽度内最大化（宽窗仍可完整显示 36 字长标题）。
- 窄窗（<760px）隐藏收藏心形，为标题让出空间。
- 附带修复下载服务的提交顺序竞态：先写下载索引再置为 `done`，避免「显示已完成但索引尚未落盘」。

## v1.0.4 — 2026-10-18

第四轮用户反馈：底部播放栏长歌名展示不全。

### 修复
- `TrackInfo` 的宽度上限原来被硬编码为 260px（≥1000px 窗口）/190px，长歌名只能显示 6–8 个字；现按窗口宽度分级 180/280/400/520px。
- 来源徽章从标题行移到第二行；标题独占整行（只留 4px 边距）。
- 缓冲提示不再覆盖歌手名：加载时在歌手名右侧显示「缓冲中」徽章，结束后恢复来源徽章。
- 播放栏左右留白重新分配（信息区 stretch 5 / 控制区 5），中间进度条仍随窗口伸缩；窄窗（<860px）隐藏音量、<1000px 收窄信息区。
- 附带修正 `paint_badge()` 对 `tone="accent"` 这类命名色的处理（此前会画成黑底）。

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)；日期为发布日。

## v1.0.3 — 2026-10-18

第三轮用户反馈整改。

### 修复
- **清晰度与字号**：字体改用整数像素 + full hinting，正文/次级文字整体放大 ~8%；界面字号范围扩到 80%–180%，歌词字号 70%–200%。
- **在线音源播放**：恢复原版「同一首歌跨源找回」能力——单源 404 时先按音质递进重试，再按标题/歌手/专辑/时长打分在其他音源中切换播放，并在状态栏标明实际来源；新增 16.5s 看门狗，避免卡在加载中。
- **LOGO**：侧栏与关于页改用原版矢量标志（`quiet-orbit-logo` 深浅两版），应用图标仍用原版多尺寸 `.ico`。

### 内部
- 新增 `hushplayer/online/matching.py`、`tests/test_cross_source.py`、`tests/test_theme.py`；`_online_failed` 终止时改为可见错误提示。

## 1.0.2 — 2026-10-18

第二轮反馈整改（9 项用户反馈 + 6 项巡检发现）。逐项复现、根因、修复与验收证据见
[`docs/qa/REIMAGINED_FIX_ROUND2.md`](qa/REIMAGINED_FIX_ROUND2.md)。

### 修复

- **歌词 / 沉浸式播放中闪屏**：移除沉浸式窗口上的整窗 `QGraphicsOpacityEffect`（离屏合成），A/B 模式切换改用快照 + `FadeOverlay` 淡出；歌词视图去掉 `WA_TranslucentBackground`，进入沉浸式前先把窗口背景设为氛围底色。渲染层采样 `delta=0.00`。
- **搜索时出现多余小窗口**：搜索框清除按钮构造时未设置 parent，显示后成为独立顶层窗口；已修复并加回归测试。
- **设置滑块卡顿**：滑块拖动过程只更新标签，松手/静默 220ms 后才写入设置并触发主题/缓存动作；主题应用增加签名缓存。
- **播放按钮三角形偏移**：改为按 icon 尺寸平移，像素测量中心与圆心一致。
- **最大化白边**：最大化时关闭 DWM 圆角与边框颜色，还原时恢复。
- **字体与原版不一致**：内置 MiSans（Regular/Semibold/Bold）并以私有方式加载，字体探测首选 MiSans。
- **主题切换生硬**：切换时对旧界面做快照淡出（260ms），标题栏新增太阳/月亮切换按钮（125% 缩放下 28×28 命中区）。
- **在线搜索体验**：音源胶囊栏（含各音源结果数）、最近搜索历史、「管理音源」入口、结果状态「N 首结果 · M 个音源 · K 个失败」。

### 新增

- 可写音源目录与音源管理：安装本地 `.js`、从 http(s) 链接安装、启用/停用、删除、恢复内置音源（`hushplayer/online/registry.py`）。
- `assets/brand/` 正式 Logo（由用户提供的 `HushPlayer.ico` 渲染 `logo.png`），窗口/托盘/侧栏/关于/打包全部接入。
- `assets/fonts/` 内置 MiSans 与许可文件；`hushplayer/core/fonts.py`。
- `hushplayer/ui/widgets/transition.py`、`hushplayer/ui/widgets/source_filter.py`。
- 测试：`tests/test_brand.py` 更新（官方素材优先后仍保留回退能力）。

## 1.0.1 — 2026-10-18

第一轮缺陷整改（10 项用户反馈 + 7 项巡检发现）。逐项复现步骤、根因、修复文件与验收证据见
[`docs/qa/REIMAGINED_FIX_ROUND1.md`](qa/REIMAGINED_FIX_ROUND1.md)。

### 修复

- **沉浸式首帧闪屏**：进入沉浸式不再先上屏再填充——氛围底色同步落位、控件布局完成后预栅格化再显示；曲目切换的过渡动画保留。
- **在线播放暂停/停止状态机**：解析中或缓冲中可以取消与暂停；播放失败时强制落到 `stopped` 并恢复控件可用；迟到的解析结果被丢弃，不会把已停止的歌曲重新加载。
- **最大化/还原**：修掉标题栏按钮双重触发导致的「点了没反应」；自绘窗口维护独立还原几何，最大化后还原不再变成全屏，Win+↑/Snap 与窗口几何持久化一并修正。
- **设置「在线音源」崩溃**：不再直接访问原始字典，统一转换为 `SourceInfo`；音源列表异步加载完成后自动出现，重名插件加短 id 区分。
- **2K/4K 界面偏小**：新增按物理分辨率自动缩放（2K 125%、4K 150%），在创建 `QApplication` 前生效，整体等比缩放；设置 → 外观可覆盖并提示重启。
- **桌面歌词逐字高亮**：改为 60 Hz 插值播放时钟 + 像素级软边扫过，不再按字符数估算或整字跳变；普通歌词与沉浸歌词同步使用。
- **主题切换**：设置卡片/行/控件递归刷新主题；主题预览改为三张迷你窗口预览卡（跟随系统/浅色/深色），选中态清晰；开关关闭态配色修正。
- **播放标识对齐**：列表播放指示器与序号共用右对齐基线。
- **选中 + 播放撞色**：关闭 QTableView 原生实心选中底色，选中行改为一整行低透明度莓果底；正在播放用标题色/均衡器/竖标记表达，不再红上红；深浅主题对比度均 ≥ WCAG AA。

### 新增

- `appearance.ui_scale` 设置项与「界面缩放」面板（跟随推荐 / 100% / 115% / 125% / 150%，含重启入口）。
- 品牌资源机制：`assets/brand/`（`logo.png`、`logo_light.png`、`logo_dark.png`、`icon.ico`、`icon.png`），投放即替换全部位置；规范见 `assets/brand/README.md`。
- `hushplayer/core/display.py`、`hushplayer/core/brand.py`、`hushplayer/audio/clock.py`、`hushplayer/ui/widgets/sweep.py`。
- 测试：`tests/test_clock.py`、`tests/test_sweep.py`、`tests/test_display.py`、`tests/test_brand.py`、`tests/test_playback_state.py`（共 24 例）。

### 已知限制

- 正式 Logo 仍等待作者提供素材（当前为占位标志），机制已就绪。
- 网易云部分曲目受版权/会员限制无法解析播放资源，属上游能力，已做跨音源回退与明确提示。
- 实时 DWM 合成后的「肉眼无闪」无法在无人值守环境录屏验证，列入人工验收清单。

## 1.0.0 — 2026-10-18

首个完整版本：本地音乐库、多平台在线音源、播放与队列、收藏与歌单、完整歌词系统、两种沉浸式播放器、桌面歌词、设置中心、缓存与下载、单实例与托盘、PyInstaller 打包与安装说明。
