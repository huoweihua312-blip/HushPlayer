# 安装、启动与卸载

## 1. 系统要求

- Windows 10 1809 或更高版本 / Windows 11，x64
- 4 GB 内存以上，200 MB 磁盘空间（另加音乐库与缓存）
- 无需预装 Python、Node.js 或任何运行库：发布包自带 Python 运行时与 Node 22

## 2. 获取发布包

发布产物位于 `F:\HushPlayerBuild\out\`（脚本默认输出到 F 盘，避免 C 盘/受管目录的完整性标签干扰托盘注册）：

| 文件 | 说明 |
| --- | --- |
| `HushPlayer/` | 解压即用目录（onedir），含 `HushPlayer.exe` 与 `_internal/` |
| `HushPlayer-<版本>-win64.zip` | 上者的压缩包（当前 1.1.15） |
| `SHA256SUMS.txt` | 压缩包校验值 |

自行构建：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip
```

脚本会生成版本信息、跑测试、必要时下载内置 Node、调用 PyInstaller，并可选打 zip。首次构建需下载 Node（约 35 MB）。

### 校验与回滚

1. 下载 zip 后先核对 `SHA256SUMS.txt`：
   ```powershell
   Get-FileHash .\HushPlayer-1.1.15-win64.zip -Algorithm SHA256
   ```
2. 升级时保留旧目录（例如把 `HushPlayer` 改名为 `HushPlayer.old`），再解压新包；确认无误后再删除旧目录。
3. 回滚：删除新目录、把 `HushPlayer.old` 改回 `HushPlayer` 即可——用户数据在独立目录，不受影响。
4. 版本号查看：`HushPlayer.exe` 属性 → 详细信息 → 产品版本；或运行后在「设置 → 关于」查看。

## 3. 安装

HushPlayer 是绿色版：把 `HushPlayer` 目录放在任意位置（例如 `D:\Apps\HushPlayer`），双击 `HushPlayer.exe` 即可。
不写系统目录、不注册服务、不写注册表。

- **便携模式**：在 `HushPlayer.exe` 同级放一个空的 `portable.txt`，或在启动前设置 `HUSHPLAYER_PORTABLE=1`，数据会写入 `HushPlayer\Data\`。
- **开始菜单快捷方式**（可选）：右键 `HushPlayer.exe` → 发送到 → 桌面快捷方式。

## 4. 首次启动

1. 进入首页，点击「添加音乐文件夹」选择音乐目录；也可以稍后在 设置 → 音乐库 中添加。
2. HushPlayer 会扫描音频文件、读取标签与内嵌封面，并写入本地数据库。
3. 点击任意歌曲开始播放。
4. 在线音乐：进入搜索页，切到「在线」分段，选择音源后搜索。首次使用会启动内置 Node 运行时（约 1 秒）。

## 5. 数据位置

| 内容 | 路径 |
| --- | --- |
| 数据库、设置、歌单、队列 | `%LOCALAPPDATA%\HushPlayerReimagined\` |
| 音频缓存 | `...\cache\audio\` |
| 封面缓存 | `...\cache\artwork\` |
| 在线歌词缓存 | `...\cache\lyrics\` |
| 日志 | `...\logs\hushplayer.log`（5 MB 轮转，保留 5 份） |
| 下载 | 默认 `%USERPROFILE%\Music\HushPlayer Downloads`，可设置 |

设置里提供「打开数据目录 / 打开日志」入口。程序文件与用户数据完全分离，升级或删除程序不会动数据。

## 6. 卸载

1. 关闭 HushPlayer（托盘 → 退出）。
2. 删除程序目录。
3. 如不再需要个人数据，删除 `%LOCALAPPDATA%\HushPlayerReimagined`（**这会删除歌单与收藏，请先备份**）。

## 7. 开机自启

设置 → 常规 → 开机时自动启动。实现方式是在
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\HushPlayer.cmd` 写入一行启动命令，
不修改注册表；关闭开关会删除该文件。

## 8. 单实例

同一用户会话只允许一个 HushPlayer 实例。重复启动时，新进程会通知已有实例把窗口置前并退出。
需要并行调试时可设置环境变量 `HUSHPLAYER_ALLOW_MULTI=1`。

## 9. 故障排查

| 现象 | 处理 |
| --- | --- |
| 启动即退出 | 看 `%LOCALAPPDATA%\HushPlayerReimagined\logs\crash.log` 与 `hushplayer.log` |
| 无声音 | 设置 → 播放 → 音频设备，换一个输出设备；确认系统未静音 |
| 在线搜索无结果 | 检查网络；设置 → 在线音源 里刷新音源；查看日志里的 runner 错误 |
| 在线播放 404 | 该音源解析失败（见 KNOWN_ISSUES），尝试其他音源或本地文件 |
| 歌词不显示 | 确认歌曲有 `.lrc` 同名文件或内嵌歌词；设置 → 歌词 里开启在线获取 |
| 界面文字发虚 | 确认 Windows 缩放与显示器设置；HushPlayer 使用 Per-Monitor V2 DPI |

## 安装包（推荐）

运行 `HushPlayer-1.1.15-setup.exe`：

- 默认安装到 `%LOCALAPPDATA%\Programs\HushPlayer`，无需管理员权限；
- 安装向导为简体中文（语言文件取自 Inno Setup 官方仓库并随包内置）；
- 安装位置可自选：向导会显示「选择目标位置」页，默认沿用上次安装目录（欢迎页会写明具体路径；自定义目录也会被带出），直接下一步即原地覆盖升级；点「浏览…」可改到任意文件夹。
- 可选「桌面快捷方式」与「登录时自动启动」；
- 卸载：设置 → 应用 → HushPlayer（或开始菜单「卸载 HushPlayer」）。

卸载**不会**删除 `%LOCALAPPDATA%\HushPlayerReimagined`（音乐库、歌单、设置、缓存）。要彻底清空，卸载后手动删除该目录。

校验安装包：

```powershell
Get-FileHash HushPlayer-1.1.15-setup.exe -Algorithm SHA256
# 0C6B7D4B3A355BB8183A22DB56CE1FFCCA347C83A431E515C0914783BE98CFEF
```

### 1.1.15 安装包

- 安装包：`HushPlayer-1.1.15-setup.exe`（82.4 MB，简体中文向导，可选择安装目录）。
- SHA256：`C43C2212B5C0476F87272D8777AB24C3DC7C0D24F5C45A4B9185FB81502CC5D8`
- 免安装 zip：`HushPlayer-1.1.15-win64.zip`，SHA256 `E5CD2F70662D76BD1E95097FB98A7EEFA54678EA4518B6BB7F0B0BAC4CD72D04`
- 卸载会删除程序目录（含 PyInstaller 的 `_internal` 与更新器），保留 `%LOCALAPPDATA%\HushPlayerReimagined` 里的音乐库、歌单与设置。
