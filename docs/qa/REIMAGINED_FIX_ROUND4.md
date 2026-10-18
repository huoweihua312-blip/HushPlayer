# 第四轮反馈整改（v1.0.4）

反馈来源：用户 2026-10-18 截图 + 一句话反馈「这个地方歌名展示不全，能不能调整一下下方的各个控件」。

## 现象

播放栏左侧显示 `colt.4…`，右侧被「酷狗」徽章占位，第二行是「正在获…」——歌名、歌手、
来源三者互相挤压。长歌名几乎不可读。

## 根因

1. `hushplayer/ui/widgets/playerbar.py` 的 `PlayerBar.resizeEvent()` 把信息区宽度硬编码为
   `260px`（窗口 ≥1000px）或 `190px`，与窗口宽度无关，长标题必然被裁。
2. 布局里 `layout.addWidget(self.info, 0, ...)` 的 stretch 是 0，剩余宽度全部给中间控制区。
3. `TrackInfo.paintEvent()` 把徽章画在标题同一行，并先从标题宽度里扣掉徽章宽度。
4. `_on_loading(True)` 直接用「正在获取播放地址…」替换歌手名，加载结束后不恢复。

## 修复

| 文件 | 改动 |
| --- | --- |
| `hushplayer/ui/widgets/playerbar.py` | 信息区宽度按窗口分级：≥1100px → 320–520；≥860 → 260–400；≥620 → 190–280；更窄 → 110–180。布局 stretch 改为信息区 5 / 控制区 5。 |
| 同上 | `TrackInfo.paintEvent()`：标题独占整行；徽章/状态徽章画在第二行、紧跟歌手名之后（`artist_metrics.horizontalAdvance(artist_text) + 8`）。 |
| 同上 | 新增 `TrackInfo.set_status()` 与 `_status`；缓冲中显示「缓冲中」强调徽章，结束后清空并 `_restore_subtitle()` 回填 `track.display_artist`；切歌时清空状态。 |
| `hushplayer/ui/widgets/common.py` | `paint_badge()` 支持命名色（`accent`/`danger`/`success`），修掉传入 `tone="accent"` 被当成颜色字符串而画成黑底的问题。 |

## 验证

- `tools/probe_r4_playerbar.py`（真实 `HushApp` + 真实 `PlayerBar`，通过 `bar._on_track()` 注入
  一条 36 字标题 + 「酷狗 · e4e9e2」来源的在线曲目）：
  - `artifacts/qa/r4/playerbar_long.png`：标题**完整**显示，徽章位于歌手名右侧；
  - `artifacts/qa/r4/playerbar_loading.png`：显示「王睿卓&加木  缓冲中」，歌手不再被覆盖；
  - `artifacts/qa/r4/playerbar_narrow.png`（764px）：标题仍显示 20+ 字，音量自动隐藏。
- 全量测试：**127 passed / 0 failed / 0 skipped**（`artifacts/junit_round4.xml`）。
- 截图已同步 `docs/screenshots/playerbar_long_title.png`、`playerbar_buffering.png`。
- 打包 1.0.4：`packaging/out/HushPlayer-1.0.4-win64.zip`，`tools/verify_package.ps1` 启动/单实例/退出验证。

## 遗留

- 标题仍为单行省略；极长标题（>60 字）在 1000px 以下窗口仍会截断，可后续加入 hover 显示完整标题的 tooltip。
