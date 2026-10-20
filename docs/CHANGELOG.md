# Changelog

## v1.1.3 — 2026-10-20

安装时可选择安装目录。

### 修复
- 升级安装时看不到「选择目标位置」页：Inno Setup 默认 `DisableDirPage=auto`，检测到同 `AppId` 的旧安装就直接复用上次路径。现在显式 `DisableDirPage=no`，每次安装都会显示目录页与「浏览…」按钮，并保留 `UsePreviousAppDir=yes`（默认停在原目录，可直接改）。
- 安装包 `HushPlayer-1.1.3-setup.exe`（82.4 MB），SHA256 `1579A07D94F4AC3ECEDCFA1651DF18882CC9A4AEDAF5E013A9EC4AE3CA14BE51`。

### 验证
- 目录页文本实测：`安装程序将安装 HushPlayer 到下面的文件夹中。` / `点击“下一步”继续。如果您想选择其他文件夹，点击“浏览”。` / `浏览(&R)...` / `上一步(&B)` / `下一步(&N)`。
- 自定义目录安装：`/DIR=F:\HushPlayerDirTest` → `HushPlayer.exe` 存在、版本 `1.1.3`；卸载后目录内 exe 移除。

## v1.1.2 — 2026-10-20

安装包中文界面。

### 变更
- 安装向导改为**简体中文**：`packaging/languages/ChineseSimplified.isl`（取自 Inno Setup 官方仓库，含 UTF-8 BOM），`[Languages]` 只列中文，因此不再出现语言选择页。
- 附加任务、桌面快捷方式、启动项说明全部中文（`[CustomMessages]` + `[Tasks]`）。
- 安装包 `HushPlayer-1.1.2-setup.exe`（82.4 MB），SHA256 `D198581B46E09D8D4A6075901DA6A39361349152453C52504A9EC9F45383DFDD`。

### 验证
- 向导文本实测：`欢迎使用 HushPlayer 安装向导` / `下一步(&N)` / `取消`。
- 静默安装后 `HushPlayer.exe` 版本与卸载项均为 `1.1.2`。

## v1.1.1 — 2026-10-20

安装包。

### 新增
- `packaging/installer.iss`（Inno Setup 6）：生成 `HushPlayer-1.1.1-setup.exe`（82.4 MB）。
  - 按用户安装到 `%LOCALAPPDATA%\Programs\HushPlayer`，**不需要管理员权限**；
  - 开始菜单快捷方式 + 卸载入口，可选桌面图标、可选登录自启（`{userstartup}`）；
  - 升级覆盖安装沿用同一 `AppId`，会先关闭正在运行的实例；
  - 卸载只删程序目录，`%LOCALAPPDATA%\HushPlayerReimagined`（音乐库、歌单、设置、缓存）保留，重装后数据仍在；
  - 安装目录位于 Medium 完整性目录，托盘图标注册可正常通过（实测 `托盘图标注册成功（系统已接受）`）。

### 验证
- 静默安装 → 文件/版本 1.1.1、HKCU 卸载项、开始菜单快捷方式均正确；启动后托盘注册成功。
- 静默卸载 → 程序目录、开始菜单、`HKCU\Software\HushPlayer`、卸载项全部清除；用户数据 160 个文件保持不动。
- `pytest`：191 passed / 0 failed（`artifacts/junit_1_1_1.xml`）。

## v1.1.0 — 2026-10-20

1.1.0 是「可交付候选」：不改主功能，收口可靠性、文档与发布流程。

### 可靠性
- 托盘改为**悲观默认**：探针确认系统接受图标前不认为托盘可用，避免早期关闭导致窗口「消失且找不回」。
- 隐藏到托盘前再探测一次注册结果（Explorer 重启、安全软件回收图标时可及时发现），失败则最小化到任务栏并提示，而不是隐藏。
- 新增回归测试 `test_tray_failure_keeps_window_reachable`。

### 文档校正（此前落后于实现）
- `KNOWN_ISSUES`：SMTC 与任务栏进度改为「已实现 / 按系统能力降级」；补充 2 万首以上未实测、soak 覆盖说明。
- `FEATURES`：媒体键行改为「键盘媒体键 + SMTC」；版本号、安装体积更新；移除过期的「SMTC 未接入」。
- `TEST_REPORT`：全量结果更新为 190 passed，并新增 1.1.0 soak 记录（20 分钟循环播放/切页/桌面歌词/主题切换）。
- `INSTALL`：发布目录改为 `F:\HushPlayerBuild\out`，新增 SHA256 校验、升级与回滚步骤、版本查看方式。
- `README`：版本号与产物路径更新。

### 验证
- `pytest -q`：191 passed / 0 failed。
- 打包验收：启动、单实例、窗口尺寸、关闭退出。
- soak：见 `docs/TEST_REPORT.md` 第 13 节（内存与句柄曲线）。

## v1.0.50 — 2026-10-20

修复内容区左上角的白色「缺口」。

### 修复
- 根因：内容区背景层带 `border-top-left-radius: 12px`，而主窗口本身是半透明圆角窗（为了显示壁纸/桌面），圆角留下的透明区域直接透出桌面，看起来就是一块白色方块缺口。
- 改为直角背景（`#HushPageBackground` 仅设背景色），并同步 `refresh_theme()` 里的重建样式，避免切换主题后又把圆角加回来。

### 验证
- `pytest -q`：190 passed / 0 failed。

## v1.0.49 — 2026-10-20

日月动画的「定格」不再让界面消失。

### 调整
- 黑白遮罩改为峰值 92% 的薄纱：切换期间界面始终可见（被压暗/提亮），不再有一段时间整窗纯白/纯黑。
- 新配色在遮罩峰值处直接换入，随后遮罩在「定格」的前 220 ms 内退去；因此定格时看到的是**已经切换好的界面 + 中央日月图标**。
- 「定格时长」语义随之变化：现在指太阳/月亮在新界面上停留的时长（界面可见），说明文字已更新。
- 图标保留到最后一阶段才淡出（此前在遮罩开始时就消失）。

