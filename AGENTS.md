# AGENTS.md — HushPlayer 开发准则（每次改动前必读）

> 这份文件是给「下一次动手的人（包括 AI）」看的。**改代码、改安装包、改样式之前先读一遍**；
> 改完如果引入了新的约定或踩到新坑，回到这里补一条。

## 0. 每次改动的固定流程（先看这五步）

1. 读本文件相关章节：动安装包看 §5/§6.1，动菜单看 §6.2，动字体/缩放看 §4/§6.3；
2. 找到对应模块的「不变量」并按它写代码；
3. 跑 `pytest -q` + 至少一张真实截图；
4. 如果改到了易碎模块（安装包脚本、`popup.py`、`tracklist.py`、`playerbar.py`、
   `queue_panel.py`、`settings_widgets.py`、`settings.py`、`theme.py`、`display.py`、`app.py`），
   **必须在 §9 追加一条变更记录**——`pre-commit` 钩子会拦住不带的提交（放行：提交信息加 `[no-agents]`）；
5. 汇报时写清「改了什么 / 为什么 / 怎么验证 / 产物哈希」。

项目根目录：`F:\Projects\HushPlayer-Reimagined`
只读参考：`F:\Projects\HushPlayer`（原版）、`F:\Projects\HushPlayer-deepseek-v2`（Aura UI 原型）。
**不得修改这两个目录，也不要在里面建 worktree。**

---

## 1. 产品定位（用户原话的要求）

- 面向 Windows 10/11 的现代桌面音乐播放器，目标是「Apple Music 的设计品质 + 更自由的音乐管理 + 多音源」。
- 必须**真正可用**：按钮真的控制播放、歌词真的跟时间轴、搜索真的返回来源数据、歌单真的落盘、设置在重启后恢复。
  用户多次强调「不要只有模拟数据的原型」。
- 品牌色 `#C95770`（莓果红）。深色模式用中性炭黑/深灰，克制使用莓果红，禁止大面积酒红背景。
- 浅色模式干净通透；圆角、层次统一；不要堆无意义的卡片和边框。
- 中文界面（安装包向导也必须是中文）。

## 2. 用户对交互/视觉的固定偏好

- 列表行：标题 + 副标题（歌手 · 来源），行高随字号缩放；**来源不做胶囊徽章**，用浅色文字跟在歌手后面。
- 菜单/下拉必须是自绘圆角浮层：12px 圆角、细描边、hover 16% 莓果红、勾选列统一对齐、二级菜单与主面板留 6px 间隙。
- 设置页：标签左、控件右；窄窗口时控件换行到下一行并右对齐；主题预览三张瓦片自适应缩小。
- 播放栏：`上一曲 / 播放 / 下一曲` 严格居中；信息区限宽（`theme().scaled(200)`）；随机/循环开启用图标 + 3px 圆点。
- 动画：主题切换有「中央日月图标 → 黑白过渡 → 新配色」全屏动画（可调时长/图标大小），另有圆形揭示与关闭两种模式。
- 沉浸式播放器两种模式：A 全幕歌词、B 封面舞台；都带真实播放控制、队列、翻译开关。

## 3. 技术架构（不要轻易换）

- Python 3.13 + PySide6 6.11.1（Widgets 自绘 + QSS），mutagen、Pillow、requests、winrt（SMTC）。
- 音频：QMediaPlayer + QAudioOutput；在线播放经本地 `AudioProxy`（Range + 磁盘缓存）。
- 在线音源：`hushplayer/runtime/source_runtime`（Node），JSONL 协议；`hushplayer/online/*` 适配。
- 数据目录：`%LOCALAPPDATA%\HushPlayerReimagined`（`HUSHPLAYER_DATA_DIR` 可覆盖）；可重建缓存与用户数据分离。
- 目录：`hushplayer/{core,model,store,library,audio,online,lyrics,services,ui}`、`packaging/`、`tools/`、`tests/`、`docs/`。
- **禁止**引入 Velopack；不安装系统级服务；不修改注册表全局策略。

