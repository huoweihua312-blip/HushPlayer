# B2 State Mapping

2026-09-10，代码路径相对 `app/ui_v2/`。设计状态不是新业务枚举；只有当前源码真实存在的 phase/role/flag 才能作为状态来源。HTML 的 state URL 不能直接搬进正式状态机。

## Track

来源：`models/track.py`、`models/track_table_model.py` 的 TRACK_ROLE / PLAYING_ROLE / PLAYBACK_ACTIVE_ROLE；`widgets/track_delegate.py::row_visual_state`；选择来自 QStyle.State_Selected，Hover 来自 TrackTable.is_row_hovered。

| B2 状态 | 正式来源 | 视觉契约 / 操作 |
|---|---|---|
| Default | 无下述flag | 无连续卡片背景，正常标题 |
| Hover | table.is_row_hovered(row) | 轻背景，更多操作可见；不是选择 |
| Selected | selectionModel/QStyle.State_Selected | 中性背景，不切换播放 |
| Playing | PLAYING_ROLE && PLAYBACK_ACTIVE_ROLE | Accent标题/播放标记；不靠整行金色 |
| Paused | PLAYING_ROLE && !PLAYBACK_ACTIVE_ROLE | 当前身份仍保留，暂停标记不动画 |
| Favorite | Track.is_favorite | 独立心形与现有收藏信号；不替代选中 |
| Unavailable | Track.is_missing 或 availability 经 track_display 解释 | 原因/缺失图标、现有重试或恢复条件 |
| Playing + Selected | 两个role/flag | 中性选中底+当前身份标记，不能二选一 |
| Playing + Favorite | playing + is_favorite | 播放标记与收藏同时存在 |
| Selected + Unavailable | selected + missing | SELECTED_DISABLED，保留中性选择可见性 |
| Hover + Unavailable | hovered + missing | HOVER_DISABLED，仍可查看信息/按条件恢复 |
| Paused + Selected | playing && !active && selected | SELECTED_PAUSED，不伪装正在播放 |
| Favorite + Unavailable | favorite && missing | 可以取消失效收藏；缺失未收藏不能新增收藏 |
| Playing + Selected + Unavailable | flags可并存，missing优先 | 当前TrackDelegate先返回SELECTED_DISABLED；B2示例仍保留当前身份标记。实施须保留业务flag，用绘制映射协调，不能改播放可用性判断来匹配截图 |
| Loading / resolving / buffering | is_loading / availability / PlaybackState.status | 来源/播放反馈，禁止直接画成已播放成功 |

现有 row_visual_state 优先级：missing+selected → missing+hover → missing → selected paused → selected playing → selected → paused → playing → hover → default。Favorite独立。OnlineResultDelegate 的可用性与正式请求能力有独立逻辑，不套用本地缺失文件的禁用规则。

## Search（本地）

| B2 | 来源 | 契约 |
|---|---|---|
| Idle | 当前query为空；输入与页面adapter同步 | 本地全量/原页面，不造网络进度 |
| Typing | SearchInputController._timer、textEdited/_edited_text | 180ms debounce；是UI过渡，不新增持久phase |
| Searching | query_ready后的现有过滤/数据加载路径 | 本地同步过滤不强造异步loading |
| Results | adapter返回可见tracks | 排序/过滤不重设播放上下文 |
| Empty | query非空且结果为空 | 搜索无结果不同于空音乐库 |
| Failed | collection/page已有错误状态 | 显示真实错误；没有错误时不人为制造phase |

Enter/清空按控制器原规则立即flush；切页 sync_text 停止旧计时器并用 QSignalBlocker 防止把查询提交到错误页面。

## Lyrics

| B2 | 当前来源 | 注意 |
|---|---|---|
| Idle | LyricsAdapter.clear → LyricsState.phase='idle' | 未播放/无歌曲，不显示演示歌词 |
| Loading | _load_formal_track / loading回调 → loading | 旧请求取消/track匹配必须保留 |
| Ready | 正式document有效 → ready；active_line/segment变化 | Canvas渲染原文/翻译，不重解析时间轴 |
| Empty | 正式无有效document/lines → empty | 无歌词，不等于纯音乐 |
| Failed | 服务失败回调 → failed | 保留retry/source入口 |
| Playback unavailable | set_track / set_playback_status → playback_unavailable | 不用合成歌词掩盖播放失败 |
| Instrumental | LyricsState支持；当前显式赋值见mock scenario分支 | 复用歌词状态视觉，不新增正式“自动纯音乐检测” |
| Manual Browsing | LyricsCanvasV2.browsing/_browse_anchor/_browse_offset | 与ready并行；return_to_current恢复跟随 |
| Translation on/off | LyricsAdapter._show_translation、display_options_changed → Canvas.set_display_options | 不同于ready/empty；保留用户选项 |
| Paused timing | PlaybackState.is_playing → Canvas.set_playback_active | 不继续推进播放时钟；选中歌词不改播放身份 |