### 验证
- `pytest -q`：190 passed / 0 failed（更新 `test_sun_moon_reveal_pops_icon_then_fades`：遮罩峰值 < 1.0、末帧归零、定格阶段新界面与图标均可见）。
- 帧序列：`docs/screenshots/theme_hold_visible.png`（定格时刻的浅色界面 + 太阳）。

## v1.0.48 — 2026-10-20

修复切到「全屏日月动画」后切换主题崩溃。

### 修复
- `AttributeError: 'SunMoonReveal' object has no attribute 'DURATION_MS'`：`apply_theme()` 用 `overlay.DURATION_MS` 计算冷却窗口，但日月动画改成毫秒时间线后已无该常量。两个遮罩类统一提供 `animation_ms()`，应用侧改用它。
- 新增回归测试 `test_overlays_expose_animation_ms`，确保两种遮罩都回答动画时长；探针连续切三次主题不再抛异常。

### 验证
- `pytest -q`：190 passed / 0 failed。
- 构建验收：`window=1280x820`、`instances=1`、`alive_after_close=False`。

## v1.0.47 — 2026-10-20

日月动画可调：弹出时长、图标大小、黑白定格时长都进设置。

### 新增
- `SunMoonReveal` 改为毫秒时间线：`pop_ms`（图标弹出）、`wash_ms`（旧帧覆盖）、`hold_ms`（黑白定格）、`fade_ms`（新配色淡入），`total_ms()` 求和、`stage()` 返回 `pop|wash|hold|fade`，所有取值都由时长推导。
- 设置 → 外观 → 动效与密度 新增三项（仅在「全屏日月动画」下生效）：
  - 日月图标弹出时长 150–1200 ms，默认 420 ms（比上一版 213 ms 明显更长）；
  - 日月图标大小 60%–160%，默认 100%；
  - 黑白定格时长 0–900 ms，默认 260 ms。
- 存储键：`appearance.theme_anim_pop_ms`、`appearance.theme_anim_icon_scale`、`appearance.theme_anim_hold_ms`。

### 修复
- 设置数值标签不再折行（按 `QFontMetrics` 计算宽度，容纳 "1200 ms"）。
- `QSlider` 补上品牌样式（莓果红滑轨与圆柄）；此前在设置里显示为系统蓝色。

### 验证
- `pytest -q`：189 passed / 0 failed（新增 `test_sun_moon_timeline_honours_settings`）。
- 截图：`docs/screenshots/theme_animation_settings.png`、`docs/screenshots/theme_sun_pop.png`、`theme_moon_pop.png`。

## v1.0.46 — 2026-10-20

全屏主题动画改为「中央弹出太阳/月亮 + 黑白过渡」。

### 变更
- 按反馈重做 `SunMoonReveal`（原 `SunriseReveal`）：不再做上下擦除与暖色光晕，动画只有黑与白。
  - 0–26%：窗口正中弹出太阳（切浅色，白色）或月亮（切深色，黑色），带缓动放大。
  - 24–58%：整窗铺一层纯白（切浅色）或纯黑（切深色），把旧画面完全盖住、避免两套配色半透明叠加的发灰/重影。
  - 58–100%：新配色从中性色里淡入；图标在此之前已经淡出。
- 性能：每帧最多两次整窗 blit（旧帧 + 新帧，或旧帧 + 纯色填充），去掉了逐帧 `QImage` 渐变遮罩合成，2560 宽度下明显更顺。
- 「过渡动画」模式的扩散边缘也改为纯黑/纯白，界面里不再出现橙/莓果色高光。

### 验证
- `pytest -q`：188 passed / 0 failed。
- 逐帧截图：`docs/screenshots/theme_sun_pop.png`（太阳弹出）、`docs/screenshots/theme_moon_pop.png`（月亮弹出）、`docs/screenshots/theme_sun_fade.png`（新配色淡入）。

## v1.0.45 — 2026-10-20

主题切换新增「全屏日出日落」动画，并可在设置中选择动画方式。

### 新增
- `hushplayer/ui/widgets/transition.py:SunriseReveal`：整窗铺满的日光转场，900ms、`InOutCubic`。切到浅色时新画面自下而上"日出"，切到深色时自上而下"日落"；过渡带用 `QImage + CompositionMode_DestinationIn` 做逐像素渐变遮罩（48 步条带会有明显横纹，已改掉），边缘带一条随行暖色光晕与低悬日轮。
- 设置 → 外观 → 动效与密度 →「主题切换动画」改为下拉选择：过渡动画（从标题栏按钮扩散，原有效果）/ 全屏日出日落 / 关闭。设置项 `appearance.theme_animation_mode`（`reveal` | `sunrise` | `off`），默认 `reveal`。
- 旧布尔设置 `appearance.theme_animation` 自动迁移：`true → reveal`、`false → off`，迁移后从配置里移除旧键，不丢用户意图。
- 连点保护与旧遮罩收尾对两种动画共用（`_end_theme_transition` / `_theme_cooldown_until`），快速点按钮仍不会叠层。

### 验证
- `pytest -q`：188 passed / 0 failed（新增动画模式默认/迁移、`SunriseReveal` 边缘方向与 `finish()` 三项测试）。
- 逐帧截图：`docs/screenshots/theme_sunrise.png`、`docs/screenshots/theme_sunset.png`（1600×1000，progress≈0.45，无横纹）。

## v1.0.44 — 2026-10-20

修复快速连点主题按钮时揭示动画卡住。

### 修复
- 每次切换都会新建一层 `ThemeReveal`，旧的那层从不收尾；多层遮罩叠在一起就是"卡住"的残留圆弧，下一次快照还会把圆弧拍进去，永久留在画面上。
- `ThemeReveal.finish()`：立即停表、`progress=1`、隐藏并关闭。
- `HushApp._end_theme_transition()`：开始新切换前先收尾旧遮罩并清空引用；`destroyed` 信号也会清引用，避免持有已销毁的包装对象。
- 连点保护：`_theme_cooldown_until`（动画时长 + 0.15s）内的再次切换直接换色、不再播放动画，避免遮罩层层堆叠。
- 提示去重：`MainWindow.toggle_theme_mode()` 1.2s 内不再重复弹「已切换到浅色/深色模式」。

