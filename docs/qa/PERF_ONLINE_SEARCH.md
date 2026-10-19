# 在线搜索性能优化（v1.0.11）

## 问题

用户启用 64 个在线音源后，搜索一次要几十秒才出现结果。

## 定位

1. `hushplayer/ui/pages/search.py` 的 `_finish_online()` 只有在**全部音源**返回后才 `set_tracks()`，
   期间界面只有「正在搜索 N 个音源…」。
2. 每个请求 `timeout=25000`：任何一个卡住的插件都会让整轮搜索最多等 25 秒。
3. 64 个请求一次性全部发出，没有并发上限，也没有按可靠性排序。
4. 旧查询不复用、不取消：连续输入会叠加请求。

运行时本身并不慢——`tools/probe_r11_search_perf.py` 直接对 64 个音源并发调用
`resolvePlayback/search`：首个结果 0.87 s、全部 1.68 s。慢的是 UI 的等待策略。

## 改动

| 项 | 之前 | 之后 |
| --- | --- | --- |
| 渲染 | 全部完成后一次 | 每批完成后 60ms 节流渲染（`_render_timer`） |
| 单源超时 | 25 s | 9 s（`SEARCH_PER_SOURCE_TIMEOUT_MS`） |
| 整轮截止 | 无 | 12 s（`_deadline_timer` → `_on_deadline()`，取消剩余请求并标注「N 个超时」） |
| 并发 | 全部同时 | 最多 12 个（`SEARCH_CONCURRENCY`），按历史耗时排序 |
| 缓存 | 无 | 5 分钟（`SEARCH_CACHE_TTL_S`），键 `(关键词, 音源)` |
| 取消 | 无 | 新查询取消上一轮 `client.cancel(request_id)` |
| 筛选栏 | 64 个胶囊溢出 | 只显示有结果的音源（≤12）+「更多音源」菜单 + 横向滚动 |

## 实测

| 场景 | 首个结果 | 全部完成 |
| --- | --- | --- |
| 8 个音源 | 0.72 s | 1.40 s |
| 64 个音源 | **0.57 s** | 2.19 s |
| 8 个音源 + 1 个 5 秒慢插件 | **0.49 s**（50 首） | 5.39 s（130 首） |

命令：
```powershell
.venv\Scripts\python.exe -u tools\probe_r11_search_perf.py 64
.venv\Scripts\python.exe -u tools\probe_r11_gui.py
.venv\Scripts\python.exe -u tools\probe_r11_slow.py
```

## 回归

`tests/test_search_incremental.py`：
- 首个音源返回后列表就应出现行，且 `_finished` 仍为 False；
- `_on_deadline()` 后 `_finished=True`、`_timed_out=2`、状态含「超时」、两个请求都被 cancel；
- 同一关键词再次搜索不产生新的 `client.search` 调用（走缓存）。

## 仍可继续优化

- 首次搜索仍需启动 Node 运行时（约 1.5 s，已在应用启动 400 ms 后预热）；
- 64 个插件的首次编译成本无法消除，可按使用频率懒加载；
- 若上游限流，个别音源会持续超时，可在音源设置里显示「近期失败次数」。
