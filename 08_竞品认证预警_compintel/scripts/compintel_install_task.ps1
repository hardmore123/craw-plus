# compintel_install_task.ps1 — 一键注册竞品情报定时任务到 Windows 计划任务
#
# 注册两个任务:
#   1. compintel_daily  — 每天 06:00 跑 compintel_daily.ps1(快,无详情)
#   2. compintel_weekly — 每周一 07:00 跑 compintel_weekly.ps1(慢,带详情)
#
# 用法: 以管理员身份运行 py -3.12 compintel_install_task.ps1
# 卸载: py -3.12 compintel_install_task.ps1 -Uninstall

param([switch]$Uninstall)

$PROJECT = Split-Path -Parent $PSScriptRoot
$DAILY = Join-Path $PSScriptRoot "compintel_daily.ps1"
$WEEKLY = Join-Path $PSScriptRoot "compintel_weekly.ps1"

$tasks = @(
    @{ Name = "compintel_daily";  Script = $DAILY;  Trigger = "每天 06:00" },
    @{ Name = "compintel_weekly"; Script = $WEEKLY; Trigger = "每周一 07:00" }
)

if ($Uninstall) {
    foreach ($t in $tasks) {
        try {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction Stop
            Write-Host "已删除任务: $($t.Name)"
        } catch {
            Write-Host "任务 $($t.Name) 不存在或已删除"
        }
    }
    exit 0
}

foreach ($t in $tasks) {
    # 定义触发器与动作
    if ($t.Name -eq "compintel_daily") {
        $trigger = New-ScheduledTaskTrigger -Daily -At 6am
    } else {
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7am
    }
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$($t.Script)`""
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)

    # 已存在则先删
    try { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction Stop } catch {}

    Register-ScheduledTask -TaskName $t.Name -Trigger $trigger -Action $action `
        -Settings $settings -Description "竞品情报$($t.Trigger): $($_)" -Force | Out-Null
    Write-Host "已注册: $($t.Name) → $($t.Trigger) → $($t.Script)"
}

Write-Host ""
Write-Host "竞品情报定时任务已安装:"
Write-Host "  每天 06:00  → compintel_daily.ps1  (快速,新记录信号)"
Write-Host "  每周一 07:00 → compinel_weekly.ps1 (深度,保密到期+字段变化)"
Write-Host ""
Write-Host "查看: Get-ScheduledTask -TaskName compintel_*"
Write-Host "手动触发: Start-ScheduledTask -TaskName compintel_daily"
Write-Host "卸载: .\compintel_install_task.ps1 -Uninstall"
