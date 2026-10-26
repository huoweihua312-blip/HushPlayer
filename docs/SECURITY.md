# 隐私与安全边界

HushPlayer 把「程序」「个人数据」「公开仓库」「发行包」分成四层。目标不是砍掉在线音乐，而是保证：

- 自己的音源插件、Cookie、数据库、歌单、收藏、历史、缓存**继续在本机可用**；
- 这些文件**不会**被提交到公开仓库，也**不会**被打进安装包；
- 别人克隆仓库或安装发行包时，拿不到任何个人音源或账号信息。

## 1. 目录边界

| 位置 | 内容 | 进公开仓库 | 进安装包 |
| --- | --- | --- | --- |
| 仓库 `hushplayer/`、`packaging/`、`tests/`、`tools/` | 源码、测试夹具（假数据）、构建脚本 | 是 | 是 |
| `%LOCALAPPDATA%\HushPlayerReimagined\` | 数据库、歌单、收藏、历史、设置、会话、缓存、日志 | 否 | 否 |
| `%LOCALAPPDATA%\HushPlayerReimagined\sources\` | 你安装的音源插件 + `source_registry.json` + 备份 | 否 | 否 |
| 便携模式的 `Data\`（exe 同级） | 同上，整套个人数据 | 否 | 否 |

发行包只包含 Node 运行框架（`plugin_host.js`、`runner.js`、`node_modules`、`node.exe`）、Python 依赖、图标字体和一个**空的** `source_registry.json`。

## 2. 音源放哪、怎么加载

- 启动时 `hushplayer.online.registry.SourceRegistry.ensure()` 只保证 `data_dir()/sources` 存在，并把注册表交给 Node 运行时（`HUSHPLAYER_SOURCE_REGISTRY` / `HUSHPLAYER_SOURCE_HOME` / `HUSHPLAYER_USER_SOURCES`）。
- 插件的安装、启用、删除都写这个目录；程序目录**不再作为音源来源**。
- 空音源是合法状态：界面会提示去「设置 → 音源」安装，不会崩溃。

## 3. 从旧版本迁移

旧版本曾把插件放在程序目录（含仓库里的 `hushplayer/runtime/source_runtime/sources/`）。现在由 `hushplayer/online/source_migration.py` 迁移：

1. 迁移前把旧注册表与它引用的插件复制到 `sources/migration_backup/legacy-<时间戳>/`；
2. 目标文件已存在就跳过，**绝不覆盖**；
3. 保留插件 id、文件名、启用状态、来源字段；
4. 全部就位才写 `sources/migration.json`；缺文件则保持「可重试」，下次启动继续补；
5. 迁移只写 `sources/` 目录，不触碰数据库、歌单、设置、缓存。

想手动重来：关掉程序，把 `sources/migration.json` 删掉再启动即可；旧文件不会被删。

## 4. 敏感信息检查

`tools/security_scan.py` 是可重复执行的扫描器，覆盖：

- **待提交文件**（`--staged`）：Cookie/会话、API Key、Bearer、GitHub Token、私钥、真实数据库、个人插件及备份、个人配置/缓存/历史、可疑绝对路径；
- **仓库跟踪文件**（`--tracked`）与未忽略的未跟踪文件（`--worktree`）；
- **发行产物**（`--path <dist> --release`、`--zip <zip>`）：直接读 onedir / ZIP / 安装脚本的实际内容，不只看源码；
- **退出码**：命中高风险返回 1，构建/提交会被拦住；输出只给脱敏后的路径、行号、长度，不打印凭据原文。

允许的误报写在 `tools/security_allowlist.json`，每条都要有 `reason`（例如 `node_modules` 里的第三方邮箱）。不要用「整个 `sources/` 目录放行」这种方式掩盖风险。

强制接入点：

| 时机 | 位置 | 行为 |
| --- | --- | --- |
| `git commit` | `.githooks/pre-commit` | 跑 `--staged`，高风险拒绝提交 |
| `git push` | `.githooks/pre-push` | 跑 `--tracked`，高风险拒绝推送 |
| 构建 | `packaging/build.ps1` | PyInstaller 前跑 `--tracked`；产物复制后跑 `--path ... --release`，失败删产物；生成 ZIP 后再扫 ZIP |
| 安装包 | 编译 `installer.iss` 前 | `python tools/security_scan.py --inno packaging/installer.iss --dist <dist>` |

钩子只是本地便利，`--no-verify` 能跳过；**发行构建里的检查才是硬门槛**。

启用钩子（每个克隆执行一次）：

```powershell
pwsh -File tools\install_git_hooks.ps1
```

## 5. 凭据处置建议（重要）

历史提交里曾包含过一个网易云 `MUSIC_U` Cookie 与带签名的订阅/播放 URL。仓库已经通过 `git rm --cached` + `.gitignore` 停止跟踪，但**历史仍然可以检出**。建议：

1. 到网易云音乐网页端「退出所有设备 / 修改密码」，让旧 `MUSIC_U` 会话失效；
2. 确认该 Cookie 属于哪个账号，检查是否还绑定了手机号/邮箱；
3. 需要彻底清除历史时，用 `git filter-repo` 单独处理这些路径，然后**强制推送所有远端分支并通知协作者重新克隆**——这一步不可逆，必须由仓库所有者明确批准后执行；
4. 旧订阅链接若带签名参数，重新生成一份新的，旧的作废。

本轮没有重写历史、没有强推、没有删除远程分支或 Release。

## 6. 相关文件

- `hushplayer/online/source_migration.py`：迁移与校验
- `hushplayer/online/registry.py`：可写音源目录与安装
- `tools/security_scan.py`、`tools/security_allowlist.json`：扫描器与白名单
- `tools/install_git_hooks.ps1`、`.githooks/pre-commit`、`.githooks/pre-push`
- `packaging/hushplayer.spec`、`packaging/build.ps1`、`packaging/installer.iss`
- `tests/test_privacy_isolation.py`：18 项隐私隔离回归