## 4. 代码层不变量（踩过的坑，别再踩）

| 主题 | 规则 |
| --- | --- |
| 字号 | 唯一换算入口 `theme().px(size)`；`pt()` 只是 `px*0.75`；字体 `setPixelSize` 取整；`PreferNoHinting`（full hinting 会让中文半粗笔画不匀）。 |
| 缩放 | 界面缩放走「字体/布局倍数」，**不要设 `QT_SCALE_FACTOR`**（分数 DPI 会发虚）。 |
| 绘制文字 | 自绘统一用 `theme().draw_text()`（整数基线），不要直接 `drawText(QRectF, AlignVCenter)`。 |
| 颜色 | QSS 里必须用 `css_rgba()`；`str(QColor)` 是 Python repr，会毁掉整张样式表。 |
| 图标 | `core/icons.py` 的颜色参数只能吃 `QColor/color_key`，alpha 由 painter 控制。 |
| 调色板覆盖 | 局部改色用对象级 override（`TrackTable.palette_override`、`QueuePanel.activate_palette()`），**不要**改全局 `theme().palette`。 |
| 队列 | `_items` 是界面顺序、`_order` 是播放顺序；随机开启时当前曲置首；`append()` 一律排队尾。 |
| 历史 | 播放历史由 `HushPlayer._record_play()` 通过 `player.track_started` 写入；`最近播放` 依赖它，别删。 |
| 在线收藏 | 在线曲入库时要补 `album_id`（`library._ensure_online_album`），否则「专辑/歌手」聚合查不到。 |
| 播放失败 | 失败必须走终态（`_set_busy(False)` + `engine.stop()` + `error_message`），否则 UI 卡在「缓冲中」。 |
| 测试 | 跨用例不要反复建/销毁 `OnlineSourceClient`（QProcess 双销毁会 fail-fast）；GUI 夹具 teardown 会弹模态时用 `HUSHPLAYER_NO_CLOSE_PROMPT=1`。 |

## 5. 构建与发布

- 应用构建：`pwsh -File packaging\build.ps1 -Zip -SkipTests`
  → 产物固定到 `F:\HushPlayerBuild\out\HushPlayer\` 与 `HushPlayer-<ver>-win64.zip`，**只留一份，不要复制回仓库**。
- 安装包（**只有用户明确说「生成安装包」时才做**）：
  1. 改 `packaging/installer.iss` 的 `#define AppVersion`；
  2. `& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss`；
  3. 产物 `F:\HushPlayerBuild\out\HushPlayer-<ver>-setup.exe`。
- 验收脚本：`pwsh -File tools\verify_package.ps1`（要求 `window=…`、`instances=1`、`alive_after_close=False`）。
- 版本号：`hushplayer/version.py` + 根 `CHANGELOG.md`（**正文在根目录**，`docs/CHANGELOG.md` 只是指针）+ `docs/INSTALL.md` 的版本与哈希。
- Git：本地 `master`；推送只推 `master:main` 与 `master:reimagined` 到 `huoweihua312-blip/HushPlayer`。
  **不要动旧标签、不要 force push 其他分支**；`main` 的历史已切到本项目（旧项目保存在 `legacy-main` 分支）。

## 6. 已解决问题索引（先看这里，别重复造轮子）

### 6.1 安装包目录记忆（**当前仍有 bug，见第 8 节**）

机制（`packaging/installer.iss`）：

- `DefaultDirName={code:PreviousDir}`；`DisableDirPage=no`；`UsePreviousAppDir=no`
  （`UsePreviousAppDir=yes` 会把「上次目录」和默认目录末段拼接，曾出现 `F:\HushPlayer\dir_override`）。
