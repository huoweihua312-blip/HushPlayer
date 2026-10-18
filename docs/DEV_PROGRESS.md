# 开发进度与续接说明

> 更新于 2026-10-18。下一位接手者（人或 AI）请先读本文件，再按「下一步」执行，不要从零重做。

## 当前状态：可交付

- 主窗口、12 个页面、播放栏、队列面板、沉浸式两种模式、桌面歌词、设置中心全部接入真实业务逻辑。
- 本地播放、在线播放（真实音源）、下载（酷我实测）、歌词（本地/内嵌/在线/LRCLIB/逐字双语）、收藏歌单、缓存、单实例、托盘、开机自启均已验证。
- 测试：`95 passed`（`docs/TEST_REPORT.md`）。
- 发布：`packaging/out/HushPlayer/HushPlayer.exe` 可启动，已截图 `docs/screenshots/packaged_light.png`。

## 已完成的里程碑

1. 研究旧项目（只读）：在线音源运行时、歌词与 UI 结构、缓存/设置布局。
2. 基础设施：路径、设置、主题、图标、日志、SQLite 仓储。
3. 音乐库：扫描、元数据、封面、聚合、搜索。
4. 播放：引擎、队列、控制器、本地+在线、代理缓存、跨音源回退。
5. 在线：Node JSONL 客户端、数据模型、真实能力探测、下载、更新检查。
6. 歌词：解析、服务、普通歌词页、沉浸式、桌面歌词。
7. UI：设计系统、标题栏/侧边栏/播放栏/列表/卡片/设置控件、全部页面。
8. 测试与打包：95 用例、PyInstaller onedir + 内置 Node、首启与退出验证。
9. 文档：README、FEATURES、ARCHITECTURE、TEST_REPORT、SCREENSHOTS、LICENSES、INSTALL、UPDATES、MIGRATION、KNOWN_ISSUES、DELIVERY。

## 下一步（按优先级）

1. **重建最终发布包**：`powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip -SkipTests`（代码有改动，现有 `packaging/out` 可能是旧构建）。
2. **复验发布包**：启动 exe → 加音乐目录 → 播放 → 在线搜索 → 打开沉浸式 → 关闭；检查日志无 traceback。
3. **修正文档口径**：README「任务栏进度」、FEATURES 单实例描述（见下「已知文档债」）。
4. **git 提交检查点**：`git add -A && git commit -m "..."`（不 push 远程）。

## 已知文档债

- `README.md` 第 29 行「任务栏进度」尚未实现，应删除或标注为未实现。
- `docs/FEATURES.md` 第 143 行写「单实例（QLocalServer 通知现有窗口）」，实际实现是 **Win32 命名互斥体 + 激活请求文件**（`hushplayer/core/single_instance.py`）。

## 关键文件地图

| 关注点 | 文件 |
| --- | --- |
| 应用入口/服务装配 | `hushplayer/app.py` |
| 主窗口/导航/快捷键/托盘 | `hushplayer/ui/main_window.py` |
| 播放控制 | `hushplayer/audio/controller.py`、`engine.py`、`queue.py` |
| 在线协议客户端 | `hushplayer/online/client.py`、`proxy.py`、`models.py` |
| 音源运行时（JS） | `hushplayer/runtime/source_runtime/` |
| 音乐库 | `hushplayer/library/`、`hushplayer/store/` |
| 歌词 | `hushplayer/lyrics/`、`hushplayer/ui/pages/lyrics.py`、`ui/widgets/lyrics_view.py` |
| 沉浸式/桌面歌词 | `hushplayer/ui/immersive.py`、`ui/desktop_lyrics.py` |
| 设置 | `hushplayer/core/settings.py`、`ui/pages/settings.py` |
| 打包 | `packaging/hushplayer.spec`、`build.ps1` |
| 截图工具 | `tools/shot_app.py` |
| 旧数据迁移 | `tools/migrate_legacy.py` |

## 当前轮次状态（v1.0.1 · 缺陷整改第一轮）

- 台账：[`docs/qa/REIMAGINED_FIX_ROUND1.md`](qa/REIMAGINED_FIX_ROUND1.md)；变更摘要：[`docs/CHANGELOG.md`](CHANGELOG.md)。
- 10 项用户反馈：9 项「已验证修复」，1 项（BUG-07 正式 Logo）「受阻（等待素材）」，机制已完成。
- 自动化：`119 passed`（`artifacts/junit_round1.xml`），既有 95 例未改动断言。
- 新增关键模块：`core/display.py`（高 DPI 缩放）、`core/brand.py`（品牌资源）、`audio/clock.py`（60 Hz 插值时钟）、`ui/widgets/sweep.py`（软边逐字扫过）。
- 重新生成的真实截图：`artifacts/shots/` → `docs/screenshots/`（34 张，含在线搜索、窄窗口、桌面歌词）。
- 打包：`packaging/out/HushPlayer-1.0.1-win64.zip`（见 `packaging/out/SHA256SUMS.txt`）。

### 后续可继续的方向

1. 收到正式 Logo 后放入 `assets/brand/`，跑 `pytest tests/test_brand.py` 并重打包。
2. 系统级媒体控制（SMTC）、任务栏缩略图按钮。
3. 大型音乐库（>2 万首）分页/代理模型。
4. 音源逐条进度与可取消的单音源搜索。
5. 安装向导（可选）与代码签名。

## 常用命令

```powershell
# 开发运行
.\.venv\Scripts\python.exe -m hushplayer

# 测试
.\.venv\Scripts\python.exe -m pytest

# 截图（真实 Windows 平台，非 offscreen）
.\.venv\Scripts\python.exe tools\shot_app.py

# 构建
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip
```

## 环境注意

- 本机 venv 的 python 无权写 `%LOCALAPPDATA%` 时，`paths.data_dir()` 会回退到项目 `Data/`（日志会写最终路径）。这解释了为什么开发期数据出现在仓库目录。
- 截图**不能**用 `QT_QPA_PLATFORM=offscreen`：Qt 该平台无字体目录，中文会渲染成方块。只有纯逻辑测试才用 offscreen。
- 修改 `hushplayer/runtime/source_runtime/*.js` 后必须 `node --check` 并重跑在线用例。
- 不要读取或修改旧项目目录与真实用户 AppData。

### v1.0.2（第二轮反馈）

- 已完成并验证：R2-01 闪屏（渲染层）、R2-02 幽灵窗口、R2-03 在线搜索与音源增删、R2-04 官方 Logo、R2-05 滑块卡顿、R2-06 主题过渡 + 日月按钮、R2-07 三角居中、R2-08 MiSans 字体、R2-09 最大化白边。
- 全量测试 120 passed；打包与 verify 见 `docs/qa/REIMAGINED_FIX_ROUND2.md` 与 `docs/TEST_REPORT.md` 第 9 节。
- 待人工确认：真实显示器上的闪屏观感、混合 DPI 拖动、字体主观一致性。
