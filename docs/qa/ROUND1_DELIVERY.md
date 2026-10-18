# 第一轮缺陷整改 · 交付报告（1.0.1）

- 日期：2026-10-18
- 基线：`1.0.0`（commit `695a4c2`）
- 本轮：`1.0.1`，聚焦用户录屏反馈的 10 项缺陷 + 7 项巡检发现
- 详细台账：[`REIMAGINED_FIX_ROUND1.md`](REIMAGINED_FIX_ROUND1.md)
- 变更摘要：[`../CHANGELOG.md`](../CHANGELOG.md)

## 1. 结论

| 指标 | 结果 |
| --- | --- |
| 用户反馈缺陷 | 10 项：**9 项已验证修复**，1 项受阻（正式 Logo 等待素材） |
| 自动化测试 | **119 passed / 0 failed / 0 skipped**（新增 24 例，既有 95 例未改动断言） |
| 真实 GUI 验收 | 深浅主题、行状态矩阵、设置各分区、在线搜索、沉浸式首帧、桌面歌词扫过、125% 缩放、打包版启动均留证 |
| 打包产物 | `packaging/out/HushPlayer-1.0.1-win64.zip`（108,530,223 B，SHA256 `F94A4AC30E98D969C4AA3473890425A5046E228B825218BE97E54C7F381EDACF`） |
| 版本 | `1.0.1`（exe 文件版本同步） |

## 2. 逐项状态

| 编号 | 缺陷 | 状态 | 关键证据 |
| --- | --- | --- | --- |
| BUG-01 | 进入沉浸式闪屏 | 已验证修复 | 录屏 0.4 s 黑帧（亮度 33.2）→ 修复后首帧 `delta=0.00`；`artifacts/qa/immflash/window/000_immediately.png` |
| BUG-02 | 网易云暂停/停止失效 | 已验证修复 | 失败后卡 `loading`；修复后失败落 `stopped`；酷我/网易可用曲 pause/resume/stop 全通过；`tests/test_playback_state.py` |
| BUG-03 | 最大化/还原异常 | 已验证修复 | 信号重复连接导致双击触发；修复后点击最大化 2560×1392、还原 1280×820，持久化正确 |
| BUG-04 | 在线使用中弹错误框 | 已验证修复 | 录屏 1:35 对话框 `AttributeError: 'dict' object has no attribute 'id'`；修复后设置→在线音源正常列出 7 个插件 |
| BUG-05 | 2K 下界面偏小 | 已验证修复 | 新增物理分辨率自动缩放；打包版日志 `界面缩放：125%`，窗口 1600×1025 |
| BUG-06 | 桌面歌词高亮不平滑 | 已验证修复 | 60 Hz 插值时钟 + 像素级软边扫过；动态测量 19 步、无回退、无 >20 px 跳变 |
| BUG-07 | 正式 Logo 缺失 | **受阻（等待素材）** | 资源机制与文档就绪；`assets/brand/README.md` |
| BUG-08 | 主题切换/预览卡 | 已验证修复 | 深色下卡片不再发白；三张迷你窗口预览卡；开关关闭态配色修正 |
| BUG-09 | 播放标识偏移 | 已验证修复 | 均衡器条与序号右基线对齐（4× 像素复核） |
| BUG-10 | 选中与播放撞色 | 已验证修复 | 选中行整行低透明度莓果底 + 深/白标题；对比度 15.8:1 / 14.2:1，播放标题 4.58:1 / 5.78:1 |

## 3. 主要代码改动

