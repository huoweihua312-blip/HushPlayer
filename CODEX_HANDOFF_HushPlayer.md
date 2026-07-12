# HushPlayer Codex Handoff

## 这是什么项目

HushPlayer 是一个 Windows 本地音乐播放器原型，用 Python + PySide6 开发。

目标不是做 Apple Music 克隆，而是做一个清爽、贴近 Windows 11 的本地播放器。用户主要想要：

- 本地音乐播放
- 自动读取歌曲元数据
- 自动匹配封面和歌词
- 歌词滚动
- 副屏沉浸歌词
- 桌面悬浮歌词
- 后续打包成 exe

用户不是程序员，所以修改时请尽量：
- 直接改真实代码，不要让用户手动找很多位置粘贴。
- 每次改完运行语法检查。
- 优先小步修改，避免大范围重构导致功能串掉。
- 不要输出超长完整文件，除非用户要求。
- 不要使用 emoji。

## 当前项目路径

```text
C:\Users\Administrator\Desktop\HushPlayer
```

主要文件：

```text
main.py
app/ui/main_window.py
data/library.json
data/playlists.json
data/stats.json
data/lyrics_bindings.json
data/settings.json
data/play_queue.json
cache/covers/
cache/lyrics/
```

不要删除 data 里的 json 文件，它们保存音乐库、歌单、统计、设置和歌词绑定。

## 已实现功能概览

### 基础播放器

- PySide6 UI
- QMediaPlayer + QAudioOutput 播放
- 播放 / 暂停
- 上一首 / 下一首
- 进度条拖动
- 音量滑块
- 音量记忆
- 播放模式：
  - 列表循环
  - 单曲循环
  - 随机播放

### 音乐库

- 导入单个音乐文件
- 导入文件夹，递归扫描
- 拖拽音乐文件 / 文件夹导入
- 支持 mp3/flac/wav/m4a/aac/ogg
- 自动读取 title / artist / album
- 音乐库保存到 `data/library.json`
- 搜索歌曲名 / 歌手 / 专辑 / 路径
- 移除选中
- 清理失效文件

### 封面

优先级：

1. 内嵌封面
2. 同目录封面文件
3. 联网封面搜索
4. 缓存

封面缓存目录：

```text
cache/covers/
```

搜不到会写 `.missing` 缓存，避免重复搜索。

### 歌词

优先级：

1. 手动绑定歌词
2. 本地同名 `.lrc`
3. 歌词缓存
4. 联网同步歌词搜索
5. 未找到

歌词缓存目录：

```text
cache/lyrics/
```

支持 LRC 时间轴滚动。

### 歌单和收藏

- 固定歌单：我喜欢
- 自定义歌单
- 左侧歌单区域
- 右键菜单可添加到歌单 / 从歌单移除
- 收藏按钮用于把当前歌曲加入 / 移出“我喜欢”

### 播放统计

- 播放次数
- 累计听歌时长
- 最近播放时间
- 最近播放 / 常听歌曲 / 最近添加视图

### 右键菜单

歌曲右键菜单大致包括：

- 播放
- 收藏 / 取消收藏
- 添加到歌单
- 从当前歌单移除
- 从音乐库移除
- 打开文件夹
- 查看歌曲信息
- 手动绑定歌词
- 取消歌词绑定
- 重新搜索歌词
- 重新搜索封面
- 下一首播放
- 加入播放队列
- 查看播放队列 / 播放列表

### 沉浸歌词

已有独立沉浸歌词窗口：

- 副屏优先全屏
- 封面模糊背景
- 黑色遮罩
- 遮罩透明度滑块
- 鼠标不动自动隐藏 UI
- 当前歌词超大显示，适合副屏看一眼知道唱到哪里

用户喜欢当前沉浸歌词方向，但还可以继续优化为“副屏提词器模式”。

### 桌面悬浮歌词

已做：

- Ctrl + Shift + D 打开 / 关闭
- 只显示当前歌词
- 无边框、无背景
- 置顶
- 可拖动
- 右键可调：
  - 锁定位置
  - 放大 / 缩小歌词
  - 加宽 / 缩窄显示区域
  - 重置大小
  - 提高 / 降低不透明度
  - 选择颜色：白、黑、黄、蓝、绿、粉、紫
  - 关闭

## 当前紧急问题

最近一次尝试把底部按钮强制重排成同一行时，破坏了“我喜欢”歌单和收藏按钮逻辑：

用户反馈：

- “我喜欢”的歌单没有了
- 收藏按钮不能正常用
- 点所有歌都显示“已收藏”
- 多了一个“我喜欢”按钮
- 用户真正想要的是：底部区域里 `收藏 / 列表循环 / 桌面歌词` 三个按钮在同一行，不是新增一个我喜欢按钮，也不是破坏左侧歌单

当前建议：

1. 先恢复到 `main_window.py.bak_v0543` 或更早备份，保证收藏和“我喜欢”正常。
2. 不要再靠全局 `findChildren(QPushButton)` 猜按钮。
3. 直接阅读 `main_window.py` 里底部控制栏创建代码，找到真实的：
   - `self.like_button`
   - `self.play_mode_button`
   - 音量布局
   - 底部右侧 layout
4. 在真实底部右侧区域明确创建结构：

```text
第一行：self.like_button | self.play_mode_button | self.floating_lyrics_button
第二行：音量 label/slider
```

不要移动左侧歌单里的“我喜欢”按钮，也不要把“我喜欢”当成收藏按钮。

## 建议下一步任务

### P0：修复当前按钮布局和收藏问题

目标：

- 恢复“我喜欢”歌单
- 恢复收藏按钮
- 保证只有真正的收藏按钮负责当前歌曲收藏状态
- 底部右侧显示为：

```text
收藏    列表循环    桌面歌词
音量    [slider]
```

建议做法：

- 打开 `app/ui/main_window.py`
- 查找 `self.like_button`
- 查找 `self.play_mode_button`
- 查找 `volume_slider`
- 查找 `install_floating_lyrics_button`
- 移除最近靠 `findChildren` 强制搬按钮的逻辑
- 在底部 UI 创建阶段显式加入 `self.floating_lyrics_button`

修改后运行：

```powershell
cd C:\Users\Administrator\Desktop\HushPlayer
.\.venv\Scripts\python.exe -m py_compile app\ui\main_window.py
.\.venv\Scripts\python.exe main.py
```

### P1：桌面歌词可读性增强

用户已经能调颜色和透明度，但下一步建议做：

- 黑色/白色描边
- 阴影
- 可选描边强度
- 可选字体大小滑块
- 可选保存桌面歌词位置

原因：桌面背景复杂时，单纯换颜色仍可能看不清。

### P2：设置页扩展

把桌面歌词设置收进设置页：

- 默认颜色
- 默认不透明度
- 默认字号
- 默认宽度
- 是否启动时自动打开桌面歌词

### P3：沉浸歌词继续优化

用户希望当前句更大、更明显：

- 当前句更大
- 其他句更弱、更远
- 当前句居中稳定
- 可增加“提词器模式 / 普通模式”切换

## 开发注意事项

- 不要删除 `data/` 和 `cache/`。
- 不要随便改 `normalize_song_path`、歌单数据结构、收藏逻辑。
- 修改 UI 时不要靠按钮文字全局查找，尤其不要把左侧“我喜欢”按钮和底部“收藏”按钮混淆。
- 每次改完必须运行：
  ```powershell
  .\.venv\Scripts\python.exe -m py_compile app\ui\main_window.py
  ```
- 改完最好运行 `main.py` 试启动。
- 用户更喜欢具体可执行步骤，不喜欢抽象建议。
