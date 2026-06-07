param(
    [string]$TaskName = "Toodledo Local Mirror Sync",
    [string]$RepoRoot,
    [string]$PythonExe = "python.exe",
    [string]$DailyAt = "02:15",
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $DeployDir = Split-Path -Parent $PSScriptRoot
    $RepoRoot = Split-Path -Parent $DeployDir
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

try {
    $ScheduleTime = [datetime]::ParseExact($DailyAt, "HH:mm", $null)
} catch {
    throw "DailyAt must use 24-hour HH:mm format, for example 02:15."
}

$PythonCommand = Get-Command $PythonExe -ErrorAction Stop

$Action = New-ScheduledTaskAction `
    -Execute $PythonCommand.Source `
    -Argument "-m td mirror sync" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $ScheduleTime

$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel LeastPrivilege

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Refreshes the read-only Toodledo SQLite mirror once per day."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $Task `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Schedule: daily at $DailyAt"
Write-Host "Working directory: $RepoRoot"
Write-Host "Command: $($PythonCommand.Source) -m td mirror sync"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task: $TaskName"
}