- `PreviousInstallDir()` 依次取，且**都要求 `DirExists`**：
  1. `%LOCALAPPDATA%\HushPlayerReimagined\last_program_dir.ini` 的 `[install] dir`
     （程序启动时由 `hushplayer/core/paths.py:remember_program_dir()` 写入，仅 frozen）；
  2. `HKCU\Software\HushPlayer\InstallDir`（卸载**不删**这个键，就是为了记住目录）；
  3. 本 AppId 的卸载记录 `InstallLocation`。
- `CurPageChanged(wpSelectDir)` 会再写一次 `WizardForm.DirEdit.Text`，但显式 `/DIR` 优先（`{param:DIR|}` 非空时跳过）。
- 卸载：`[UninstallDelete]` 只清 `{app}\_internal`、`HushPlayerUpdater.exe` 与 `{app}\Data`，**保留** `%LOCALAPPDATA%\HushPlayerReimagined` 用户数据。

验证方式（不依赖 GUI 向导）：

```powershell
# 1) 显式 /DIR 必须赢
HushPlayer-<ver>-setup.exe /VERYSILENT /DIR=F:\HushPlayerBuild\dirfix /LOG=...
# 2) 不带 /DIR 必须落到记忆目录
HushPlayer-<ver>-setup.exe /VERYSILENT /LOG=...
# 3) 卸载后目录/快捷方式清空，用户数据保留
```

**测试纪律**：测试安装会写 `InstallDir` 与 `last_program_dir.ini`，污染用户记忆。
测试前先备份这两个值，测试后恢复；或者用 `/DIR` 指向临时目录并在测试结束前把记忆改回去。

### 6.2 菜单/下拉（浮层，不再用独立窗口）

- `hushplayer/ui/widgets/popup.py`：`PopupMenu` 优先作为**宿主窗口内的子控件浮层**（无独立窗口 → 无 DWM 矩形阴影、无黑角、点击不被窗口命中区截断）；
  装不下时才回退独立窗口 + `setMask(圆角 ∪ 子菜单)`（桌面歌词这种小窗走这条）。
- 二级菜单画在同一浮层里（`_sub_open/_sub_rect/_sub_item_at`），与主面板留 6px 间隙；
  指针穿过间隙时靠 `_in_bridge()` 保持打开（否则「一移过去就消失」）。
- 下拉：`SettingCombo.showPopup()` 用 `QTimer.singleShot(0, ...)` 异步弹出，否则会被立即关闭。

### 6.3 字体与缩放

- 1.0.29 起统一 `theme().px()`；1.1.10 起界面缩放不再用 `QT_SCALE_FACTOR`，改倍数（日志 `界面缩放：125%（字体与布局 ×1.25，DPI 1.0）`）。
- 加粗发虚：`PreferFullHinting` → `PreferNoHinting`。

### 6.4 其他已修问题（简述）

- 队列时长被截断：面板宽度随字号缩放，窄宽列宽按字号换算，滚动条出现时重算。
- 来源样式：胶囊 → 副标题浅色文字。
- 在线收藏不进专辑/歌手：SQL 只查 `kind='local'`；改为「本地 + 已收藏在线」，并给在线曲补 `album_id`。
- 最近播放恒空：从未调用 `record_play`；改为监听 `track_started`。
- 主题连点卡死：`ThemeReveal.finish()` + 冷却窗口，避免多层遮罩叠加。
- 托盘图标：项目目录带 Low 完整性标签时 `Shell_NotifyIcon` 返回 WinError 5；打包版装到 Medium 目录正常，`services/tray_probe.py` 会真实探测，失败则最小化到任务栏而不是隐藏窗口。
- 关闭询问：默认 `ask`，`closeEvent` 有重入保护（Windows 会重复投递 WM_CLOSE）。
- 歌单删除崩溃：`playlist_menu()` 内部自己 `exec()` 又返回 `None`；现在只构建、由调用方显示。

## 7. 验证纪律（每个改动都要过）