### 验证
- 新增测试 `tests/test_theme_transition.py::test_reveal_finish_retires_overlay`、`::test_app_retires_previous_reveal_before_next`。
- `pytest -q`：186 passed / 0 failed。
- 离屏连点探针 `tools/probe_r49_theme2.py`：连点 6 次后 `overlay_alive=False`、无异常、最终模式正确。

## v1.0.43 — 2026-10-20

构建产物移回本机 F: 盘（不写入 C:）。

### 变更
- 打包输出改到 `F:\HushPlayerBuild\out\HushPlayer`（该目录无 Low 完整性标签，exe 以正常 Medium 完整性运行，托盘图标可被系统接受）。
- 仓库内 `packaging\out` 只保留 zip 副本与 `SHA256SUMS.txt`；PyInstaller 的中间产物仍在 `packaging\build`。
- `tools/verify_package.ps1` 同样从 `F:\HushPlayerBuild\out\HushPlayer` 复制到 `F:\HushPlayerBuild\verify` 后验收，不再使用 `%LOCALAPPDATA%`。
- 清理了此前在 `%LOCALAPPDATA%` 下生成的 HushPlayerBuild / HushPlayerVerify / HushTrayTest / HushTrayVerify / HushV42 目录。

### 验证
- `pytest`：184 passed / 0 failed。
- 构建日志：`完整性：no mandatory label (Medium)`、`（输出固定在本机 F: 盘，不写入 C:）`。
- 运行 `F:\HushPlayerBuild\out\HushPlayer\HushPlayer.exe`：日志 `托盘图标注册成功（系统已接受）`。

## v1.0.42 — 2026-10-20

移除迷你播放器；托盘不可用时改为最小化到任务栏；构建输出移到普通目录。

### 变更
- 删除 `hushplayer/ui/mini_player.py` 及全部入口（Ctrl+Shift+M、托盘菜单项、关闭对话框第三项）。
- 托盘图标不可用时不再打开迷你播放器：关闭/最小化一律**最小化到任务栏**并提示「并未退出」，窗口始终可从任务栏找回；关闭对话框第三项按可用性显示「最小化到托盘」或「最小化到任务栏」。
- 构建输出改到 `%LOCALAPPDATA%\HushPlayerBuild\out`（Medium 完整性），仓库 `packaging\out` 只保留 zip 副本。原因：仓库目录带 Low 标签，在其中构建出的 exe 会被 Windows 拒绝注册托盘图标。

### 验证
- `pytest`：184 passed / 0 failed（迷你播放器用例替换为「无托盘时最小化到任务栏」）。
- 新构建产物路径 `%LOCALAPPDATA%\HushPlayerBuild\out\HushPlayer\HushPlayer.exe`（无 Low 标签），运行日志 `托盘图标注册成功（系统已接受）`。

## v1.0.41 — 2026-10-20

修复最大化/还原时的崩溃（托盘改写遗留）。

### 修复
- `MainWindow` 缺少 `_tray_available()`：上一轮重写托盘判定时误删该方法，而 `changeEvent`、`_hide_to_tray`、关闭对话框仍在调用，导致**点最大化即抛 AttributeError**，窗口停在半切换状态（用户截图中的 `frameless.py:140 toggle_maximize → main_window.py:754 changeEvent`）。
- 恢复 `_tray_available()`：`_tray` 存在且 `_tray_ok` 为真时可用；探针跑完前乐观视为可用。
- `changeEvent` 增加异常兜底，托盘状态异常不再影响窗口最大化/最小化。
- 新增回归测试 `test_window_state_changes_survive_tray_state`：最大化→还原→再最大化、以及伪造 `WindowStateChange`，确保不再依赖缺失属性。

### 验证
- `pytest`：184 passed / 0 failed（含新回归用例）。
- 真实窗口探针：`max=True 1920x1032 → normal=False 1280x820 → min=True → restored`，无异常。

## v1.0.40 — 2026-10-20

托盘图标：改成真实注册探测，并如实提示低完整性目录问题。

### 修复
- 新增 `hushplayer/services/tray_probe.py`：直接调用 `Shell_NotifyIconW(NIM_ADD/NIM_DELETE)` 判断**本程序**图标是否被外壳接受，返回真实 Win32 错误码，不再用 `geometry()`、也不再把「系统托盘可用」当成「本程序注册成功」。
- 托盘诊断日志改为「托盘图标注册成功（系统已接受）」/「托盘图标注册失败：<原因>」；失败且 `WinError 5` 时提示「请把程序移到桌面等普通目录运行」，并保持窗口可用（不隐藏到不可见的托盘）。
- 根因（用户对照实验确认）：项目目录带 `Low Mandatory Level` 标签，`python.exe` 与构建出的 exe 继承 Low，低完整性进程注册托盘图标会被系统拒绝（错误 5）；原版项目目录是 Medium，因此同样代码在原版正常。`icacls /setintegritylevel` 无法提升标签（需要 `SeRelabelPrivilege`），所以交付验收改为在普通目录（桌面/AppData/下载）解压运行。

### 验证
- 项目目录内探测：`probe False 5`（预期，Low 环境）。
- 复制发布包到 `%LOCALAPPDATA%\HushTrayVerify`（Medium）运行：日志 `托盘图标注册成功（系统已接受）`，通知区可见品牌图标。
- `pytest -q`：183 passed / 0 failed。

## v1.0.39 — 2026-10-12

托盘图标改用随包 `.ico`，并加一个一定能用的“找回来”快捷键。

