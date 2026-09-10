# B2 正式菜单与入口逐项映射

2026-09-10，基于当前 `app/ui_v2/` 的菜单构造、条件判断与信号连接重新扫描。隐藏/不创建与 disabled 严格区分。路径以下均以 `app/ui_v2/` 为根。B2 目标共用 System Menu/Tooltip/Focus；不新造业务项。

## Sidebar 更多

证据：`shell/navigation_sidebar.py::_show_more_navigation_menu` 过滤固定 route 集合；标题来自 `adapters/navigation_adapter.py::MAIN_ITEMS`，顺序按 items()。

| Trigger | Menu Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|---|
| Sidebar 更多，含compact图标 | 最近播放 | adapter 有 recent | 无显式禁用；缺item不创建 | 无 | adapter.set_route('recent') | 普通菜单行+recent图标 |
| 同上 | 歌手 | 有 artists | 同上 | 无 | set_route('artists') | 普通菜单行 |
| 同上 | 专辑 | 有 albums | 同上 | 无 | set_route('albums') | 普通菜单行 |
| 同上 | 歌词 | 有 lyrics | 同上 | 无 | set_route('lyrics') | 普通菜单行，目标普通歌词 |

当前没有其他 More 项。设置在独立入口，在线搜索/浏览在主导航；待导入按 include_pending 及对应路由显示，不能加入此菜单。`more_playlists_button` 是未加入布局且显式隐藏的兼容句柄，不是正式可见入口。“更多”按钮的 active 表示上述四个路由之一；菜单项当前不设 checkable，不把它改成多选菜单。

## 自定义歌单

| Trigger | Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|---|
| Sidebar 歌单右键 | 重命名歌单 | can_mutate 且 id != liked | 否则整个菜单不创建 | 无 | PlaylistNameDialog → adapter.rename_playlist | Input Dialog |
| 同上 | 删除歌单 | 同上 | 同上 | 无 | PlaylistConfirmDialog → delete_playlist | Destructive Confirm；歌曲文件保留 |
| PlaylistHeader 更多 | 添加歌曲 | !_read_only | 只读隐藏并禁用更多按钮 | 无 | add_requested → PlaylistPage._add_first_available_track | 普通菜单项；不替换添加算法 |
| 同上 | 重命名 | 同上 | 同上 | 无 | rename_requested | Input Dialog |
| 同上，分隔线后 | 删除歌单 | 同上 | 同上 | 无 | delete_requested | Destructive |

证据 `widgets/playlist_header.py`、`pages/playlist_page.py`。收藏歌单按钮始终隐藏且 disabled，不把原型动作扩成正式收藏歌单功能。添加歌曲当前处理必须保留，不能因原型有选择框就自行改成全新选曲流程。

## TrackTable

Trigger：有效歌曲行右键/更多区域；无有效 index 返回 None。证据 `widgets/track_table.py::build_context_menu`、`_can_change_favorite`。

| Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|
| 播放 | (not is_missing or is_online) and _playback_enabled | 条件不满足禁用，缺失/后端原因Tooltip | 无 | _request_play(track) | Primary menu action |
| 在线寻找并播放 | needs_online_recovery 且播放启用 | 不需恢复则隐藏；播放未启用则禁用 | 无 | online_recovery_requested(track) | Recovery Dialog，保留身份 |
| 添加到我喜欢 / 取消收藏 | collection.can_mutate_favorites，且 not missing or 已收藏 | collection不可改则隐藏；缺失未收藏禁用 | 无 | _toggle_from_menu | 动态文字；不必凭空加checkbox |
| 添加到歌单 | can_mutate_favorites | 否则隐藏 | 不是子菜单 | mock_action_requested('add_to_playlist',id) → 已接入正式选择对话框 | PlaylistSelectionDialog |
| 从当前歌单移除 | _playlist_remove_callback != None | 否则隐藏，不是常驻禁用 | 无 | callback(track.id) | 普通移除项，非删文件 |
| 查看歌曲信息 | 有有效track | 无额外限制 | 无 | mock_action_requested('show_info',id) | TrackInfoDialog |
| 查看艺人 | _artist_navigation_enabled and artist.strip() | 否则隐藏 | 无 | artist_requested(track.artist) | 普通路由项 |

不要根据信号名带 mock 就判断未接入；正式 MainWindow / ContentRouter 对该信号有实际处理。TrackTable 的加入歌单是对话框，不能与 Online/Browse 子菜单混为一套业务路径。

## Artist / Browse

| Trigger | Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|---|
| Artist详情 Hero 更多 | 复制艺人名称 | 当前艺人存在时实际写剪贴板 | 菜单action无显式disable；无艺人不复制 | 无 | QApplication.clipboard().setText | 普通菜单项 |
| Browse 歌曲卡片右键 | 播放 | _playback_enabled | 否则disabled；track无效或无playlists整个菜单不建 | 无 | _request_track_play | Track menu视觉 |
| 同上 | 收藏 / 取消收藏 | 可转换的online_track，或collection非只读 | 否则隐藏 | 无 | online_adapter.toggle_favorite / collection.set_favorite | 动态文字 |
| 同上 | 加入歌单 | playlist_count>0 且 (online_track存在 or 非只读) | 否则父菜单disabled | 每个实际歌单名称 | online request_add_to_playlist / playlists.add_tracks | 子菜单，不造空白新建项 |