1. `pytest -q`（当前基线 **219 passed**；只增不减，禁止放宽断言）。
2. 至少一个真实 GUI/离屏截图（`tools/probe_*.py` → `artifacts/qa/...`），不要只凭代码想象。
3. 涉及打包：`packaging/build.ps1` + `tools/verify_package.ps1`。
4. 涉及安装包：静默安装 → 版本/快捷方式/注册表 → 卸载 → 残留检查（见 6.1）。
5. 汇报时写清楚「改了什么、为什么、怎么验证的、产物哈希」。

### 7.1 让 AGENTS.md 真正生效的三层机制

1. **自动注入**：DSH 会把仓库根的 `AGENTS.md` 作为工作区指令注入每次会话（文件变化后也会重新注入）。
   所以它必须留在仓库根、保持简短（当前约 130 行），否则会被截断或读不完。
2. **提交门禁**：`.githooks/pre-commit` → `tools/agents_guard.py`。
   改到 §0 列出的易碎模块却没 `git add AGENTS.md` 时提交被拒。
   每个新克隆执行一次 `pwsh -File tools\install_git_hooks.ps1` 启用（`core.hooksPath=.githooks`）。
3. **执行纪律**：每次开始改动前，先在回复里说明「读了 §X」；改完把结论写进 §6/§9。
   要给规则加新条款，加到 §4（不变量）或 §6（方案索引），不要散落在别处。

> 工具链小坑：本机 `.venv` 的 Python 以 Low 完整性运行，而 DSH 写入的 `AGENTS.md` 是 Medium，
> 直接 `write_text` 会 `PermissionError`。改这个文件用 PowerShell（Medium 进程）写：
> `Set-Content AGENTS.md $text -Encoding UTF8`。

## 8. 已知问题 / 待办

- **安装包默认目录仍可能不对（用户 1.1.26 报告，本轮不修）**。
  2026-10-22 现场状态：
  - `HKCU\Software\HushPlayer\InstallDir = F:\HushPlayer`（存在）；
  - `last_program_dir.ini = F:\HushPlayerBuild\verify_1_1_26`（**该目录已被卸载删除 → 属脏数据**）；
  - `%LOCALAPPDATA%\Programs\HushPlayer\HushPlayer.exe` 仍是 1.1.4 的遗留文件（无卸载记录）。
  排查顺序建议：
  1. 确认 `PreviousInstallDir()` 在该机器上实际返回什么（临时加 `[Code]` 日志到 `{tmp}\hushdir.log`，或用 `/LOG`）；
  2. 检查 `CurPageChanged` 是否把 `DirEdit` 又写回了默认值；
  3. 清理脏记忆（删除失效的 ini / 修正 `InstallDir`）后再看向导默认值；
  4. 长期方案：把「测试安装」和「用户安装」的记忆分开（测试用独立 AppId 或临时注册表影子键），避免验证过程污染用户目录记忆。
- `%LOCALAPPDATA%\Programs\HushPlayer` 的 1.1.4 残留需要一次清理（属用户机器上的历史安装）。

## 9. 本文件变更记录

- 2026-10-22：首次创建。汇总用户要求、技术不变量、安装/菜单/字体/队列等既有方案，记录安装包默认目录的待排查项。
- 2026-10-22：新增 §0「每次改动的固定流程」与 §7.1「三层生效机制」；新增提交门禁
  `.githooks/pre-commit` + `tools/agents_guard.py` + `tools/install_git_hooks.ps1`（说明见 `docs/GIT_HOOKS.md`）。
- 2026-10-22：补充编辑方式说明——`.venv` 的 Python 是 Low 完整性，写 Medium 的 `AGENTS.md` 会 `PermissionError`，改用 PowerShell 写。
- 2026-10-23：新增跨平台歌单导入（services/playlist_link.py、playlist_import.py、playlist_matcher.py + ui/playlist_import_dialog.py）。链接导入只支持网易云公开歌单，其余平台引导导出文件；匹配复用 online/matching.py 并对 Live/Remix/伴奏等版本 token 加减分；自动匹配的在线结果必须 resolve_playback 验证后才算可播放。详见 docs/PLAYLIST_IMPORT.md。