### 修复
- 托盘图标改为优先加载 `assets/brand/HushPlayer.ico`（16–96px 多帧原生图标，`QIcon(path)` 与系统资源帧一致），矢量图标只作兜底；此前用 `QPixmap` 现画再 `addPixmap`，与系统托盘取帧路径不同。
- 新增全局快捷键 `Ctrl+Alt+H`：无论窗口在托盘、迷你播放器还是被隐藏，都能把主窗口叫回来（`GlobalHotkeys.show_window_requested` → `MainWindow.show_from_background()`，迷你播放器可见时先关闭它）。设置页快捷键说明同步补充。

### 说明
本机 `Shell_NotifyIconW` 直接返回 `FALSE`（`GetLastError()=5`），最小 PySide6 托盘也一样不显示，因此无法在本环境做“图标可见”的自动断言；`Ctrl+Alt+H` 是独立于托盘的恢复通道。

### 验证
- `pytest -q`：183 passed / 0 failed。
- `brand.tray_icon()` 尺寸帧：16/20/24/32/40/48/64/96/128/256。

## v1.0.38 — 2026-10-12

托盘图标不再被误判；迷你播放器重做。

### 修复
- 托盘判定放宽：Windows 11 对“溢出区里的图标”也返回 `geometry()=0,0,0,0`，旧逻辑会把它当成“没注册”并强行切到迷你播放器（这正是 1.0.37 里迷你播放器突然出现的原因）。现在只以 `QSystemTrayIcon.isSystemTrayAvailable()` 为准，可用时正常隐藏到托盘，仅记录 `托盘图标已注册（geometry=…）`。

### 改进
- 迷你播放器重做：424×140、80px 封面（12px 圆角）、标题 10.2/600 + 艺术家 8.8、右侧「返回主界面 / 关闭」小按钮、进度条带总时长、控制行带已播时间，圆角 18 与托盘卡片风格统一。

### 验证
- `pytest -q`：183 passed / 0 failed。
- 截图：`docs/screenshots/mini_player.png`。

## v1.0.37 — 2026-10-11

托盘不可用时，用迷你播放器接管“后台”。

### 背景
用独立的原生探针（不加载 HushPlayer 代码）验证：`Shell_NotifyIconW(NIM_ADD)` 直接返回 `FALSE`，`GetLastError()=5`（拒绝访问）；最小 PySide6 托盘程序（纯红块图标 + 系统标准图标）同样不出现，`geometry()` 为 `0,0,0,0`。同会话窗口站为 `WinSta0/Default`，进程未提权。结论：这台机器的任务栏/托盘环境拒绝新进程注册托盘图标，与原版实现（同为 `QSystemTrayIcon` + `show()`）无关。

### 修复
- 托盘不可用时，`_hide_to_tray()` 改为 `_background_without_tray()`：切到迷你播放器并隐藏主窗口，播放控制始终可达；提示「托盘图标不可用，已切换到迷你播放器」。
- 关闭询问的中间按钮按可用性变成「最小化到托盘」或「隐藏到迷你播放器」；选择「隐藏到迷你播放器」与 `minimize_to_tray` 设置走同一条后台路径。
- 首次托盘说明弹窗只在托盘可用时出现，避免对不可用环境做无效指引。

### 验证
- `pytest -q`：183 passed / 0 failed。
- 探针 `tools/probe_r40_fallback.py`：强制 `_tray_ok=False` 后 `_hide_to_tray()` → `main_visible=False mini=True`。
- 原生证据脚本 `tools/probe_tray_native.py`：`Shell_NotifyIconW add 0 err 5`。

## v1.0.36 — 2026-10-11

不再依赖托盘图标，窗口不会“消失”。

### 修复
- 托盘图标注册校验：启动 2.6s 后检查 `QSystemTrayIcon.geometry()`，为空即判定系统未真正接收图标，记录 `托盘图标未注册（geometry=… visible=…）` 并置 `_tray_ok=False`。
- 一旦校验失败：关闭询问里不再提供「最小化到托盘」、`minimize_to_tray` 自动退回任务栏最小化、`_hide_to_tray` 直接 `showMinimized()` 并提示，避免窗口被隐藏却找不到入口。
- `_tray_available()` 统一判定，替代原来分散的 `isVisible()` 判断，避免“图标没注册但 Qt 仍报 visible=True”。

### 说明
在本机用**不加载 HushPlayer 代码**的最小 PySide6 托盘程序（纯红块图标 + 系统标准图标）也无法出现在通知区，说明这台机器的任务栏/托盘环境会忽略部分进程的托盘注册，与图标素材无关。因此本版把“托盘不可用”当作正常降级路径处理。

### 验证
- `pytest -q`：183 passed / 0 failed。

## v1.0.35 — 2026-10-11

关闭询问只弹一次；托盘改用品牌图标。

### 修复
- 关闭询问重复弹窗：`closeEvent` 增加重入保护与 1.2s 抑制窗口。Windows 在模态框关闭后会把同一次 WM_CLOSE 再投递一次，旧代码会因此第二次询问；现在同一次关闭最多只问一次，选择「取消」时窗口保持打开。
- 托盘图标改为品牌标记：`brand.tray_icon()` 用矢量在深色圆角底板上绘制 Logo 的声波条（`>=24px` 五条带白点，`16/20px` 三条加粗），保证在 16px 通知区也清晰可辨；同时 `_reactassert`(1.2s 后) 再 `setIcon + show` 一次，规避 Explorer 偶发忽略首次注册。日志新增 `sizes=[16, 20, 24, 32, 48, 64]` 便于排查。
- 托盘不可用/图标异常时依旧保持窗口可见并提示；首次最小化到托盘的说明保留。

### 验证
- `pytest -q`：183 passed / 0 failed。
- 关闭探针 `tools/probe_r39_close.py`：连续 `close()` 三次只触发 1 次询问；`close_action=quit` 时 0 次询问并正常退出。
- 打包运行日志：`托盘图标：null=False visible=True available=True sizes=[16, 20, 24, 32, 48, 64]`。

