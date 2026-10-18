# 架构说明

## 1. 技术选型与约束

| 维度 | 选择 | 理由 |
| --- | --- | --- |
| 语言 / 运行时 | Python 3.13 | 原版音源运行时（Node.js）可原样复用；Windows 打包成熟；团队与工具链已具备 |
| UI | PySide6 6.11 Widgets + 自绘 + QSS | 对标题栏、列表、歌词、封面舞台有像素级控制；避免重写 Electron/Web 带来的协调成本 |
| 音频 | `QMediaPlayer` + `QAudioOutput`（Qt FFmpeg 后端） | 支持 MP3/FLAC/WAV/AAC/M4A/OGG 等；与 Qt 事件循环一致；无额外原生依赖 |
| 数据 | SQLite（WAL） + JSON 设置 | 数千首歌的查询与事务可靠；设置/队列用小 JSON，便于人工排查与迁移 |
| 在线音源 | 复用的 Node.js JSONL 运行时 + Qt `QProcess` | 插件协议不变，升级音源不用改 PySide 代码 |
| 在线播放 | 本地 HTTP 代理 + 磁盘缓存 | 统一处理 header、Range、seek、长暂停恢复与缓存，不让 `QMediaPlayer` 直连远端 |
| 打包 | PyInstaller onedir（内置 Node 与音源运行时） | 用户无需安装 Python/Node；不使用 Velopack（用户明确要求） |

## 2. 分层

```
hushplayer/
  app.py               应用装配、启动/退出、设置联动、托盘与单实例接入
  version.py           版本、App ID、更新通道
  core/                与业务无关的基础设施
    paths.py           数据/缓存/日志/下载/资源路径，便携模式与可写回退
    settings.py        分层设置（点号键、原子写、备份、损坏恢复）
    theme.py           调色板、度量、字体、QSS、深浅色解析
    icons.py           自绘 SVG 图标库（颜色与透明度运行时注入）
    logging_setup.py   轮转日志 + faulthandler
    single_instance.py 命名互斥体 + 激活请求文件
  model/               领域模型（Track / Album / Artist / Playlist / Lyrics 文档）
  store/               SQLite 连接、迁移、仓储（曲目/歌单/歌词绑定/元数据）
  library/             扫描、元数据解析、封面存储与异步加载
  audio/               播放队列（顺序/随机不变量）、播放引擎、控制器
  online/              音源进程客户端、数据模型映射、本地 HTTP 缓存代理
  lyrics/              LRC/增强 LRC/YRC/QRC/KRC 解析、时间轴、歌词服务
  services/            面向 UI 的业务服务
    library.py         音乐库查询、收藏、歌单、扫描入口
    state.py           播放会话与队列持久化
    cache.py           缓存统计/清理/修复
    downloads.py       在线下载队列
    updater.py         更新检查（只提示，不静默安装）
    startup.py         开机自启（Startup 文件夹脚本）
  ui/                  表现层
    main_window.py     无边框主窗、导航、历史栈、托盘、快捷键
    immersive.py       沉浸式窗口（All Screen / Cover Stage）
    desktop_lyrics.py  桌面悬浮歌词
    context.py         服务容器（UI 单例，避免层层传参）
    theme 消费方        所有页面/控件通过 theme() 取色，不硬编码
    widgets/           标题栏、侧栏、播放栏、歌曲列表、封面、滑块、歌词视图、设置控件、队列面板…
    pages/             首页、歌曲、专辑、艺人、收藏、最近、歌单、搜索、歌词、设置、页面基类
  runtime/             随包分发的 Node 音源运行时与内置 node.exe（打包时）
tools/                 夹具生成、探测脚本、截图、迁移工具、图标/版本信息生成
tests/                 95 个自动化测试（单元 + 集成 + 真实网络）
packaging/             PyInstaller spec、manifest、启动器、构建脚本
```

依赖方向：`ui → services → (library|audio|lyrics|online|store) → core`；`core` 不反向依赖任何业务模块。UI 通过 `ui/context.py` 的 `AppContext` 取服务，因此页面可独立实例化与测试（`tests/test_gui_smoke.py` 就是手工装配 context 后跑真实窗口）。

## 3. 关键数据流

### 3.1 播放

```
双击歌曲 → TrackListWidget.play_requested
        → MainWindow/页面调用 PlayerController.play_tracks(tracks, index, context)
        → PlayQueue.set_tracks（保留界面顺序与播放顺序两套索引）
        → PlayerController._load(track)
            本地：engine.load(file://…)
            在线：client.resolve_playback → AudioProxy.register → engine.load(127.0.0.1/audio/<token>)
        ← engine 信号（position/duration/state/end_of_media/error）
        → PlayerController 转发 → 播放栏 / 队列面板 / 歌词页 / 沉浸式 / 桌面歌词 / 托盘
```