- 2026-10-23：歌单导入 1.2.1 体验改进——三档匹配强度（`MATCH_STRENGTHS` strict/balanced/loose）、候选 18 个 + 变体二次搜索（`_query_variants`/`_start_variants`）、「全部采用最佳候选」、导入前确认与未导入 CSV 导出（`_export_missing`，`data_dir()/exports`）。注意：`.venv` Python 写 `CHANGELOG.md`/`AGENTS.md` 会 PermissionError，必须用 PowerShell。
- 2026-10-23：1.2.2 修复「双击歌曲行弹出的候选菜单盖住光标、第二次点击误选」。菜单锚点改为光标右下方 28/30px 并做屏幕翻转；`PopupMenu` 增加 `_shown_at` + 220ms 激活保护（双击第二下不再命中菜单项）。以后凡是由「双击/单击」直接弹出的菜单都要走这条规则。
- 2026-10-23：1.2.3——① `PopupMenu._sub_hover` 在指针离开子菜单时必须清零，否则会出现「二级菜单外仍高亮子项」；② 原生标题栏窗口（QDialog）用 `core/theme.py:apply_native_title_bar()` + DWM 20/19 跟随主题，导入向导 `showEvent`/主题变更时调用；③ `_content_width()` 对无标题子菜单取空串，防 `horizontalAdvance(None)` 崩溃。
- 2026-10-23：1.2.4——导入向导的匹配表改用**自绘表头**（`_TableHeader`）。原因：原生 `QHeaderView` 不吃对话框 QSS/调色板，浅色模式下会变成黑色横条；同时 `QColor("rgba(...)")` 是无效写法（会退化成纯黑），自绘取色一律用 `theme().rgba()`。以后凡是「表格 + 主题」场景，优先自绘表头，不要依赖 QHeaderView 配色。
- 2026-10-23：1.2.5——匹配表包进圆角卡片（`QFrame#ImportTableFrame`，`palette.surface` + 10% 描边 + 12px 圆角），自绘表头只画文字与分隔线、不填底色。以后「表格进卡片」时，让容器负责背景与圆角，表头不要重复填色，否则会盖住圆角。
- 2026-10-23：1.2.7——导入歌单对话框改为**无边框自绘标题栏**（_DialogTitleBar，24px 左基线对齐、拖动移动、Esc 关闭、#HushDialogRoot 圆角遮罩）；正文收成一套字阶（15pt/600 标题、9.4pt/0.75 主说明、9pt/0.55 计数、9pt/0.5 提示）；修自绘表头取色（QColor 不能吃 CSS rgba 字符串，否则变黑）；页脚按钮前加 addStretch 防拉伸。
- 2026-10-23：1.2.6——新增「全黑」主题（`Palette(mode="pure")`，window/sidebar `#000000`，`_PALETTES` 三套并存，`is_dark` 把 pure 计入深色），主题选择器扩为四项并按宽度自适应瓦片；导入匹配表外框去掉（容器只留底色）。注意：`ThemePicker` 新增 API 后要 `grep "def set_value"` 确认没有重复定义（后定义会覆盖前者）；`QColor("rgba(...)")` 仍是无效写法。

### 1.2.9（导入歌单零人工确认 · 自绘 CheckBox）

