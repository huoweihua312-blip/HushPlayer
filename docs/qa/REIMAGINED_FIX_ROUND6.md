# 第六轮反馈整改（v1.0.7）

反馈来源：用户 2026-10-19 截图 + 「点击喜欢按钮时报错」。

## 现象

在「我喜欢」页面（且正在播放）点击歌曲行的心形 / 播放栏心形后，弹出应用自带的未捕获异常对话框：

```
HushPlayer 遇到了问题 - HushPlayer
AttributeError: 'TrackListWidget' object has no attribute 'ensure_current_visible'
  File "hushplayer/ui/pages/trackpage.py", line 103, in reload
  File "hushplayer/ui/pages/trackpage.py", line 134, in _sync_current
```

## 根因

`TrackListPage._sync_current()` 在「播放中」会调用 `self.list.ensure_current_visible()` 让当前曲目
滚入视野。但页面嵌入的是复合控件 `TrackListWidget`（内部包着 `TrackTable`），它只透传了
`set_tracks/set_favorites/set_current/...`，**漏掉了 `ensure_current_visible`**。

收藏状态变化会触发 `favorites_changed` → 页面 `reload()` → `_sync_current()`，于是每次在播放中点
喜欢都会命中这一行。异常发生在 Qt 定时器槽中，被 `sys.excepthook` 捕获后弹出模态对话框。

## 修复

- `hushplayer/ui/widgets/tracklist.py`：`TrackListWidget` 增加
  `ensure_current_visible()` → `self.table.ensure_current_visible()`。
- 审计：脚本比对 `TrackTable` 与 `TrackListWidget` 的方法集合，并扫描所有 `hushplayer/ui` 下
  `self.list.<name>(` 调用，确认无其它缺失透传。
- 回归测试：`tests/test_gui_smoke.py::test_favorite_heart_does_not_break_favorites_page`
  （导入夹具 → 播放 → 打开「我喜欢」→ 点喜欢 → 强制 `_sync_current()`，用 `sys.excepthook`
  捕获槽内异常，断言为空且列表出现该曲目）。

## 验证

- 真实窗口探针 `tools/probe_r7_favorite.py`（临时数据目录、真实播放）：`state=playing`、
  `favorites rows 1`、`errors 0`、`RESULT PASS`；截图 `docs/screenshots/favorites_playing.png`。
- 单实例测试隔离：新增 `HUSHPLAYER_MUTEX_SUFFIX` 环境变量，测试与打包验收各用自己的互斥体，
  不再与用户正在运行的正式版冲突；`tools/verify_package.ps1` 只跟踪自己启动的进程，不再
  `Stop-Process` 所有 HushPlayer。
- 全量测试：**130 passed / 0 failed / 0 skipped**（`artifacts/junit_round7.xml`）。
- 打包 1.0.7：`packaging/out/HushPlayer-1.0.7-win64.zip`。

## 额外说明

这个缺陷在 1.0.0 起就存在，只是需要「播放中 + 在收藏页点喜欢」才会触发，此前的冒烟测试没有
覆盖该组合。现在收藏页的交互已纳入自动化回归。
