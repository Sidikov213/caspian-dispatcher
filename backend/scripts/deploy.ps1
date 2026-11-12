# Выкатка бэкенда на продакшен-сервер одной командой (через GitHub Actions, workflow deploy.yml).
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy.ps1            # выкатить main
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy.ps1 logs       # журнал сервиса
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy.ps1 restart    # перезапуск
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy.ps1 check      # только проверки
#   ... deploy.ps1 deploy -Upgrade                                                  # с apt upgrade
# Нужен gh (GitHub CLI) с доступом к репозиторию. Выкатывается то, что уже запушено в main.
param(
    [ValidateSet("deploy", "logs", "restart", "check")]
    [string]$Action = "deploy",
    [switch]$Upgrade
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
Set-Location (Join-Path $PSScriptRoot "..\..")

if ($Action -eq "deploy") {
    git fetch -q origin main
    $ahead = (git rev-list --count origin/main..HEAD).Trim()
    $dirty = git status --porcelain -- backend
    if ($ahead -ne "0") { Write-Warning "Локальных коммитов не в origin/main: $ahead. Выкатится только запушенное — сначала git push." }
    if ($dirty) { Write-Warning "В backend/ есть незакоммиченные изменения — они не выкатятся." }
}

$upgradeArg = if ($Upgrade) { "true" } else { "false" }
$before = (gh run list --workflow deploy.yml -L 1 --json databaseId -q ".[0].databaseId" 2>$null)
gh workflow run deploy.yml --ref main -f action=$Action -f upgrade=$upgradeArg
if ($LASTEXITCODE -ne 0) { throw "gh workflow run не запустился" }

$id = $before
for ($i = 0; $i -lt 30 -and $id -eq $before; $i++) {
    Start-Sleep -Seconds 2
    $id = (gh run list --workflow deploy.yml -L 1 --json databaseId -q ".[0].databaseId")
}
Write-Host "Запуск: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions/runs/$id"
gh run watch $id --exit-status --interval 10
$code = $LASTEXITCODE

# Итог: строки проверок и адрес; для logs — журнал целиком.
# Строка лога GitHub: «задача<TAB>шаг<TAB>[BOM]2026-11-12T12:38:31.1234567Z текст» — оставляем только текст.
$log = gh run view $id --log | ForEach-Object { ($_ -split "`t", 3)[-1] -replace '^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ', '' }
if ($Action -eq "logs") {
    $log | Select-Object -Last 240
} else {
    $log |
        Select-String -Pattern "^(OK  |FAIL|адрес:|HTTPS_)" | ForEach-Object { $_.Line }
}
exit $code