- 匹配器新增 `auto_adopt`（默认由 `playlist.auto_adopt` 决定，默认 `True`）：本地候选不再直接进 `review`；在线可用时把本地候选带进在线竞优，按分数取高者；在线只有一个候选时也直接采用。只有完全无候选才 `unmatched`，`review` 仅在关闭自动采用时出现。
- 不要用原生 `QCheckBox`：indicator 一旦用 QSS 上色就不再画对勾（深色下变成实心色块）。统一用 `hushplayer/ui/widgets/check.py:CheckBox`（`QAbstractButton` 子类，`toggled(bool)` 而非 `stateChanged`）。
- 自绘控件的信号差异：`CheckBox`/`ToggleSwitch` 只有 `toggled`，没有 `stateChanged`；回调签名用 `bool`。
- 测试必须 `_pump(qapp, matcher)`：`PlaylistMatcher.start()` 用 `QTimer.singleShot(0, …)` 分片执行，不同步事件循环会停在 `pending`。### 1.2.8（系统对话框自绘、导入表表头对齐）
- 规则：不再使用 `QMessageBox` / `QInputDialog`；统一走 `hushplayer/ui/dialogs.py` 的 `notify / confirm / choose / ask_text`（`QFileDialog` 例外，保留系统文件选择器）。
- 规则：自绘表头必须与 delegate 用同一套水平对齐（只有评分列 `AlignRight`），否则会差 6–10px。
- 教训：`QPainter.save()` 与 `restore()` 之间抛异常会吞掉 Python traceback，终端只剩 `Painter ended with N saved states` + access violation；定位时 monkeypatch 包一层打印真实异常。
- 教训：`build.ps1` 在旧版正在运行时无法删除输出目录，已改为回退到 `HushPlayer-<version>`，不杀用户进程。- 2026-10-25：1.2.10——导入歌单**彻底零确认**：`_apply()` 不再弹确认框/同名菜单（同名自动 merge），匹配器去掉 margin 门槛（有候选就采用最高分），`_finished()` 兜底采用残留 review/pending；对话框加 scrim（宿主窗口上 `rgba(0,0,0,0.40)` 遮罩）+ `palette.surface` 背景 + 1px 描边与主界面分层；`apply_import` 逐首 try/except 并写汇总日志。教训：`PlaylistImportDialog` 的 scrim 依赖父窗口，探针必须传 `ctx().window`，否则看不到遮罩。

### 1.2.11（2026-10-25）

- 修复导入向导勾选框悬停崩溃：`hushplayer/ui/widgets/check.py` 误调用不存在的 `HoverAnimation.set_end()`，应为 `HoverAnimation.to()`。凡复用 `hushplayer/ui/widgets/common.py` 中的小工具类，必须先确认公开方法名。
- 回归：`tests/test_dialogs.py::test_checkbox_hover_uses_hover_animation_api` 覆盖进入/离开两段悬停动画（纯离屏渲染不会触发 `enterEvent`，这类 bug 只能靠事件级测试或真实悬停探针发现）。
- 说明：日志里的 `Request failed with status code 404`、`播放解析超时（20000 ms）` 为上游音源插件问题，不是崩溃原因。
- 2026-10-25：1.3.0——① 修复歌曲列表选中行高亮「只覆盖部分列」：`TrackDelegate.paint` 不再只在第 0 列画整行底，而是**每个单元格都画同一块整行圆角矩形**，靠单元格裁剪拼成整条带，任何单格重绘（封面加载、收藏变化）都会补齐；回归探针 `tools/probe_r83_select.py` 断言「只重绘标题列后颜色不变」。② 新增右键「替换歌曲来源…」（`services/source_replace.py` + `ui/track_source_dialog.py` + `TrackRepository.update_source`）：跨音源重搜同一首歌，选中后只改来源字段、**保留 track.id**，收藏/歌单/历史不丢。
- 1.3.1（2026-10-25）：选中行高亮按「行」判定 hover（Qt 的 State_MouseOver 是按单元格给的，不能用于整行底色）；右键替换来源先 ensure_started、`_on_response` 兼容 list/dict 并加超时兜底。
1.3.2 (2026-10-25) 高亮色带逐格叠加（补 setClipRect）；替换来源后同步刷新列表页/队列/当前曲目（PlayQueue.replace_track 需同时更新 _by_id）。
