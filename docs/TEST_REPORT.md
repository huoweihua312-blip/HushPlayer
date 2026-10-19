# 测试报告

> 本报告记录**真实执行**的结果。命令与输出均来自本机（Windows 10，Python 3.13.15，PySide6 6.11.1）。

## 1. 运行方式

```powershell
# 全量（含真实网络音源用例）
.\.venv\Scripts\python.exe -m pytest

# 只跑离线用例
.\.venv\Scripts\python.exe -m pytest -m "not network"

# 只跑需要真实音频/图形环境的集成用例
.\.venv\Scripts\python.exe -m pytest -m integration
```

`pytest.ini` 启用了 `--strict-markers`，自定义标记为 `integration` 与 `network`。

## 2. 最近一次全量结果

| 项 | 值 |
| --- | --- |
| 执行时间 | 2026-10-18 |
| 用例总数 | **119** |
| 通过 | **119** |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 0 |
| 总耗时 | **29.81 s**（波动属正常） |
| JUnit 原始结果 | `artifacts/junit_round1.xml` |

```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed in 28.66s   # 复跑：95 passed in 28.74s
```

## 3. 用例分布

| 文件 | 数量 | 覆盖内容 |
| --- | --- | --- |
| `tests/test_queue.py` | 16 | 队列顺序、随机不变量、循环模式、增删移动、快照往返 |
| `tests/test_library.py` | 12 | 元数据、封面、扫描错误、统计、聚合、搜索、排序分页、收藏、歌单 |
| `tests/test_lyrics_parser.py` | 12 | LRC/增强 LRC/YRC/QRC、偏移、逐词时间、纯文本、纯音乐、翻译合并 |
| `tests/test_downloads.py` | 8 | 落盘、索引、重名后缀、解析失败、HTTP 500、取消、文件名清洗 |
| `tests/test_settings.py` | 8 | 默认值、持久化、原子写、损坏恢复、未知字段、前缀重置 |
| `tests/test_gui_smoke.py` | 7 | 真实窗口构造、9 条路由、详情页、前进后退、主题、沉浸式、桌面歌词、播放栏 |
| `tests/test_lyrics_service.py` | 7 | sidecar、翻译文件、缓存、偏移钳制、离线回退、手动绑定 |
| `tests/test_updater.py` | 7 | 版本比较、清单解析、更新源缺失、坏 JSON、HTTP 503 |
| `tests/test_cache.py` | 5 | 统计、修复、清理、Range 206、完整性索引 |
| `tests/test_online.py` | 5 | 音源列表、真实搜索、`resolvePlayback`、未知音源错误、退出 |
| `tests/test_playback_state.py` | 4 | 解析中暂停取消、失败落 stopped、stop 取消迟到结果、`halt_pending` |
| `tests/test_clock.py` | 6 | 60 Hz 插值时钟：仅播放时 tick、位置插值、暂停冻结、时长钳制、reset |
| `tests/test_sweep.py` | 6 | 软边逐字扫过：面积随进度增长、亚字符步进、词时间轴、无词回退 |
| `tests/test_display.py` | 8 | 高 DPI 缩放：阈值推荐、auto 跟随物理屏、显式偏好、非法值、环境变量写入/清除 |
| `tests/test_brand.py` | 4 | 品牌资源回退链、多尺寸 `QIcon`、圆角 pixmap、`has_official_logo()` |
| `tests/test_playback.py` | 5 | 真实 WAV 播放、暂停、seek、结束事件、控制器切歌/循环/静音、会话恢复 |
| `tests/test_single_instance.py` | 3 | 命名互斥体、激活请求、环境变量旁路 |

## 4. 测试中发现并修复的真实缺陷（节选）

