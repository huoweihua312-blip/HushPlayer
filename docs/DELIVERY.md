# 交付总结

## 1. 这是一次重写，不是换肤

HushPlayer Reimagined 与旧版共享的只有**在线音源的宿主协议与插件生态**。界面、播放控制、数据库、歌词、缓存、沉浸式与桌面歌词全部重新设计实现：

| 维度 | 旧版 HushPlayer | Reimagined |
| --- | --- | --- |
| 定位 | 功能迭代中的 PySide6 播放器 | 从产品与设计出发的完整重写 |
| 界面 | 多轮 UI 实验叠加 | 统一设计系统（色板、间距、圆角、字体、动画时长） |
| 歌词 | 仅 LRC，逐字按字数**估算** | 真实逐字/逐词时间（增强 LRC/YRC/QRC），双语、翻译、偏移 |
| 沉浸式 | 概念原型 | 两种真实模式（全幕歌词 / 封面舞台），封面取色环境光 |
| 队列 | 界面顺序即播放顺序，随机常错位 | `_items`（显示序）与 `_order`（播放序）分离，随机有严格不变量与测试 |
| 在线播放 | 直接交给播放器拉远端 URL | 本地 HTTP 代理 + 磁盘缓存 + Range + 完整性问题修复 |
| 数据 | 迁移多次的 schema | 新 schema、WAL、事务、原子写，与程序分离 |
| 更新 | 曾尝试 Velopack | 轻量清单检查，只提示不静默安装 |

## 2. 复用了什么

- **在线音源运行时**：`source_runtime/runner.js`、`plugin_host.js` 及其 `node_modules`、`source_registry.json` 与已安装插件，从旧项目复制后独立维护。协议（JSONL）保持不变，因此新旧插件兼容。
- **对旧实现的修正**：`normalizeResolvedResource` 处理插件返回字符串 URL / `false` 的情况；错误文案更明确。这些改动只在新项目里。
- **研究结论**：旧版歌词按字符数估算时间、在线歌词链路（音源 `getLyric` → LRCLIB → 缓存）、QProcess 客户端结构、缓存与设置的文件布局，都被阅读并作为参考，但代码为重新实现。

## 3. 重新实现的部分

- `hushplayer/core/`：路径（含便携/回退链）、设置（点号键、原子写、损坏恢复）、主题（深浅色、字体、动效）、图标（40+ 自绘 SVG）、日志。
- `hushplayer/store/`：SQLite schema、仓储、FTS 搜索、歌单与收藏关系。
- `hushplayer/library/`：扫描器（增量、跳过未变文件、失效清理）、元数据与封面提取、内容寻址封面缓存。
- `hushplayer/audio/`：`QMediaPlayer` 封装、队列（随机/循环/快照/恢复）、控制器（在线解析、代理注册、跨音源回退、长暂停重解析）。
- `hushplayer/online/`：Node JSONL 客户端（QProcess、超时、取消、优雅退出）、数据模型、本地音频代理与缓存。
- `hushplayer/lyrics/`：LRC/增强 LRC/YRC/QRC 解析、逐词/逐字进度、双语与翻译合并；歌词服务（sidecar、内嵌、缓存、音源、LRCLIB、偏移、手动绑定）。
- `hushplayer/services/`：音乐库服务、播放会话持久化、缓存管理、下载、更新检查、单实例、开机自启。
- `hushplayer/ui/`：主窗口、标题栏、侧边栏、播放栏、队列面板、12 个页面、列表/卡片/滑块/歌词/设置控件、沉浸式窗口、桌面歌词窗口、Toast。
- `tools/`、`tests/`、`packaging/`、`docs/`：全部新增。

## 4. 交付物清单

| 交付物 | 位置 | 状态 |
| --- | --- | --- |
| 完整源码 | `hushplayer/`、`tools/`、`tests/`、`packaging/` | ✅ |
| Windows 可运行程序 | `packaging/out/HushPlayer/HushPlayer.exe` + `HushPlayer-1.0.0-win64.zip` | ✅ 已启动验证 |
| 单元/集成测试 | `tests/`（95 用例），报告 `docs/TEST_REPORT.md` | ✅ 真实执行 |
| 真实界面截图 | `docs/screenshots/`（35 张，深浅色） | ✅ 真实窗口抓取 |
| 功能说明 | `docs/FEATURES.md` | ✅ 含完成度与音源能力矩阵 |
| 架构说明 | `docs/ARCHITECTURE.md` | ✅ |
| 安装/启动/卸载 | `docs/INSTALL.md` | ✅ |
| 更新机制 | `docs/UPDATES.md` | ✅ |
| 旧数据迁移 | `docs/MIGRATION.md` + `tools/migrate_legacy.py` | ✅ 预览/备份/回退 |
| 依赖与许可 | `docs/LICENSES.md`、`LICENSE` | ✅ |
| 已知问题 | `docs/KNOWN_ISSUES.md` | ✅ |
| 开发进度与续接 | `docs/DEV_PROGRESS.md` | ✅ |

## 5. 与旧版的主要行为差异（用户可感知）

1. 数据目录换成 `HushPlayerReimagined`，首次启动是空库，旧收藏需用迁移工具导入。
2. 在线播放先落到本地缓存，拖动进度与长暂停恢复更稳。
3. 随机播放的「即将播放」列表与实际播放一致。
4. 歌词逐字高亮按真实时间，不再按字数匀速猜测。
5. 下载只在支持下载的音源出现；不支持的音源不显示该菜单项。
6. 关闭行为、最小化到托盘、开机自启都在设置里可配，且不写注册表。
7. 更新只提示，不自动替换程序。

## 6. 后续可以继续做的方向

- 接入 Windows SMTC（系统媒体控制中心）与任务栏缩略图按钮。
- 大型库（>2 万首）分页/虚拟化与封面懒加载压力测试。
- 歌词编辑器（逐行微调、双语对齐、导出）。
- 音频可视化与均衡器（需评估 QtMultimedia 后端能力）。
- 安装向导（MSI/Inno Setup）与代码签名，配合自动更新。
- 音源管理界面（安装/更新/禁用插件，显示每个音源的真实能力探测结果）。
- 更细的缓存策略（按码率分层、LRU 淘汰可视化）。
