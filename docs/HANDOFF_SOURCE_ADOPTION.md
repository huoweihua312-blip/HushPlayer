# 交接文档：让「双击播放」自动把歌曲来源改成实际播放源

> 目标读者：另一个 AI / 工程师。读完应能独立给出新方案或直接实现。
> 版本基线：HushPlayer 1.3.12（`F:\Projects\HushPlayer-Reimagined`，Python 3.13 + PySide6 6.11.1 + Node 音源运行时 + SQLite）。
> 本文只描述现状与可行方案，**没有任何代码改动**。

---

## 1. 用户要的效果（唯一验收标准）

播放一首在线歌曲时，如果它的原始音源失败（404/超时/无版权），程序自动去别的音源找到同曲并播放。
此时：

- **列表里的来源徽章、播放栏的来源** 必须变成「实际在播的那个源」；
- **数据库里这条歌曲记录的 source 字段** 也要变成实际源（下次播放直接从该源开始，不再回退）；
- 现有行为：只有右键「替换歌曲来源」会改，**双击播放不会改**（用户反复反馈，见 m19652 / m19681）。

歌曲 `id` 必须保持不变（收藏、歌单、历史都按 id 关联）。

---

## 2. 相关代码地图（1.3.12）

| 关注点 | 位置 |
| --- | --- |
| 播放控制器（解析/回退/记忆） | `hushplayer/audio/controller.py`（约 1300 行） |
| 播放队列 | `hushplayer/audio/queue.py` |
| 数据库写入 | `hushplayer/store/repository.py` |
| 业务层（库/封面/信号） | `hushplayer/services/library.py` |
| 右键替换来源 | `hushplayer/services/source_replace.py`、`hushplayer/ui/track_source_dialog.py` |
| 来源记忆 | `hushplayer/services/source_memory.py` |
| 音源健康度 | `hushplayer/online/health.py` |
| 主窗口/装配 | `hushplayer/app.py`（`HushPlayer`）、`hushplayer/ui/main_window.py` |

关键 API（真实签名）：

```python
# store/repository.py:195
def update_source(self, track_id: str, *, source_id: str, source_name: str,
                  remote_id: str, raw: dict | None = None, title: str = "",
                  artist: str = "", album: str = "", duration_ms: int = 0,
                  artwork_url: str = "", album_id: str = "", artist_id: str = "") -> None
# 只改来源相关字段，id 不变

# services/library.py:164
def replace_online_source(self, track_id: str, candidate) -> Track | None
# 内部：tracks.update_source(...) → covers.invalidate(updated.id) → track_updated.emit(updated.id)
# 右键「替换歌曲来源」就是走这条，已验证列表能刷新

# audio/queue.py:162
def replace_track(self, track: Track) -> bool
# 替换 _items[index] 与 _by_id[track.id]，发 changed；若替换的是当前项再发 current_changed(track)

# services/source_replace.py
@dataclass
class SourceCandidate:
    source_id: str; source_name: str; remote_id: str
    title: str; artist: str; album: str
    duration_ms: int; artwork_url: str
    score: int; raw: dict; note: str = ""

def plausible(track: Track, candidate: SourceCandidate) -> bool   # :171
```

`PlayerController.__init__` 只依赖 `engine/client/proxy/queue`，**没有 library 引用**；因此“写库”这件事必须由 `HushPlayer` 层做。

---

## 3. 当前播放链路（为什么双击不改来源）

```
UI → controller.play_track(track) / queue 切换
   → _load(track) → _resolve_online(track)
        ├─ 记忆别名命中  → _on_resolved(track, data, ..., alias_source)
        └─ 原源解析
             ├─ 成功 → _apply_resolved(track, data, source_id=track.source_id)
             └─ 失败 → _online_failed → _fallback_all_sources
                          ├─ 搜到别的源 → _on_fallback_resolved(track, match, response)
                          └─ 全都失败   → 报错
   → 音频真正开始播放：_on_state("playing")
        → _commit_memory_pending()   # 1.3.8 引入：只在这里写记忆，避免 404 假成功
```

- `_apply_resolved(..., source_id="")`（controller.py:750）知道“实际用的源”，但只用于 `active_source_changed` 和健康度，**不写库**。
- `_on_fallback_resolved`（:976）拿到 `match`（别的源的同曲 Track），只 `_memory_pending = (track, match)`（:1009），**不写库、不换队列对象**。
- `_commit_memory_pending`（:1079）写 `source_memory.remember_track / remember_source_map / set_preferred`，**仍然不写库**。