| 缺陷 | 修复 |
| --- | --- |
| 队列随机模式下 `set_tracks(start_index)` 忽略起始曲目 | 先记录选中曲目再洗牌，放到 `_order[0]` |
| `append()` 在随机模式随机插入，破坏「接下来播放」预告 | 一律追加到播放顺序末尾 |
| `insert_next()` 把当前指针移到新插入曲目 | 重建顺序后按 id 重算 `_pos` |
| `move_row()` 先移动后读当前曲目，读到错误项 | 先保存当前曲目再移动 |
| 重复导入同一文件误报 `added` | `upsert_many(return_counts=True)` 区分新增/更新 |
| WAV/AIFF 的 ID3 标签被误判为 Vorbis，标题歌手全空 | 按 `ID3`/`MP4Tags` 实例判断标签族 |
| klyric/QRC 文档 `kind` 为空，逐字高亮失效 | 显式设置 `kind="synced"`、`has_word_timing` |
| 无时间戳翻译文件无法合并 | 按行号 `zip` 回退合并 |
| `QLocalServer` 无法在 Windows 上可靠地做单实例 | 改用命名内核互斥体 + 激活请求文件 |
| 退出时封面线程仍向已销毁对象发信号 | `CoverProvider.shutdown()` + 发送前检查/忽略 |
| 队列面板取播放栏高度时把 `None` 当作属性名 | 直接走 `ctx().window.playerbar.height()` |
| 窄列表里隐藏列后表头与实际列错位 | 按真实列位置映射 `columnViewportPosition` |

## 5. 需要人工验收的项目

自动化无法可靠模拟真实音频设备、系统托盘与多显示器，以下项目已人工执行过一轮，仍建议按环境复验：

| 项目 | 步骤 | 通过标准 |
| --- | --- | --- |
| 音频输出 | 播放任一本歌曲目，拖动系统音量 | 有声音、进度前进、暂停后位置不动 |
| 音频设备切换 | 设置 → 播放 → 音频设备 切换 | 声音从新设备输出，不崩溃 |
| 媒体键 | 键盘播放/暂停、上一首、下一首 | 与播放器状态一致 |
| 系统托盘 | 关闭到托盘、双击托盘、托盘菜单 | 窗口恢复、播放状态正确 |
| 最小化到托盘 | 最小化窗口 | 任务栏隐藏，托盘可见 |
| 桌面歌词穿透 | 右键 → 鼠标穿透 | 鼠标可点到下方窗口，歌词可恢复 |
| 多显示器 / DPI | 拖到 150% 缩放显示器、切换主屏 | 布局不模糊、不越界，歌词位置被钳制回屏幕 |
| 单实例 | 启动 exe 两次 | 第二次退出，第一次窗口置前并提示 |
| 安装包完整性 | 解压 zip 到新目录运行 | 首启无缺库错误，能播放本地与在线歌曲 |

## 6. 未覆盖 / 已知测试空缺

- 自动更新下载与安装未实现，因此没有对应测试。
- 系统级 SMTC（Windows 媒体控制中心）未接入，媒体键走 Qt 快捷键。
- 极端规模（10 万首）未做压力测试；当前结论基于数千首级别的实测与设计。
- 网络用例依赖第三方音源可用性；音源失效时这些用例会失败或跳过，属外部变化，不是产品回归。

## 8. 第一轮缺陷整改（1.0.1）

针对用户录屏反馈的 10 项缺陷，逐项完成「复现 → 根因 → 修复 → 自动化 → 真实 GUI 验证」，台账见
[`docs/qa/REIMAGINED_FIX_ROUND1.md`](qa/REIMAGINED_FIX_ROUND1.md)。

| 编号 | 内容 | 状态 | 本轮新增自动化 |
| --- | --- | --- | --- |
| BUG-01 | 进入沉浸式黑帧/闪屏 | 已验证修复 | 动态帧检 `tools/probe_immersive_flash2.py`（首帧 `delta=0.00`） |
| BUG-02 | 在线播放暂停/停止失效 | 已验证修复 | `tests/test_playback_state.py`（4） |
| BUG-03 | 最大化/还原异常 | 已验证修复 | `tools/probe_maximize*.py`（QTest 真实点击 + 持久化） |
| BUG-04 | 在线使用中弹出错误对话框 | 已验证修复 | 真实 GUI 打开「在线音源」分区（`artifacts/qa/settings_online_loaded.png`） |
| BUG-05 | 2K 下界面偏小 | 已验证修复 | `tests/test_display.py`（8） |
| BUG-06 | 桌面歌词高亮不平滑 | 已验证修复 | `tests/test_clock.py`（6）+ `tests/test_sweep.py`（6）+ `tools/probe_sweep.py` 动态测量 |
| BUG-07 | 正式 Logo 缺失 | 受阻（等待素材） | `tests/test_brand.py`（4） |
| BUG-08 | 主题切换/预览卡 | 已验证修复 | 主题实时切换截图（`artifacts/qa/theme/`） |
| BUG-09 | 播放标识偏移 | 已验证修复 | 像素级对齐复核（`artifacts/qa/_idx_light.png`） |
| BUG-10 | 选中与播放撞色 | 已验证修复 | 状态矩阵截图（`artifacts/qa/rowstates_*.png`） |