## v1.0.34 — 2026-10-11

主题转场不再闪一帧新界面；最小化到托盘不会“找不回来”。

### 修复
- `HushPlayer.apply_theme` 改为「先冻结旧画面、再换调色板」：换主题前先把旧截图铺满窗口并让它完成一次绘制，再应用新主题，随后隐藏遮罩抓取新画面并开始日出/日落转场。原先的顺序会先呈现一帧完整的新主题，观感即闪烁。
- `ThemeReveal` 新增 `freeze()` / `resume_with()`，供上述两步式转场使用；仅进入设置页时的旧→新淡入路径改为同一套流程（非深浅色切换时用 `FadeOverlay`）。
- 托盘图标健壮性：`_build_tray` 校验 `QIcon.isNull()` 并在为空时回退到耳机图形，同时记录 `托盘图标：null=… visible=…`；`changeEvent` 只有在托盘**确实可见**时才隐藏窗口。
- 新增首次最小化到托盘的说明弹窗（`general.tray_hint_shown` 记忆）：告知 Windows 11 会把新图标放进 `^` 隐藏区、可拖到常显区，并提示可在设置里改回直接退出。`_hide_to_tray` 在托盘不可用时保持窗口打开并提示，避免窗口消失却无处恢复。

### 验证
- `pytest -q`：183 passed / 0 failed。
- 转场逐帧抓取（`tools/probe_r39_frames.py`）：第 1 帧（60ms）仍是旧深色画面 + 右上角小圆，第 2 帧（160ms）为光照边界推进，第 3 帧（900ms）完成浅色，全程没有整屏新主题的过渡帧。
- 托盘探针（`tools/probe_r39_theme_tray.py`）：`tray_visible=True icon_null=False`；`_hide_to_tray()` 后窗口不可见、`_restore_from_tray()` 恢复；把 `_tray` 置空后 `_hide_to_tray()` 会保持窗口可见（守卫生效）。

## v1.0.33 — 2026-10-09

退出询问默认启用，主题切换加入「日出 / 日落」转场。

### 退出选项为什么之前看不到
- 不是测试环境限制：`general.close_action` 的默认值是 `quit`，而关闭对话框只在值为 `ask` 且托盘可用时出现，所以默认路径直接退出、永不询问。
- 现在：默认 `ask`，首次关闭即弹窗（取消 / 最小化到托盘 / 直接退出，可勾选「记住我的选择」）；托盘不可用时自动隐藏托盘按钮；旧配置里被写成 `quit` 的一次性迁移为 `ask`（只迁移一次，之后尊重用户选择）；自动化测试通过 `sys.modules` 检测跳过弹窗。

### 主题切换动画
- 新增 `ThemeReveal`：截取切换前后两帧，以标题栏主题按钮为圆心做圆形揭示（620ms，OutCubic），边缘带暖色/暗色光环——切浅色是日出、切深色是日落。
- 与旧的整屏淡入相比：不建离屏合成、不触碰活动控件树，只在两张快照间裁剪绘制，滚动歌词时不掉帧。
- 设置 → 外观与主题 新增「主题切换动画」开关（默认开），并受「减少动画效果」约束。

### 验证
- `pytest`：183 passed / 0 failed（新增 2 个：默认关闭行为、主题转场几何）。
- 截图：`docs/screenshots/theme_transition.png`、`docs/screenshots/close_dialog.png`。

## v1.0.32 — 2026-10-09

列表行的标题/副标题改为按字体度量排版（在线结果用的紧凑行同样覆盖）。

### 根因
- `TrackDelegate` 里标题与副标题用的是**写死的像素盒**（标题 `center-19, h=20`、副标题 `center+1, h=16`；紧凑模式为 `-15/16` 与 `+1/14`）。字号放到 1.5 倍后，20px 的字形塞进 16px 的盒子，两行互相压住。上一轮只改了行高，没改这两处盒子的位置与高度。

### 改动
- 两行文字改为：`block_h = title.height + 2 + sub.height`，整块以行中心居中；标题盒与副标题盒都用 `QFontMetrics.height()`，不再有固定偏移。
- 紧凑（在线搜索结果）与普通（音乐库）两条分支共用同一套计算。

### 验证
- `pytest`：181 passed / 0 failed。
- 截图：`docs/screenshots/rows_normal_150.png`（音乐库）、`docs/screenshots/rows_compact_150.png`（在线结果紧凑行）。

## v1.0.31 — 2026-10-09

修掉放大字号后暴露的三处挤压：列表行、主题预览卡、播放栏控件分布。

### 改动
- 歌曲/搜索结果列表：行高改为按「封面 + 两行文字 + 内边距」计算（`theme().scaled`），1.5 倍时约 53px；标题与副标题不再互相压住。
- 设置「主题」预览：卡片高度由两行标签的 `QFontMetrics.height()` 推出，标签画在预览图下方，不再叠在卡片边上。
- 播放栏：列宽策略改为「只有中列吸收剩余空间」，左右两组保持自然宽度；封面信息区最大宽度收紧（`scaled(200)`），心形按钮紧跟歌曲信息，不再飘到中间。

### 验证
- `pytest`：181 passed / 0 failed。
- 截图：`docs/screenshots/songs_150.png`、`docs/screenshots/settings_150.png`、`docs/screenshots/playerbar_150.png`。

## v1.0.30 — 2026-10-09

分区导航与侧栏的图标改为「对齐文字墨迹」，而不是对齐行盒。

### 根因
- `AlignVCenter` 居中的是**字体盒**，而中文字形墨迹比字体盒中心低约 8px（ascent 里留了上方的空气）。图标却按行盒中心放置，于是图标整体偏高、看着「没对齐」。

### 改动
- 设置分区导航：图标中心 = `基线 − capHeight/2`，基线由 `QFontMetrics.ascent/descent` 推出；图标列宽与文字间距随字号缩放（1.5 倍时 18→27px、间距 3→4.5px 换算后墨迹间距约 10px）。
- 侧栏主导航使用同一规则。
- 实测（2560×1392、×1.5）：图标与文字墨迹中心差 **0–1px**（播放三角因形状为 2px），改前为 **8–9px**。