结论：**“实际播放源”从未离开控制器**。UI 上的徽章读的是 `Track.source_id`（旧值），所以永远显示旧源。

---

## 4. 方案 A（推荐）：播放成功后“晋升”来源

核心：复用右键已验证的写入路径，把触发点从“用户点击”换成“音频真正开始播放”。

### 4.1 控制器新增信号与状态

```python
# controller.py
played_source = Signal(object, object, str, str)  # track, payload, source_id, remote_id
```

- `_apply_resolved(source_id=...)` 里记录 `self._active_source_id`、`self._active_payload`、`self._active_remote_id`
  （remote_id 可从 `data`/track 里取；别名路径下取别名记忆里的 remote id）。
- `_on_fallback_resolved` 里记录 `match.source_id / match.remote_id / response`。
- `_commit_memory_pending()` 末尾：

```python
if self._active_source_id and self._active_source_id != track.source_id:
    self.played_source.emit(track, self._active_payload, self._active_source_id, self._active_remote_id)
```

### 4.2 主窗口接线（唯一写库点）

```python
# hushplayer/app.py (HushPlayer)
self.player.played_source.connect(self._on_played_source)

def _on_played_source(self, track, payload, source_id, remote_id):
    if not track or not source_id:
        return
    if source_id == track.source_id and remote_id == track.remote_id:
        return
    candidate = candidate_from_payload(track, payload, source_id, remote_id)  # 新增小函数
    if not plausible(track, candidate):
        return                      # 宁可只播放，也不把错误版本写进库
    updated = self.library.replace_online_source(track.id, candidate)
    if updated is None:             # 不在库里（极端情况）：只改内存对象
        track.source_id, track.source_name = source_id, candidate.source_name
        track.remote_id, track.raw = remote_id, candidate.raw
        updated = track
    self.player.queue.replace_track(updated)
    self.player.adopt_track(updated)          # 新增：_track=updated + active_source_changed
```

### 4.3 需要新增的两个小函数

```python
# services/source_replace.py
def candidate_from_payload(track, payload, source_id, remote_id) -> SourceCandidate:
    """把一次在线解析的 payload 转成 SourceCandidate（score=0，仅用于回填来源）。"""

# audio/controller.py
def adopt_track(self, track: Track) -> None:
    """播放中用同 id 的新记录替换当前对象（来源被改写后），并刷新播放栏。"""
```

### 4.4 为什么放在 `playing` 之后

1.3.8 的教训：音源可以返回一个 200 的 URL，随后流式请求 404。**只有 `_on_state("playing")` 才能证明“这次真的能播”**。放在更早（`_on_fallback_resolved`）会把死源写进库，用户下次又踩回退。

### 4.5 边界

| 场景 | 行为 |
| --- | --- |
| 同源同 remote id | 直接 return，不写库、不发信号 |
| `plausible()` 不过（标题/歌手/时长差太多） | 只播放，不改来源；status 提示「用其他版本播放，未更改来源」 |
| 歌曲不在 DB | 只更新内存 + 队列 + 播放栏，不写库 |
| 设置 `playback.adopt_played_source` 关闭 | 完全退回现状（可回滚） |

---

## 5. 备选方案与取舍

| 方案 | 做法 | 结论 |
| --- | --- | --- |
| B. 回退成功时立即写库 | `_on_fallback_resolved` 里直接 `replace_online_source` | ✗ 会把 404 假成功写进库（1.3.8 已证明） |
| C. 只在 UI 层覆盖显示 | 列表/播放栏加一层 “display_source” | ✗ 用户要的是记录真的变；下次播放仍从旧源开始 |
| D. 记忆即真相 | 只依赖 `source_memory` 的 alias | ✗ 这就是现状：显示不改、跨会话/换 key 就丢；用户已多次否定 |
| A. 播放后晋升（推荐） | 见上 | ✓ 与右键同一条路径，UI/DB/队列一次改齐 |

---

## 6. 这个功能改过哪些地方（避免重复踩坑）