回归：既有 95 例全部保持通过，未删除、未放宽断言；新增 24 例，合计 **119 例通过**。

## 7. 打包产物验收（真实执行）

在 `packaging/out/HushPlayer/HushPlayer.exe` 上执行 `tools/verify_package.ps1`（脚本会启动真实进程、截图、启动第二个实例、发送 `WM_CLOSE`）：

| 检查 | 1.0.1 结果 |
| --- | --- |
| 版本 | 日志 `启动 HushPlayer 1.0.1`，exe 文件版本同步 |
| 进程启动 | 成功，窗口 `1600×1025` 物理像素（1280×820 逻辑 × 125%），标题 `HushPlayer` |
| 高 DPI 缩放 | 日志 `界面缩放：125%（QT_SCALE_FACTOR=1.25）` |
| 内置 Node 运行时 | 日志 `online runtime started ...\_internal\hushplayer\runtime\node\node.exe`，随后 `runner ready` |
| 数据目录 | 通过 `HUSHPLAYER_DATA_DIR` 隔离到临时目录，未触碰真实用户数据 |
| 单实例 | 第二个实例检测到已有实例后退出，主实例日志「收到第二个实例的激活请求」，进程总数保持 1 |
| 优雅退出 | `WM_CLOSE` 后进程退出，日志「正在退出 HushPlayer」 |
| 截图 | `docs/screenshots/packaged_dark.png`（用 `PrintWindow` 抓取，避免被前台浏览器遮挡） |
| 产物 | `HushPlayer-1.0.1-win64.zip`（108,530,223 B）SHA256 `F94A4AC30E98D969C4AA3473890425A5046E228B825218BE97E54C7F381EDACF` |

原始日志：`artifacts/packaged_run/logs/hushplayer.log`（不随仓库提交）。

## 9. 第二轮反馈整改（1.0.2）

| 项目 | 数值 |
| --- | --- |
| 用例总数 | 120（119 + 品牌测试补充 1） |
| 结果 | 120 passed / 0 failed / 0 skipped |
| 耗时 | 29.949 s |
| JUnit | `artifacts/junit_round2.xml` |

新增/更新的自动化覆盖：

| 文件 | 覆盖点 |
| --- | --- |
| `tests/test_brand.py` | 官方 Logo 优先、brand 目录为空时回退占位资源、多尺寸 ico |

动态验证（脚本化，可复跑）：

| 脚本 | 结论 |
| --- | --- |
| `tools/probe_immersive_flash2.py` | 进入沉浸式首帧 `luma=37.86`，40–1400 ms 全部 `delta=0.00` |
| `tools/probe_r2_mode_switch.py` | Cover ↔ All Screen 各 3 次、61 帧采样，最差 `+0.1` 亮度差 |
| `tools/probe_r2_windows.py` | 输入文字前后顶层窗口数：2 → 1（幽灵窗口消失） |
| `tools/probe_r2_search.py` | 真实搜索 130 条、7 个音源、胶囊计数正确 |
| `tools/probe_r2_sources.py` | 音源删除 → 恢复：7 → 6 → 7 |

人工验收项见 [`docs/qa/REIMAGINED_FIX_ROUND2.md`](../docs/qa/REIMAGINED_FIX_ROUND2.md) 第 5 节。