### 验证
- `pytest`：181 passed / 0 failed。
- 对照截图：`docs/screenshots/settings_nav_zoom.png`、`docs/screenshots/sidebar_nav_zoom.png`。

## v1.0.29 — 2026-10-09

统一排版管线：QSS 文本与自绘文本使用同一像素尺寸，布局改由字体度量驱动。

### 根因
- 界面里其实有**两套字号来源**：搜索框等原生控件继承 `QApplication` 字体（21px），而侧栏/列表等自绘文本走 `theme().font()`（约 16px）。同一个界面两种字号、两种观感，侧栏因此显得更粗更小。
- 行高、列宽、文字盒等大量常量是固定像素，按 16px 文本调的；字号一放大就互相挤压。

### 改动
- `Theme.px(size)` 成为唯一字号换算；`font()` 与 QSS 用的 `pt()` 都由它推导（`pt = px × 0.75`），并有测试锁定二者一致。
- 应用默认字体设为正文尺寸（`font(10)`），原生控件与自绘文本同高。
- 文字容器改为按 `QFontMetrics` 排布：播放栏 `TrackInfo`、播放栏高度、卡片文字盒（标题/副标题两行）、歌曲行高与固定列宽（按类型缩放）。
- 侧栏导航 400 / 选中 500，与搜索框一致。

### 验证
- `pytest`：181 passed / 0 failed。
- 2560×1392 截图：`docs/screenshots/songs_150.png`、`docs/screenshots/home_150.png`、`docs/screenshots/sidebar_weight.png`。

## v1.0.28 — 2026-10-09

侧栏导航字重与搜索框统一为常规字重。

### 调整
- 侧栏导航项：未选中 500 → **400**，选中 600 → **500**；歌单条目同步。与搜索框占位文字（常规 400）保持一致，不再显得偏粗。
- 「音乐库」「歌单」分组标题与品牌字标维持原字重。

### 验证
- `pytest`：181 passed / 0 failed。
- 对照截图：`artifacts/qa/r31/_nav.png`、`_field.png`（同窗口、同缩放）。

## v1.0.27 — 2026-10-09

宽窗口内容列限宽（居中/左对齐），避免 2K/4K 下列表与卡片被拉得过宽。

### 调整
- 新增 `CenteredBox(child, max_width, align)`：内容列超过上限后不再铺满，按 `align` 居中（歌曲/专辑类页面）或左对齐（设置页，紧接分区导航）。
- 歌曲页把「页面标题 + 表格」并入同一列（`theme().scaled(1180)`），标题与表头左边缘对齐，「添加音乐」贴列右缘。
- 设置页内容列上限 `theme().scaled(1040)`，左对齐分区导航右侧，卡片不再横跨整个窗口。

### 验证
- `pytest`：181 passed / 0 failed。
- 2560×1392 截图：`docs/screenshots/settings_150.png`、`docs/screenshots/songs_150.png`。

## v1.0.26 — 2026-10-09

设置导航图标与文字比例、设置行密度。

### 修复 / 调整
- 设置分区导航的图标改为随类型缩放（1.5 倍时 18→27px），图标列宽与文字起点同样按缩放换算，文字与图标共用一条竖轴；选中的字重从 600 降到 500，避免放大后显得过粗。
- 设置行上下留白与标题/说明行距改为按类型缩放（1.5 倍时 9→12px、2→4px），行不再贴在一起。
- 页面标题字重 700→600，减少大字号下的「厚重感」。

## v1.0.25 — 2026-10-09

放大字号后出现的文字重叠与错位。

### 修复
- **所有自绘标题改为按字体度量排布**：`PageHeader`（页面标题/副标题）、`EmptyState`（欢迎页图标/标题/说明/按钮）、播放栏 `TrackInfo`（歌名/歌手/徽章）不再用固定像素偏移，改为 `QFontMetrics.height()` 计算行高并整体居中，因此字号放大到 180% 也不会互相压住。
- **空状态按钮位置**：按钮原来固定在 `height/2 + 58`，字号变大后会压在说明文字上；现在跟在说明文字下方 12px。
- **导航图标随字号缩放**：侧栏与设置分区列表的图标尺寸、图标列宽、文字起始位置都由类型缩放换算（1.5 倍时图标 17→26px、行高 32→43px），图标与文字始终同一条轴线。
- 修复 `hushplayer/ui/pages/page.py` 缺少 `QRect` 导入导致自绘异常的问题。

## v1.0.24 — 2026-10-09

1440p 下字体仍然偏小：改为「整数像素 + 类型缩放」方案。

- 新增 `Theme.ui_scale` / `Theme.type_scale` / `Theme.pt()`：在 DPR=1.0（文字保持整数像素、不发虚）的前提下，把字号整体放大 50%（1440p，正文约 18px），并同步缩放 QSS 里以 pt 写死的字号。
- `display.recommended_type_scale()`：≥3200 宽 → 1.0（4K 本身用 150% DPR）、≥2400 → 1.5、≥2000 → 1.2、其余 1.0。
- 列表行高 46→50、玩家栏 90→94、侧栏 236→244，避免字号变大后拥挤。
- 设置侧栏图标/文字沿用 v1.0.23 的 20px 图标列对齐。

## v1.0.23 — 2026-10-09

第五轮反馈：关闭方式可询问、文字清晰度、设置侧栏对齐。

### 新增
- **关闭方式询问**：设置 → 常规 → 「关闭窗口时」新增「每次询问」（新默认）。关闭时弹出「直接退出 / 最小化到托盘 / 取消」，可勾选「记住我的选择」写入设置。

