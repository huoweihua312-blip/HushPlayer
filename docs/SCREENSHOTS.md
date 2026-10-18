# 截图清单

全部截图由 `tools/shot_app.py` 启动真实程序、在真实 Windows 平台抓取（非设计稿、非浏览器渲染）。
文件位于 `docs/screenshots/`，同时以 `<场景>_<dark|light>.png` 命名。

```powershell
.\.venv\Scripts\python.exe tools\shot_app.py            # 全部场景
.\.venv\Scripts\python.exe tools\shot_app.py songs      # 指定场景
```

## 主窗口

| 场景 | 深色 | 浅色 | 说明 |
| --- | --- | --- | --- |
| 首页 | `home_dark.png` | `home_light.png` | 问候语、最近播放、最近添加、常听歌曲 |
| 歌曲 | `songs_dark.png` | `songs_light.png` | 表头、封面、收藏、来源徽章、排序 |
| 专辑网格 | `albums_dark.png` | `albums_light.png` | 卡片网格 |
| 专辑详情 | `album_dark.png` | `album_light.png` | Hero 封面 + 曲目 |
| 歌手网格 | `artists_dark.png` | `artists_light.png` | 圆形头像卡片 |
| 歌手详情 | `artist_dark.png` | `artist_light.png` | Hero + 歌曲/专辑分段 |
| 我喜欢 | `favorites_dark.png` | `favorites_light.png` | 系统歌单 |
| 歌单详情 | `playlist_dark.png` | `playlist_light.png` | 自定义歌单 + 拖拽排序 |
| 搜索（本地） | `search_dark.png` | `search_light.png` | 分段控件、专辑卡、歌曲 |
| 搜索（在线） | `online_dark.png` | `online_light.png` | 真实音源结果（130 条）、来源徽章、失败音源提示 |
| 队列面板 | `queue_dark.png` | `queue_light.png` | 右侧队列、窄列布局 |
| 设置 | `settings_dark.png` | `settings_light.png` | 左侧分类 + 卡片式设置项 |
| 小窗口 | `narrow_dark.png` | `narrow_light.png` | 960×680，列自适应 |

## 歌词与沉浸式

| 场景 | 深色 | 浅色 | 说明 |
| --- | --- | --- | --- |
| 普通歌词页 | `lyrics_dark.png` | `lyrics_light.png` | 封面、信息、逐字高亮、双语、偏移 |
| 沉浸式 · 封面舞台 | `immersive_dark.png` | `immersive_light.png` | 居中封面 + 光晕 + 歌词预览 + 控制栏 |
| 沉浸式 · 全幕歌词 | `immersive_lyrics_dark.png` | `immersive_lyrics_light.png` | 大字号逐字歌词 + 翻译 |
| 桌面歌词 | `desktop_lyrics_dark.png` | `desktop_lyrics_light.png` | 主行逐字扫过 + 翻译 + 下一行 |

## 打包版

| 文件 | 说明 |
| --- | --- |
| `packaged_light.png` | 从 `packaging/out/HushPlayer/HushPlayer.exe` 启动后的空库首页（浅色），证明发布产物可独立运行 |

## 截图里刻意保留的真实状态

- 在线搜索结果里部分曲目时长为 `—`：酷我插件对部分结果不返回时长，界面如实显示而不是编造。
- 网易云、酷狗等音源的播放/下载能力与截图无关，能力矩阵见 [FEATURES.md](FEATURES.md)。
- 桌面歌词截图使用深色底衬，便于观察半透明气泡在真实桌面上的对比度。