证据 `pages/artist_detail_page.py::_show_more_menu`、`pages/browse_page.py::_show_track_menu`。卡片菜单信号来自 BrowseSection；没有找到专辑/艺人列表卡片的独立附加 QMenu，不复制原型示例创造菜单。

## Online Result

Trigger：有效在线结果右键；`widgets/online_result_table.py::build_context_menu`。

| Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|
| 播放 | 正式 is_formal 时可请求；非正式按 availability/retryable/read_only | 不能仅按原型 unavailable 禁用正式重试入口 | 无 | adapter.request_play | Menu普通播放项 |
| 收藏 / 取消收藏 | !collection.read_only or can_mutate_remote | 否则隐藏 | 无 | adapter.toggle_favorite | 动态文字 |
| 添加到歌单 | 同上 | 同上；源码未给空列表父项额外禁用 | 实际playlist.name | request_add_to_playlist(id,playlist_id) | 子菜单 |
| 查看歌曲信息 | 有track，显式enabled | 无 | 无 | request_metadata | Track Info |
| 查看来源 | 有track | 无 | 无 | source_requested → 来源管理 | 普通菜单项，不是新“来源详情窗口” |

下载 action 只在 `not formal` 条件下生成，故不属于本次正式菜单冻结。不得在正式 UI 中迁入。

## SourceSelector 与来源行

| Trigger | Item / control | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|---|
| 在线搜索来源下拉 | 全选来源 | state.phase != searching | searching禁用 | 无 | set_enabled_sources(all ids) | Menu item |
| 同上 | 清空来源 | 同上 | 同上 | 无 | set_enabled_sources(()) | Menu item |
| 同上，分隔线后 | 来源名 + 状态 + 结果数 | 同上 | 同上 | 无；checkable=enabled | set_source_enabled(id,checked) | Checked menu + Tooltip延迟/数量 |
| 来源管理行 | 启用 / 停用 | source.status != searching | searching禁用 | 无 | SourceRow.toggle_requested → set_enabled | 整轨道开关或现有按钮样式 |
| 同上 | 重试 | failed / warning 才显示 | 其他状态隐藏 | 无 | retry_requested → adapter.retry | Warning action |
| 同上 | 移除 | importer存在才显示 | importer缺失隐藏 | 无 | _confirm_remove → SourceRemoveConfirmDialog | Destructive confirm |
| 来源管理页头 | 添加来源 | importer存在 | 缺失disabled | 无 | SourceImportDialog | Primary action |
| 同上 | 全选 / 清空 | 没有任何searching来源 | 忙碌disabled | 无 | select_all / clear_selection | Secondary actions |

证据 `widgets/source_selector.py`、`pages/online_source_page.py`。正式 SourceRow **没有 Source Menu**：原型的“查看来源信息 / 移除来源”弹出菜单只提供视觉演示，不能作为新增入口依据。移除保留原有确认、来源配置与歌曲关系处理。

## 其他正式菜单/弹层

| Trigger | Item | Enabled condition | Disabled / hidden | Submenu | Target action | B2 mapping |
|---|---|---|---|---|---|---|
| 普通歌词 toolbar 更多 | 回到当前歌词 | action本身无显式disable | 无文档由Canvas处理 | 无 | LyricsPage连接 canvas.return_to_current | 普通单项菜单 |
| 桌面歌词右键 | 快捷设置面板 | 窗口可接受输入 | 锁定/穿透遵循窗口状态 | 不是QMenu | DesktopLyricsQuickSettingsPopover | Desktop Settings设计，不能换成普通主窗Dialog |
| Windows tray右键 | 解锁桌面歌词 | _desktop_lyrics_locked | 未锁时隐藏 | 无 | desktop_lyrics_unlock_requested | 原生菜单 |
| 同上，分隔线后 | 打开 HushPlayer | tray存在 | 无显式disable | 无 | restore_window | 原生菜单 |
| 同上，分隔线后 | 退出 HushPlayer | tray存在 | 无显式disable | 无 | request_exit | 原生菜单 |
| 设置/来源/排序等combo | 当前枚举选项 | 由现有控件与busy状态决定 | 不可用选项不扩写 | 原生popup | 当前valueChanged/currentIndexChanged | B2 input/popover视觉，保持枚举 |
| 可编辑文本右键 | Qt默认编辑操作 | selection/readOnly/clipboard决定 | Qt默认条件 | Qt原生 | undo/copy/paste等 | 保留原生文字编辑，不改业务 |

`LibraryPage._build_state_menu` 的预览状态菜单不在正式 AllSongsPage 构造：`include_preview_controls=False`，明确排除。实验窗口菜单、隐藏 PlayerBar more、未找到实现的沉浸歌单选择器也不纳入正式入口。

映射完成的是当前源码入口、条件与B2组件规格，不是对所有运行时业务菜单逐项实测。实现时须按本表逐项核对动态条件，不能只验收静态截图。