`PlayQueue` 的不变量：

- `_items` 永远是界面顺序；
- `_order` 是实际播放顺序；非随机时等于 `_items`，随机时以当前曲目为首洗牌；
- 增删、移动、插入下一首都会同步维护 `_order` 与 `_pos`，因此「接下来播放」预告与真实播放一致；
- 自动结束与手动切歌语义不同：`repeat=one` 时自动返回自身、手动前进到下一首；`repeat=all` 到尾部回绕并重洗。

### 3.2 在线播放缓存

```
client.resolve_playback(source, track)
  → {url, headers, mimeType, expiresAt}
  → proxy.register(cache_key, url, headers, …) → http://127.0.0.1:<port>/audio/<token>
      · 下载线程直接写最终文件，同目录 {token}.meta.json 标记 complete + size
      · HTTP 线程按 Range 读同一文件；未就绪时 wait_for(offset) 等待已写字节
  → QMediaPlayer 按需 Range 拉流，拖动进度即 seek
```

不使用「先写 .part 再改名」：Windows 上重命名正在被读取的文件会失败。完整性由 meta 索引判定，崩溃残留会被 `CacheService.repair()` 清理。

### 3.3 歌词

```
LyricsService.request(track)
  → 手动绑定 → 同目录 sidecar（含翻译文件） → 内嵌标签
  → 磁盘缓存 → 音源 getLyric → LRCLIB
  → parser.parse（LRC / 增强 LRC / YRC / QRC / KRC / 纯文本 / 纯音乐）
  → LyricsResult(document, status, provider)
  → LyricsPage / ImmersiveWindow / DesktopLyricsWindow 订阅 resolved
```

时间轴只使用真实时间戳：增强 LRC 的 `<mm:ss.xx>`、YRC/QRC/KRC 的 `(offset,duration)`。普通 LRC 没有词级时间时，按行进度在字符间插值（并在 FEATURES 中如实标注为「按行进度扫过」）。用户偏移叠加在文件 `[offset:]` 之上，写回数据库。

## 4. 线程模型

- **UI 主线程**：只做绘制与轻量状态更新，不读文件、不发网络请求。
- **扫描**：`Scanner` 在 `QThread` 中遍历、解析元数据、批量 upsert，按 40 个文件发一次进度。
- **封面**：`CoverProvider` 用 4 线程 `QThreadPool` 下载/解码，内存 LRU 400 项。
- **歌词**：LRCLIB 请求在 2 线程池；音源歌词走 Node 进程异步回调。
- **缓存/下载**：每个资源一个 `Download` 线程；下载队列在 `QThreadPool`。
- **音源进程**：单个 `QProcess`，按行 JSON 协议；每请求独立超时；退出时先 `shutdown` 再终止。

## 5. 数据与目录

| 内容 | 位置 | 是否可重建 |
| --- | --- | --- |
| SQLite（曲目/歌单/收藏/统计/歌词绑定） | `%LOCALAPPDATA%\HushPlayerReimagined\hushplayer.db` | 否（用户数据） |
| 设置 | 同上 `settings.json`（+ `.bak`） | 否 |
| 播放队列与会话 | 同上 `play_queue.json` | 部分 |
| 歌词缓存 | 同上 `cache\lyrics\` | 是 |
| 音频缓存 | 同上 `cache\audio\` | 是 |
| 封面缓存 | 同上 `cache\artwork\` | 是 |
| 下载 | 默认 `%USERPROFILE%\Music\HushPlayer Downloads`，可配置 | 否（用户文件） |
| 日志 | 同上 `logs\hushplayer.log`、`crash.log` | 是 |

设置与数据库刻意使用与旧版不同的目录名（`HushPlayerReimagined`），避免开发期间触碰真实旧数据；迁移由 `tools/migrate_legacy.py` 显式执行。

## 6. 有意为之的取舍

1. **不做实时高斯模糊**：封面取色在 24×24 缩略图上分桶完成，氛围光用径向渐变近似，避免每帧模糊的 GPU/CPU 开销。
2. **整库装入列表模型**：数千行时内存排序比分页 SQL 更简单、交互更顺；扫描与封面仍在线程中完成。
3. **不做静默更新**：用户明确不要 Velopack；更新只做「检查 → 提示 → 打开下载页」。
4. **不写注册表**：开机自启用 Startup 文件夹脚本，单实例用命名互斥体，均可逆、无需管理员权限。
5. **音频设备切换**用 `QMediaDevices` 枚举并重建 `QAudioOutput`，而不是依赖系统默认设备变化事件。