## 10. 第三轮反馈整改（v1.0.3）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **127 passed / 0 failed / 0 skipped**，30.48 s（`artifacts/junit_round3_final.xml`） |
| 新增测试文件 | `tests/test_cross_source.py`（4 例：打分排序、跨源回退、音质递进、关闭回退）、`tests/test_theme.py`（3 例：整数像素与 hinting、字号下限、缩放单调性） |
| 更新测试 | `tests/test_playback_state.py` 改为整条音质链失败后必须落到 stopped 且给出错误提示 |
| 真实网络验证 | `tools/probe_r3_sources.py` 7 个音源搜索/解析；`tools/probe_r3_fallback.py` 酷狗 404 → 跨源播放 `state=playing`、`position=1665ms` |
| 真实 GUI | 首页/歌曲/设置 1600×1025（1280×820 @125%）截图重采；侧栏标志与关于页改为原版 SVG |
| 打包产物 | 1.0.3 onedir + zip，`tools/verify_package.ps1` 启动/单实例/退出验证 |

结论：第三轮 3 项可修反馈全部修复并验证；酷狗/QQ海棠的 404 与小米搜索异常属于插件依赖的第三方接口，
通过跨源回退保证同一首歌仍可播放，已在 UI 标明实际来源。


## 11. 第六轮反馈整改（v1.0.7）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **130 passed / 0 failed / 0 skipped**，32.8 s（`artifacts/junit_round7_final.xml`） |
| 新增回归 | `tests/test_gui_smoke.py::test_favorite_heart_does_not_break_favorites_page`（播放中在「我喜欢」点喜欢，捕获 Qt 槽内异常） |
| 测试隔离 | 单实例用例改用 `HUSHPLAYER_MUTEX_SUFFIX`，可与用户正在运行的正式版并存 |
| 真实窗口 | `tools/probe_r7_favorite.py`：`state=playing`、`favorites rows 1`、`errors 0`、PASS；截图 `docs/screenshots/favorites_playing.png` |
| 打包产物 | 1.0.7 onedir + zip；`tools/verify_package.ps1` 改为只操作自己启动的进程，并验证单实例拦截 |


## 12. 第七轮反馈整改（v1.0.8）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **133 passed / 0 failed / 0 skipped**，32.3 s（`artifacts/junit_round8.xml`） |
| 新增测试 | `tests/test_source_registry.py`：插件元数据解析、安装/去重/删除、错误类型与 2 MB 上限 |
| 真实 GUI | `tools/probe_r8_source.py`：安装 MusicFree 风格插件 → 列表出现「本地测试源」→ 运行时 `search()` 返回 1 条，`errors 0`；截图 `docs/screenshots/settings_installed_source.png` |
| 打包产物 | 1.0.8 onedir + zip，`tools/verify_package.ps1` 验证 |


## 13. 批量导入音源（v1.0.9）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **135 passed / 0 failed / 0 skipped**，31.5 s（`artifacts/junit_round9.xml`） |
| 新增测试 | `tests/test_source_registry.py` 增加 `collect_plugin_files` 与 `install_many`（含重复、坏文件） |
| 真实 GUI | `tools/probe_r9_batch.py`：文件夹内 3 插件 + 1 txt → 安装 2、跳过 1 重复、`errors 0`；截图 `docs/screenshots/settings_batch_import.png` |
| 打包产物 | 1.0.9 onedir + zip，`tools/verify_package.ps1` 启动/单实例/退出验证 |


## 14. 可收起音源列表（v1.0.10）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **138 passed / 0 failed / 0 skipped**，35.7 s（`artifacts/junit_round10.xml`） |
| 新增测试 | `tests/test_source_window.py`（短列表全显示、长列表折叠到 4、展开后全显示） |
| 真实 GUI | `tools/probe_r10_collapse.py`：折叠态 4 条 + 「展开全部音源（还有 3 个）」，展开态 7 条 + 「收起音源列表」；`errors 0` |
| 截图 | `docs/screenshots/sources_collapsed.png`、`sources_expanded.png` |


