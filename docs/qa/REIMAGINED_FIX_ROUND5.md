# 第五轮反馈整改（v1.0.6）

反馈来源：用户截图（歌词来源 · 酷狗 / 偏移 +1.0s）+ 一句话反馈
「偏移调整时，歌词会调到顶端然后再回到当前播放的歌词」。

## 现象

在歌词页点 `-` / `+` 调整偏移时，歌词列表先跳到第一行，约半秒后跳回当前播放行。

## 根因（三层）

1. `hushplayer/ui/pages/lyrics.py` 的 `set_offset()` 每次都会 `view.set_document(document)`，
   而 `LyricsView.set_document()` 无条件 `bar.setValue(0)` —— 直接把视图重置到顶部。
2. 文档重建后 `body.setMinimumHeight()` 改变内容高度，QScrollArea 的滚动范围在布局完成前
   仍是旧值/0，`setValue(previous)` 会被钳到 0；布局完成后才恢复。
3. 即使第 1、2 步修掉，`LyricsView.set_position()`（每次播放时钟 tick）与 `resizeEvent()`
   都会调用 `_scroll_to_index(active)`，在偏移变化导致活动行改变时再次把视图拉走。

## 修复

| 位置 | 改动 |
| --- | --- |
| `hushplayer/ui/widgets/lyrics_view.py` | `LyricsBody.position` 暴露当前歌词位置；`set_document(..., keep_position=False)` 新增参数，同一首歌重建时保留位置与滚动偏移，并暂存旧的 `maximum()` 防止钳 0。 |
| 同上 | 校准后的 1.5 秒内 `set_position()` 与 `resizeEvent()` 都不自动重定位（`_hold_scroll_until`），视口保持不动，仅活动行高亮变化。 |
| `hushplayer/ui/pages/lyrics.py` | 偏移路径显式传 `keep_position=True`；`_apply_result()` 对同一 `track_id` 的重复解析也传 `keep_position=True`（否则服务层缓存回写会再次把视图拉到顶部）。 |

## 验证

- `tools/probe_r6_offset.py`（真实 `HushApp`，本地 LRC 6 行，播放中执行 +300ms / -300ms）：
  `before=193`，调整后连续 40 帧采样值全部为 `193`（此前为 `0`，随后跳到 `11`），**PASS**。
  截图 `docs/screenshots/lyrics_offset_hold.png`。
- `tests/test_lyrics_view_scroll.py`：偏移重建保持滚动值、切歌归零，2 例通过。
- 全量测试 **129 passed / 0 failed**（`artifacts/junit_round6.xml`，33.1 s）。
- 打包 1.0.6 + `tools/verify_package.ps1` 启动/单实例/退出验证。