- **1.3.3** 引入来源记忆（alias/source_map/preferred），`health.looks_broken`。
- **1.3.5** 切歌 double-resolve：`next()/previous()` 改为 `_silent_current`，并 `client.cancel(旧请求)`。
- **1.3.6** 记忆改多键：`track.id` / `r::{source}::{remote}` / `q::{source}::{norm(title)}::{norm(artist)}`。
- **1.3.7/1.3.9** alias 失败/宽匹配回退，记录健康度。
- **1.3.8** 记忆改为“真开播才写”（`_memory_pending` → `playing` 时 commit）。
- **1.3.12** 死别名只试一次：`health.recently_failed()`、失败清 `preferred`（`set_preferred("")` 曾是空操作）。
- 以上都在修「下次别再搜」，**没有任何一版修「这次把 source 写回」**——这就是用户一直说“没实现”的原因。

其它已知坑：

- `QColor("rgba(...)")` 在 Qt 里无效，必须用 `css_rgba()`；透明顶层窗不认 QSS 背景，需在 `paintEvent` 自绘。
- 原生 `QToolTip`/`QMenu`/`QMessageBox` 与主题不一致，项目内已有自绘替代（`ui/widgets/tooltip.py`、`popup.py`、`ui/dialogs.py`）。
- 列表选中高亮：每个单元格都要 `painter.setClipRect(option.rect)`，否则半透明叠加成“分块”。
- 打包后 Node 运行时日志被截断、单实例锁、`AGENTS.md` 必须用 PowerShell 写（venv Python 是 Low 完整性）。

---

## 7. 怎么验证（必须全过）

1. **单测 A**：KG 曲目 → 回退 WY → 触发 `_on_state("playing")` 后：
   `library.tracks.get(id).source_id == WY`、`queue.current.source_id == WY`、收到 1 次 `track_updated`。
2. **单测 B**：预置 alias=WY 的 KG 曲目，播放后 DB 同样变 WY。
3. **单测 C**：候选 `plausible()` 为 False 时，DB 不变。
4. **回归**：第二次播放该曲，`client.search` 调用次数为 0（不再搜源）。
5. **真机截图**：列表徽章 + 播放栏都显示新源，与右键替换后的截图一致（`docs/screenshots/` 有 1.3.x 基线）。
6. `pytest -q`（当前 285 passed）、`packaging/build.ps1`、`packaging/verify_package.ps1`。

测试环境：`.venv\Scripts\python -m pytest -q`；离线用 `tests/fakes.py` 的 `FakeClient`（可注入 per-source 的 search/resolve 行为）。

---

## 8. 给另一个 AI 的提示词（可直接粘贴）

> 你在 `F:\Projects\HushPlayer-Reimagined`（Python 3.13 + PySide6）里修一个功能：播放器自动回退到其他音源后，歌曲记录里的 `source_id/remote_id` 没有更新，导致列表徽章与下次播放仍用旧源。
> 已有可用路径：`LibraryService.replace_online_source(track_id, SourceCandidate)`（内部 `TrackRepository.update_source`，保持 `id` 不变，发 `track_updated`）+ `PlayQueue.replace_track(track)`。
> 约束：
> 1. 必须在 `PlayerController._commit_memory_pending()`（即 `_on_state("playing")` 后）才写库，避免把 404 的 URL 写成好源；
> 2. 只能改来源字段，不能改 `track.id`；
> 3. 必须过 `services/source_replace.plausible()`，防止把别的版本挂上来；
> 4. 提供 `playback.adopt_played_source` 开关（默认开）以便回滚；
> 5. 不改动 1.3.12 已修的记忆/健康度逻辑。
> 请给出：受影响的文件与函数、信号/状态设计、边界处理、3 个单测（回退、别名命中、plausible 失败）、以及如何验证 UI 与 DB 一致。先给方案，不要直接改代码。

---

## 9. 验收后的发布清单

版本号 `hushplayer/version.py` → `CHANGELOG.md` 顶部新增小节 → `AGENTS.md` §9（PowerShell 写）→ `pytest -q` → `packaging/build.ps1` → `packaging/verify_package.ps1`（记录 window/instances/alive/`启动 HushPlayer x.y.z`）→ 复制 zip 到 `F:\HushPlayerBuild\out` → 计算 SHA256 → 提交并推 `main`（`git push origin main`；`main` 是唯一长期开发分支）。