### 修复 / 调整
- **文字清晰度**：界面缩放默认改为 **100%**（1440p 及以下），避免 1.25 倍分数缩放把字形落在半像素上；实测文字边缘梯度 3.08 → 3.43（越锐利越高）。同时把字号下限抬高 0.6px 补偿 100% 下的视觉变小；仍可在设置里选 125%/150%。
- **设置侧栏图标与文字对齐**：图标改为固定 20px 图标列（18px 字形，垂直 +0.5px 光学校正），文字左边距 14+18+10=42px，所有行共用同一轴线。

## v1.0.22 — 2026-10-19

### 新增
- **ReplayGain 音量归一化**：读取本地文件 `REPLAYGAIN_TRACK_GAIN` / `REPLAYGAIN_ALBUM_GAIN`，按「关闭 / 按曲目 / 按专辑」修正输出增益（±12 dB 上限），不改变音量滑块与系统音量；在线流不处理。
- **切歌预加载**：播放开始 2.5s 后提前解析队列下一首在线歌曲，切换时直接使用解析结果，省掉解析往返；预加载失败的曲目在切换时自动回退到正常解析。

### 验证
- 本地切歌实测：`stopped → playing` **23 ms**（`tools/probe_r25_gap.py`）。
- `tests/test_replaygain.py`（标签解析、album 回落、无标签/缺失文件回退 1.0、引擎增益不影响滑块音量）、`tests/test_preload.py`（提前解析下一首、切歌复用结果）。
- 全量 **178 passed / 0 failed / 0 skipped**（`artifacts/junit_round25.xml`）。

## v1.0.21 — 2026-10-19

### 新增
- **迷你播放器**：托盘菜单「迷你播放器」或 `Ctrl+Shift+M` 切换到 380×118 置顶小窗，显示封面、歌名/歌手、上一首/播放/下一首、进度条；可拖动位置、双击或 Esc 返回主界面，位置写入 `general.mini_player_x/y`。

### 验证
- `tests/test_gui_smoke.py::test_mini_player_round_trip`（主窗隐藏 → 迷你窗显示 → 关闭后恢复）。
- 真实探针：播放中切换迷你窗，`next()` 切歌成功，关闭后主窗恢复，截图 `docs/screenshots/mini_player.png`。
- 全量 **175 passed / 0 failed / 0 skipped**（`artifacts/junit_round24.xml`）。

## v1.0.20 — 2026-10-19

### 新增
- **失效文件重定位**：设置 → 音乐库 → 「检查并修复…」。程序先按原相对路径在新文件夹里找，找不到再按文件名搜索并重新关联；只改数据库路径，不移动/删除任何文件。修复后会显示「已重新关联 N 首，仍有 M 首未找到」。

### 验证
- 新增 `tests/test_relocate.py`（3 例：检测丢失、按相对路径修复、按文件名找回）。
- 真实 GUI 探针：8 首失效 → 选新目录 → 0 首失效，且新目录写入扫描目录列表。
- 全量 **174 passed / 0 failed / 0 skipped**（`artifacts/junit_round23.xml`）。

## v1.0.19 — 2026-10-19

### 新增
- **沉浸式快捷设置**：沉浸模式右上角新增齿轮按钮，弹出菜单可直接「放大/缩小歌词」「显示翻译」「左对齐歌词」「切换封面舞台 / 全幕歌词」，无需退回主界面再进设置。
- **自绘控件无障碍名称**：图标按钮取提示文案、文字按钮随标签变化、播放键随状态在「播放/暂停」间切换；播放进度、音量、搜索框、歌曲列表都有可读名称，屏幕阅读器与 UI 自动化可识别。

### 验证
- 桌面歌词位置与字号记忆复核：写入 (320,210)/44px → 窗口恢复一致；拖动到 (410,260) 后设置落盘。
- 新增 `tests/test_accessibility.py`（5 例）；全量 **171 passed / 0 failed / 0 skipped**（`artifacts/junit_round22.xml`）。
- 真实 GUI：`docs/screenshots/immersive_quick_settings.png`；探针输出菜单项 6 条、字号 1.0→1.1→1.0。

## v1.0.18 — 2026-10-19

### 新增
- **批量操作条**：在歌曲/专辑/歌单/搜索等任何歌曲列表里选中 2 首以上，列表底部浮出操作条——播放所选、下一首播放、加入队列、收藏、加入歌单（歌单页额外提供「从歌单移除」）。
  选择数量实时显示，点「取消选择」收起；条自身的动作全部落到真实播放队列与音乐库，不是占位按钮。

### 测试
- 新增 `tests/test_selection_bar.py`（3 例：数量驱动显隐、歌单上下文移除按钮、列表选择联动）。
- 全量 **166 passed / 0 failed / 0 skipped**（`artifacts/junit_round21.xml`）。
- 真实 GUI：`docs/screenshots/selection_bar.png`；探针实测「下一首播放」后队列 3 首、「收藏」后我喜欢 0 → 3。

## v1.0.17 — 2026-10-19

第四轮优化（音源可观测性与可维护性）。

### 新增
- **音源健康度**：`hushplayer/online/health.py` 记录每个音源的解析成功/失败次数，写在 `source_health.json`；设置页的音源行显示「解析成功率 87%」「最近解析全部失败」等摘要，方便判断哪个插件该换。
- **订阅更新检查**：`SourceRegistry.preview_subscription(url)` 只读取订阅、比对已安装插件的 sha256，报告新增数量；设置页新增「检查订阅更新」按钮，导入过订阅后点一下即可发现新音源并按需安装。

### 测试
- 新增 `tests/test_source_health.py`（3 例）与订阅预检用例；全量 **163 passed / 0 failed / 0 skipped**（39.1 s，`artifacts/junit_round20.xml`）。
- 真实 GUI：`docs/screenshots/settings_health.png`。

## v1.0.16 — 2026-10-19

第四轮优化（续）：播放地址缓存、搜索去重、睡眠定时。