| 领域 | 文件 |
| --- | --- |
| 播放状态机 | `hushplayer/audio/controller.py`、`hushplayer/audio/engine.py` |
| 平滑歌词时钟 | `hushplayer/audio/clock.py`（新增）、`hushplayer/app.py`、`hushplayer/ui/context.py` |
| 软边逐字扫过 | `hushplayer/ui/widgets/sweep.py`（新增）、`hushplayer/ui/widgets/lyrics_view.py`、`hushplayer/ui/desktop_lyrics.py` |
| 窗口最大化 | `hushplayer/ui/widgets/frameless.py`、`hushplayer/ui/widgets/titlebar.py`、`hushplayer/ui/main_window.py` |
| 沉浸式首帧 | `hushplayer/ui/immersive.py` |
| 列表视觉 | `hushplayer/ui/widgets/tracklist.py`、`hushplayer/core/theme.py` |
| 设置中心 | `hushplayer/ui/pages/settings.py`、`hushplayer/ui/widgets/settings_widgets.py` |
| 高 DPI 缩放 | `hushplayer/core/display.py`（新增）、`hushplayer/app.py`、`hushplayer/core/settings.py` |
| 品牌资源 | `hushplayer/core/brand.py`（新增）、`assets/brand/README.md`、窗口/托盘/侧栏/关于页接线 |
| 验证工具 | `tools/probe_immersive_flash2.py`、`tools/probe_maximize*.py`、`tools/probe_pause_online.py`、`tools/probe_sweep.py`、`tools/probe_theme_live.py`、`tools/probe_rowstates.py`、`tools/probe_settings_online.py`、`tools/verify_package.ps1`（PrintWindow 抓图） |

## 4. 真实运行与性能

- 启动（打包版，125% 缩放）：18:09:20.548 启动 → 18:09:21.153 主窗口就绪（约 **0.6 s**）；Node 运行时 18:09:22.374 就绪（约 1.8 s，含插件加载）。
- 切歌/暂停/停止：见 `tools/probe_pause_online.py` 输出（位置冻结/恢复/归零准确）。
- 歌词动画：60 Hz 时钟 + 仅歌词控件局部 `update()`，未引入整窗重绘；窗口隐藏时不更新。
- 退出：`WM_CLOSE` 后进程退出、日志「正在退出 HushPlayer」、无残留 node 子进程。
- 单实例：第二实例立即退出并触发主实例激活（日志「收到第二个实例的激活请求」）。

## 5. DPI 与分辨率验收

| 场景 | 结果 |
| --- | --- |
| 2560×1440 / 100%（本机） | auto → 125%，窗口 1600×1025，字号/行高/图标等比，无重叠 |
| 1920×1080 | 自动 100%（阈值逻辑 + 单元测试） |
| 3840×2160 | 自动 150%（阈值逻辑 + 单元测试） |
| 手动覆盖 | 设置 → 外观 → 界面缩放，重启后生效；`appearance.ui_scale` 持久化 |
| 小窗口 960×680 | `docs/screenshots/narrow_*.png`，列按宽度隐藏，播放栏收缩 |

## 6. 未解决 / 风险

1. **BUG-07**：正式 Logo 未提供；当前占位，投放后需重打包（步骤见 `assets/brand/README.md`）。
2. **肉眼看闪**：DWM 合成后的画面无法在无人值守环境录制（gdigrab 抓不到应用窗口），已用窗口首帧证明，最终确认列入人工验收。
3. **网易云版权限制**：部分曲目无可用播放资源，属上游能力；已做跨音源回退与明确提示。
4. **混合 DPI 多显示器**：Qt 会在跨屏时重建部分绘制资源，可能有短暂重绘；未在本轮实测第二块物理屏。
5. **与 1.0.0 的风险对比**：本轮改动集中在「状态机 / 窗口几何 / 绘制时序 / 缩放」四类；未改动在线音源运行时协议、数据库结构与用户数据格式，**升级不需要迁移数据**，`play_queue.json`/`settings.json` 向后兼容（新增字段有默认值）。

## 7. 人工验收清单

见 [`REIMAGINED_FIX_ROUND1.md`](REIMAGINED_FIX_ROUND1.md) 第六节（9 条），以及 `docs/KNOWN_ISSUES.md` 中的说明。
