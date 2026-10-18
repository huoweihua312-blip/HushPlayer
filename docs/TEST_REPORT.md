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
| 截图 | `docs/screenshots/packaged_dark_125.png`（用 `PrintWindow` 抓取，避免被前台浏览器遮挡） |
| 产物 | `HushPlayer-1.0.1-win64.zip`（108,530,282 B）SHA256 `359667F96CCE111AE0603B1C25A1FE04EBB2D215D639DB89D5D0C12828CDD0B2` |

原始日志：`artifacts/packaged_run/logs/hushplayer.log`（不随仓库提交）。