普通与沉浸共用歌词来源，但度量/背景不同。罗马音在兼容数据或测试仍有字样，不能据此恢复已移除的正式入口。

## Settings

来源：`models/settings_edit_session.py::SettingsEditSession`、`widgets/settings_overlay.py`、`adapters/legacy_settings_bridge.py`。

| B2 | 源码状态 | 结果 |
|---|---|---|
| Clean | session.dirty_fields为空 | footer禁用保存 |
| Dirty | working_snapshot与original不同 | 可保存但须通过validate |
| Preview | previewed_fields + theme等预览回调 | 只预览，不视为已保存 |
| Validation Failed | session.validation_errors / bridge.validate | 标错、保留草稿，不能写入无效设置 |
| Saving | _save_state='saving' | 保存中反馈 |
| Save Failed | bridge提交抛SettingsBridgeError；_save_state='failed' | 草稿保留、失败提示 |
| Saved | replace_after_save更新两个snapshot，清dirty/preview | 后续取消回到最新成功快照 |
| Cancel | session.cancel + preview恢复 | 恢复打开前/最后成功保存，不重置所有设置 |
| Unsaved close | request_close检测dirty → SettingsConfirmDialog | 继续编辑/放弃/保存按现有分支 |
| Immediate actions | _run_action：缓存/来源/待导入等 | 不混进草稿事务；不能声称Cancel撤销已经清理的文件 |

歌词设置的透明度是背景透明度；缓存“失败记录”命令不能变成所有歌词删除。目录草稿与实际扫描结果是不同事务。

## Online / Import / Recovery / Pending

| B2 | 正式来源 | 视觉与动作 |
|---|---|---|
| Idle | OnlineSearchState.phase='idle' | 搜索历史/输入 |
| Typing | set_query + 编辑器当前值 | 非独立service phase |
| Searching | phase='searching' | 查询中/可取消 |
| Progress | phase='searching' + progress/message | 不是新增phase='progress' |
| Results | _on_formal_results → results | 部分警告可与结果共存 |
| Empty | 完成后无结果 → empty | 无结果反馈 |
| Failed | _on_formal_status/结果summary/请求失败 → failed | retry保持有效query与来源 |
| Disabled Source | OnlineSource.enabled=False/status='disabled' | 与capability、health分别表达 |
| Source busy/failure | Source.status searching/failed/warning | 控件条件按menu-map，不能所有按钮都禁用 |
| Import invalid/busy/result | SourceImportDialog + importer回调/当前输入 | 校验、停止、部分成功与失败；不用HTML定时器替换服务 |
| Recovery | Track.needs_online_recovery、OnlineRecoveryCandidateDialog候选选择、MainWindow恢复处理 | 只更换来源，不重建成员身份 |
| Pending selected | QListWidget选择 + _sync_action_state | 不选禁用批量动作；selected不等于imported |
| Pending processing/failed | 现有导入验证与结果回调 | 原型state为演示，正式结果由验证器决定 |

OnlineAdapter 有正式与mock分支。generation/请求id必须区分过期回调；不能让旧结果覆盖新查询。Prototype自定义URL已改为当前输入草稿，忙碌/停止/重试/完成均不回落默认mock URL。

## Update

| B2 | 当前来源 | 不可改变 |
|---|---|---|
| Checking | Settings check_updates动作 → 正式更新检查服务 | 不重复启动/不阻塞UI |
| No Update | 服务检查完成，无可用manifest | 不伪造UpdateDialog枚举；显示现有检查结果 |
| Available / release notes | UpdateDialog接收manifest；format_release_notes | 当前/目标版本、架构、分版本日志 |
| Downloading | on_download_started / on_download_progress | 状态与进度一致 |
| Failed | on_download_failed | 无已校验文件，不启用安装 |
| Cancelled | on_download_cancelled / closeEvent | 清理未完成临时文件，由现有服务负责 |
| Verifying | 下载服务校验过程；界面当前合并“下载并校验” | 原型独立验证画面可作视觉阶段，不新增伪progress事件 |
| Ready | on_download_verified，_package_ready/_installer_ready | 仅真实大小/摘要验证通过才能安装 |
| Install / launch failed | install_now / on_installer_launch_failed | 正式app继续运行、允许重试/完整包回退 |

真实无更新、校验进度等来源并非一个统一 `UpdateState` 枚举。视觉迁移应接收既有信号，不为设计重写更新状态机。
