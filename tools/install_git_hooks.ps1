# 启用仓库内的 Git 钩子（只需执行一次；换机器/重新克隆后再执行）。
# 说明见 docs/GIT_HOOKS.md。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    git config core.hooksPath .githooks
    if ($LASTEXITCODE -ne 0) { throw "git config 失败" }

    # Git for Windows 需要可执行位；NTFS 上改为写 .gitattributes 之外的处理不可靠，
    # 这里直接确认文件存在并给出提示。
    $hook = Join-Path $root ".githooks/pre-commit"
    if (-not (Test-Path $hook)) { throw "缺少 .githooks/pre-commit" }

    Write-Host "已启用 core.hooksPath=.githooks"
    Write-Host "pre-commit 将在改动易碎模块时要求同步更新 AGENTS.md"
}
finally {
    Pop-Location
}
