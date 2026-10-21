# 安装本仓库的 Git 钩子（每个克隆只需执行一次）

```powershell
cd F:\Projects\HushPlayer-Reimagined
pwsh -File tools\install_git_hooks.ps1
```

脚本做的事只有一件：把 `core.hooksPath` 指向仓库里的 `.githooks`，
于是 `pre-commit` 会跑 `tools/agents_guard.py`：

- 如果这次提交改到了易碎模块（安装包脚本、菜单浮层、列表/播放栏/队列绘制、
  设置控件、主题、缩放、`app.py`）却没有同时更新 `AGENTS.md`，提交会被拒绝；
- 确实不需要更新时，在提交信息里加 `[no-agents]` 放行。

钩子是版本化的（`.githooks/`），但 Git 不会自动启用它——所以每个工作副本
都要跑一次上面的命令。换机器或重新克隆后记得再跑一次。
