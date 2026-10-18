# 从旧版 HushPlayer 导入数据

HushPlayer Reimagined 使用**全新的数据目录**，不会读取或修改旧版目录：

| | 旧版（只读参考） | 新版 |
| --- | --- | --- |
| 数据目录 | 旧版自己的 AppData/项目配置目录 | `%LOCALAPPDATA%\HushPlayerReimagined` |
| 数据库 | 旧 schema | 新 schema，首次启动自动建表 |

因此升级不会自动迁移任何东西。若确实需要把旧版的收藏、歌单、统计带过来，使用随附的迁移工具：

```
tools/migrate_legacy.py
```

## 安全保证

1. **默认只预览**，不加 `--apply` 不写任何文件。
2. 写入前把目标数据目录整体打包到 `backups/legacy-import-<时间戳>.zip`。
3. 只复制白名单文件，**只读源目录**，绝不删除、绝不改写旧项目。
4. 目标端同名文件先复制成 `*.before-import`，再覆盖。
5. 数据库整文件复制，不做 schema 改写；新版启动时按自己的迁移逻辑补表。
6. 提供 `--rollback <zip>`，解压备份恢复，恢复前同样保留 `*.before-rollback`。

## 用法

```powershell
# 1) 预览：列出将要复制的文件、大小、JSON 记录数
.\.venv\Scripts\python.exe tools\migrate_legacy.py --source "C:\Users\你\AppData\Roaming\HushPlayer"

# 2) 真正导入（会先自动备份目标目录）
.\.venv\Scripts\python.exe tools\migrate_legacy.py --source "C:\Users\你\AppData\Roaming\HushPlayer" --apply

# 3) 不满意就回退
.\.venv\Scripts\python.exe tools\migrate_legacy.py --rollback backups\legacy-import-20261018-120000.zip
```

迁移前请**关闭新旧两个程序**，避免 SQLite 与 JSON 写入竞争。

## 可以迁移的内容

白名单（存在即复制）：

- `hushplayer.db`（及 `-wal`/`-shm`）
- `library.json`、`playlists.json`、`favorites.json`
- `settings.json`、`play_queue.json`、`playback_session.json`
- `stats.json`、`remote_tracks.json`、`lyrics_bindings.json`
- `ignored_imports.json`、`pending_imports.json`

明确不迁移：

- `cache/`、`artwork/`、`downloads/`、`logs/` —— 可重建或体积大。
- 旧版的音源注册表：新版使用自带运行时与独立注册表，迁移旧注册表可能引用不存在的路径。

## 失败与回退

- 任何文件复制失败会立即停止并打印失败文件；已复制部分可用 `--rollback` 回退。
- 回退只恢复备份里存在的文件；目标端在导入后新增的文件不会被删除（保守策略）。
- 若新版数据库与旧库结构不兼容，新版会把损坏/不兼容的库另存并重建（日志有记录），此时请直接 `--rollback` 回退，再按 [INSTALL.md](INSTALL.md) 手动导入音乐目录。

## 为什么不自动迁移

用户明确要求「不得自动执行不可逆迁移」。旧版数据结构与新版不同，自动改库风险不可控；
预览 + 备份 + 回退的三段式流程让用户能先判断再决定。