### 新增
- **播放地址缓存**：同一首歌 120 秒内重复播放/切歌回到上一首时复用已解析的播放地址（并跳过已过期链接），减少一次网络往返；可用「重新获取」或换歌强制刷新。
- **搜索去重**：同一首歌被多个音源返回时只保留第一条（同标题+歌手才算重复，Live/翻唱等版本仍保留），设置 → 在线音源可关闭。
- **睡眠定时**：设置 → 播放可选 15/30/60/90 分钟，到点自动暂停并复位为「关闭」。

### 修复
- 控制器在解析成功路径上统一走 `_apply_resolved()`，失败分支的 `tried` 参数不再丢失；缓存命中时同样复用音质递进与跨源回退逻辑。

## v1.0.15 — 2026-10-19

第四轮优化：下载中心与歌词手动搜索。

### 新增
- **下载中心页面**（侧栏「下载」）：进行中任务的实时进度（MB / 百分比）、取消、失败重试、从列表移除、下载历史、打开所在文件夹、清空已完成。`downloads` 服务新增 `retry()` / `remove()` 并在索引写入上加锁，修复两个任务同时完成时历史记录丢失的竞态。
- **歌词手动搜索/更换**：歌词页工具栏新增搜索按钮，可按「歌名 歌手」在 LRCLIB 搜索，列表显示来源、专辑、时长与是否带时间轴，右侧实时预览，选定后立即替换并写入缓存（下次打开优先使用你的选择）。

### 修复
- 下载服务 `_record_success` 的读-改-写现在持锁，避免并发完成时索引丢条目。
- 下载页行内进度更新改为就地刷新，不再因信号时序导致列表停留在旧状态。

## v1.0.13 — 2026-10-19

### 重新设计搜索页布局
- **本地与在线各自独立的空状态**：没有输入时只显示居中的引导（图标 + 标题 + 说明），
  不再出现空的「专辑 / 歌手 / 歌曲」标题和空表格；无结果时同一区域显示「没有找到结果」。
- **本地结果按「歌曲 → 专辑 → 歌手」排序**，歌曲列表按行数自适应高度（上限 420px），
  搜索「夜航」时先看到歌曲，再向下浏览专辑与歌手。
- **在线搜索工具栏合并为两行**：第一行是音源胶囊（可横向滚动）+「更多音源」+「管理音源」+
  「全部播放」；第二行是细状态（结果数 / 音源数 / 失败 / 超时）。搜索中这条状态会实时更新为
  「已找到 N 首 · 正在搜索 x/y 个音源…」。
- **最近搜索只在空闲时出现**：作为空状态的一部分展示，不再常驻占用一行；没有历史时自动隐藏。
- 「更多音源」在全部音源都已显示时自动隐藏；胶囊栏仍只收敛显示有结果的音源。
- 修复：`_run_local` 在播放器尚未初始化时抛 `AttributeError`（测试环境暴露），改为安全判空。

## v1.0.12 — 2026-10-19

### 新增
- **导入 MusicFree 订阅**（设置 → 在线音源 → 导入订阅）：粘贴 `mf.json` 订阅地址，
  自动解析 `{"plugins": [{"name", "url", "version"}]}`（兼容 `sources`/`data`/`items`
  以及纯数组），逐个下载并安装，返回「已安装 N / 重复 M / 失败 K」汇总；单个插件
  下载或安装失败不会中断其余条目，失败项会列出名称与原因。
- 订阅里每个插件仍走同一套校验：仅 http(s)、单文件 ≤2 MB、sha256 去重、写入用户数据
  目录，不执行插件代码（元数据只从源码头部解析）。

### 实现
- `hushplayer/online/registry.py`：`download_plugin_bytes()`（流式下载 + 2 MB 上限）、
  `subscription_entries()`（四种常见文档结构）、`SourceRegistry._install_bytes()`
  （落盘/去重/写注册表的统一入口，`install_file` 复用它）、`install_subscription()`。
- `hushplayer/ui/pages/settings.py`：新增「导入订阅…」行与 `_import_subscription()`
  （等待光标、失败 `QMessageBox`、成功 toast 汇总、自动刷新音源列表）。
- 测试：`tests/test_source_registry.py` 新增订阅结构解析、本地 HTTP 订阅安装（2 成功 + 1 失败）。

## v1.0.11 — 2026-10-19

在线搜索提速（面向 64 个音源的场景）。

### 修复
- **结果边返回边显示**：搜索结果按批渲染（60ms 节流），不再等全部音源返回后才一次性出现。
- **单音源超时 25s → 9s**，整轮搜索 12s 硬截止：超时音源计入「N 个超时」，界面不会因为一个卡住的插件而长时间空白。
- **并发控制**：同时最多 12 个音源在查询，按历史响应速度优先派发（快源先出结果）。
- **重查走缓存**：同一关键词 + 音源在 5 分钟内的结果直接复用，重复搜索近乎瞬时。
- **取消旧请求**：输入新关键词时取消上一轮的待处理请求，不再让旧查询占用运行时。
- **音源筛选栏**：结果返回后只显示有结果的音源胶囊（≤12 个），其余收进「更多音源」菜单；胶囊条支持横向滚动。

### 实测（本机 2560×1440）
| 场景 | 首个结果 | 全部完成 |
| --- | --- | --- |
| 8 个音源 | 0.72 s | 1.40 s |
| 64 个音源（真实搜索） | **0.57 s** | 2.19 s |
| 8 个音源 + 1 个卡 5 秒的插件 | **0.49 s** | 5.39 s（其余结果照常先显示） |

## v1.0.10 — 2026-10-19

在线音源列表可收起。

### 新增
- 「设置 → 在线音源」在音源超过 4 个时默认只显示前 4 个，末尾出现「展开全部音源（还有 N 个）」；
  展开后显示全部，并出现「收起音源列表」。
- 展开/收起状态写入 `online.sources_expanded`，重启后保持。

### 修复
- 重新填充列表时旧行用 `deleteLater()` 异步销毁，折叠瞬间会与新行重叠闪烁；改为先 `hide()` + `setParent(None)` 再销毁。

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
