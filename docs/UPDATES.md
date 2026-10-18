# 更新机制

## 设计原则

用户明确否决了 Velopack 方案（复杂度高、没有解决实际问题）。HushPlayer 采用**最小可信的更新检查**：

- 只做「检查 + 告知 + 打开下载页」，**不静默下载、不自动安装**。
- 更新源是普通 HTTPS JSON 文件，可放在任意静态托管（GitHub Releases、对象存储、内网服务器）。
- 清单地址可配置，不写死；未配置时更新检查直接返回「尚未配置更新源」，不报错、不联网。
- 检查失败绝不阻塞启动，只在日志与设置页提示。

实现见 `hushplayer/services/updater.py`，入口：

- 设置 → 关于 → 检查更新
- 设置 → 常规 → 启动时检查更新（默认开启，启动 6 秒后检查一次）

## 清单格式

```json
{
  "version": "1.1.0",
  "url": "https://example.com/hushplayer/HushPlayer-1.1.0-win64.zip",
  "notes": "修复在线歌词缓存失效问题；新增……",
  "published_at": "2026-11-01",
  "minimum": "1.0.0"
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 是 | 语义化版本，与 `hushplayer/version.py` 的 `VERSION` 比较 |
| `url` / `download_url` | 否 | 新版本下载页；缺失时只提示版本号 |
| `notes` / `changelog` | 否 | 更新说明，界面最多展示 600 字 |
| `published_at` / `date` | 否 | 发布日期，仅展示 |
| `minimum` | 否 | 最低兼容版本（预留字段，当前不影响提示） |

版本比较使用纯数字段 `major.minor.patch`；非数字后缀忽略。

## 配置方式

设置文件 `%LOCALAPPDATA%\HushPlayerReimagined\settings.json`：

```json
{
  "update": {
    "manifest_url": "https://example.com/hushplayer/latest.json",
    "check_on_start": true
  }
}
```

`update.check_on_start` 缺省为 `true`。

## 发布流程（维护者）

1. 修改 `hushplayer/version.py` 的 `VERSION`。
2. 生成安装包与校验值：
   ```powershell
   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip
   ```
3. 上传 `HushPlayer-<version>-win64.zip`，记录 SHA256。
4. 更新 `latest.json`（版本号、下载地址、更新说明）。
5. 用户下次启动会看到「发现新版本 x.y.z」，在 设置 → 关于 中查看详情并打开下载页。

## 为什么不做自动安装

- 没有代码签名证书时，自动替换可执行文件容易触发 SmartScreen 与安全软件拦截。
- 绿色版目录可能被用户放在受保护位置（Program Files），静默写入需要管理员权限。
- 用户更在意「清楚知道更新了什么」，而不是省一次点击。

后续若引入签名与增量更新，可在保留现有清单格式的前提下扩展，不需要改客户端协议。