## 15. 在线搜索提速（v1.0.11）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **141 passed / 0 failed / 0 skipped**，33.6 s（`artifacts/junit_round11.xml`） |
| 新增测试 | `tests/test_search_incremental.py`（首个结果先渲染、超时收尾与取消、重复查询走缓存） |
| 性能探针 | `tools/probe_r11_search_perf.py`（8/64 音源）、`tools/probe_r11_gui.py`（真实窗口首帧）、`tools/probe_r11_slow.py`（含 5 秒慢插件） |
| 实测 | 64 音源：首个结果 0.57 s、全部完成 2.19 s；慢插件场景：0.49 s 先出结果、5.39 s 全部收尾 |


## 17. 搜索页布局重设计（v1.0.13）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **145 passed / 0 failed / 0 skipped**，35.1 s（`artifacts/junit_round13.xml`） |
| 新增用例 | `test_idle_state_shows_intro_not_results`（空闲态隐藏工具栏/状态、搜索切到结果页）、`test_local_search_switches_between_intro_and_results`（本地空/无结果切到引导页） |
| 真实 GUI | `tools/probe_r13_layout.py`：本地空闲、在线空闲、在线结果三态截图（125%，1600×1025） |
| 截图 | `docs/screenshots/search_local_empty.png`、`search_online_idle.png`、`search_online_results.png` |


## 17. 第五轮反馈（v1.0.23）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **179 passed / 0 failed / 0 skipped**，42.60 s（`artifacts/junit_round26_final.xml`） |
| 关闭方式询问 | 设置 → 常规 → 「关闭窗口时」新增「每次询问」；真实对话框截图 `docs/screenshots/close_dialog.png`（直接退出 / 最小化到托盘 / 取消 + 记住选择） |
| 文字清晰度 | 界面默认缩放 1440p 及以下改为 100%；同一文本的边缘梯度 3.08（125%）→ **3.43（100%）**；字号下限 +0.6px 补偿视觉大小 |
| 设置侧栏对齐 | 图标固定 20px 列（18px 字形 + 0.5px 光学校正），文字左边距 42px；`artifacts/qa/settings_general.png` 复核 |
| 打包产物 | `HushPlayer-1.0.23-win64.zip`，SHA256 `21D8ED7DE3A5C4C59892809C2532C6DF8DD82F0EC5C14D20A9F02D2BC11B536E`；verify 日志 `启动 HushPlayer 1.0.23`、`界面缩放：100%`、单实例、干净退出 |


## 18. 1440p 字号偏小（v1.0.24）

| 项目 | 结果 |
| --- | --- |
| 全量自动化测试 | **181 passed / 0 failed / 0 skipped**，41.30 s（`artifacts/junit_round27_final2.xml`） |
| 方案 | 保持 DPR=1.0（字形落在整数像素、不发虚），通过 `Theme.ui_scale` 把字号整体放大 50%（正文 10.5→18px），并同步 QSS 中 pt 字号；新增 `Theme.pt()` |
| 阈值 | `display.recommended_type_scale()`：≥3200 → 1.0，≥2400 → 1.5，≥2000 → 1.2，其余 1.0（4K 仍由 150% DPR 承担） |
| 布局 | 列表行高 46→50、播放栏 90→94、侧栏 236→244 |
| 新增测试 | `tests/test_theme.py::test_ui_scale_enlarges_type_without_changing_dpr`、`tests/test_display.py::test_type_scale_thresholds` |
| 截图 | `docs/screenshots/songs_dark.png`、`settings_light.png`、`lyrics_light.png`（100% DPR + 1.18 类型缩放） |


### 1.0.24 打包与验收

- 产物：`packaging/out/HushPlayer-1.0.24-win64.zip`（270.8 MB 解包），SHA256 `DDEE91C6ECA999B8D3BFD4355111F10580AEF20EA94622FBFAD679107160948B`。
- 启动日志：`界面缩放：100%（QT_SCALE_FACTOR=1.0）`、`应用主题：system → dark（字号缩放 ×1.50）`、窗口 2560×1392、单实例拦截、退出干净。
- 截图 `docs/screenshots/packaged_dark.png`（2560×1392，1.5 类型缩放）。
