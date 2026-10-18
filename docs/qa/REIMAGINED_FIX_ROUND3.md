# 第三轮反馈整改（v1.0.3）

来源：用户 2026-10-18 第三轮反馈（4 项）。这轮的重点不是界面改版，而是**清晰度**、
**字号可调范围**、**在线音源播放可靠性**与**品牌素材一致性**。

## 一、逐项状态

| 编号 | 严重程度 | 反馈 | 复现与证据 | 根因 | 修复 | 自动化测试 | 真实 GUI 验证 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R3-01 | 高 | 字体与窗口不够清晰；字体调节范围偏小 | 打包版 1.0.2 在 2560×1440 / 系统 DPI 96（100%）下以 `QT_SCALE_FACTOR=1.25` 渲染；正文 10.5px、次级文字 8.4px、徽章 7.4px，1.25 倍后仍偏细；设置里字号只能 85%–120% | ①小字号 + 细字重在 1.25 倍下笔画不足；②`QFont` 未显式要求 full hinting，小字号落在半像素上发虚；③字号上限太低 | `hushplayer/core/theme.py`：`font()/mono_font()` 增加 `PreferFullHinting`、`Kerning`，新增 `FONT_LEGIBILITY_BONUS = 0.4` 与 11px 下限（8.4→11、10.5→13.6 逻辑像素）；`hushplayer/ui/pages/settings.py` 字号范围 0.80–1.80，歌词字号 0.70–2.00 | `tests/test_theme.py`（字体像素取整与单调性） | `artifacts/shots/home_dark.png`、`songs_light.png`、`settings_*.png`（1600×1025 = 1280×820@125%），文字明显变大变实 | 已验证修复 |
| R3-02 | 高 | 原版各音源都能播，移植后部分音源不能播 | `tools/probe_r3_sources.py`：7 源 `play=True`；酷狗、QQ海棠对 standard/higher/320k/flac/128k 全部 404；小米搜索抛 `Cannot read properties of undefined (reading 'map')`；酷狗 raw 无 `hash` 字段。**在 runtime 目录直接 `require("./plugin_host.js")` 调 `resolvePlayback` 同样 404**，证明与本移植无关（插件调用的第三方接口变了） | 移植本身没有破坏协议；缺的是原版 `OnlineTrackRecoveryService` 的「同曲跨源找回」行为，导致单源 404 时直接失败 | 新增 `hushplayer/online/matching.py`（NFKC+casefold 归一化；标题/歌手/专辑/时长加权，`AUTO_MIN_SCORE=80`、`AUTO_MARGIN=15`、`CANDIDATE_MIN_SCORE=55`）；`hushplayer/audio/controller.py` 增加 `QUALITY_CHAIN=("standard","higher","320k")` 音质递进、`_fallback_all_sources()` 并行搜索所有未试音源并按分数切换、16.5s 看门狗避免卡在 loading、`_play_candidate()` 保留原队列曲目与来源标识 | `tests/test_cross_source.py`（4 例：打分排序、跨源回退播放、音质递进、关闭回退时不越权搜索）、`tests/test_playback_state.py` 更新为整条音质链失败后落 stopped 并给错误提示 | `tools/probe_r3_fallback.py`：酷狗「晴天」404 → 自动在网易/汽水/QQ/小米中查找 → 经 QQ 音乐插件（内部走酷我 CDN）播放，`state=playing`、`position=1665ms`；状态栏依次提示「酷狗 暂时无法播放…正在其他音源中查找」「已通过 QQ音乐 · 1a43 播放」 | 已验证修复 |
| R3-03 | 中 | LOGO 与原版不一致 | 原版界面用的是 `app/ui_v2/assets/quiet-orbit-logo.svg`（112×76 波形 + h + 三角，深色 `#aab3bf/#e6e9ed/#7d8896`，浅色另有一套）；我们此前用 `assets/brand/HushPlayer.ico` 渲染的**带底板应用图标**当侧栏标志 | 混淆了「应用图标」与「界面标志」两种素材 | 复制原版两份 SVG 到 `assets/brand/logo_dark.svg`、`logo_light.svg`；`hushplayer/core/brand.py` 增加 SVG 渲染（`QSvgRenderer`，按 viewBox 等比居中）与 `logo_light/dark.svg` 优先解析；侧栏 `LogoMark` 改为按 112:76 比例绘制纯标志（38×26，无底板），关于页同样改用标志；窗口/任务栏/托盘/EXE 仍用多尺寸 `HushPlayer.ico`（与原版一致） | `tests/test_brand.py`（存在官方素材时返回 SVG；缺失时回退占位） | `artifacts/qa/r3/_sidebar_logo_new.png`（侧栏标志与文字比例）、`settings_about` 截图 | 已验证修复 |

## 二、额外发现

- X3-01：`_on_fallback_resolved()` 加载回退流后没有清 `busy`，界面会一直显示「正在加载」（真实播放已经在走）。已修复并纳入 R3-02 验证。
- X3-02：跨源回退的「领先分差」会被同一首歌的重复条目拉低，导致本可自动切换却降级成「最接近结果」。已按（归一化标题, 歌手）分组后再算分差。
- X3-03：两个 QQ 插件同名，状态栏与徽章无法区分。`build_sources()` 统一给重名源追加 `· 后四位`。
- X3-04：`SourceInfo.label` 是只读属性，最初直接赋值抛 `AttributeError: property 'label' has no setter`；改为改写 `name`。
- X3-05：回退搜索若某个音源不回调，会永远停在 loading；已加 `FALLBACK_SEARCH_TIMEOUT_MS + 2500` 看门狗与 `settled` 去重。
- X3-06：`Theme.font()` 旧实现里的 `if not display else` 分支两侧相同，属于无效代码，已清理。

## 三、验证命令

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/junit_round3.xml   # 127 passed
.venv\Scripts\python.exe -u tools\probe_r3_sources.py                        # 各音源真实能力
.venv\Scripts\python.exe -u tools\probe_r3_fallback.py                       # 酷狗 404 → 跨源播放
.venv\Scripts\python.exe -u tools\shot_app.py home songs settings ...         # 真实窗口截图
pwsh -File packaging\build.ps1 -Zip -SkipTests                                  # 1.0.3 安装包
pwsh -File tools\verify_package.ps1                                             # 打包版启动/单实例/退出
```

## 四、人工验收清单

1. 在 2560×1440 / 100% 缩放下打开应用，正文与次级文字应清晰、不虚边。
2. 设置 → 外观与主题，把「界面字号」拉到 140%/180%，界面应整体放大且不重叠；拉到 80% 仍可读。
3. 搜索「晴天」，选一条酷狗结果播放：状态栏应提示正在其他音源查找，随后开始播放。
4. 打开设置 → 在线音源：两个 QQ 音乐条目应带不同后缀，可禁用/删除/恢复。
5. 侧栏标志应与原版一致（波形 + h + 三角，无深色底板），深浅主题各一张。
6. 最大化/还原、切换主题、进入沉浸式歌词，均应无白边、无闪屏。

## 五、未解决

- 酷狗、QQ海棠 404 与小米搜索异常来自插件依赖的第三方接口，非本项目可控；已通过跨源回退保证「同一首歌仍能播放」，并在界面标明实际播放来源。
- 若所有音源都解析失败，仍会提示错误并停在停止态（不会再卡在加载中）。
