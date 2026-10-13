[CmdletBinding()]
param(
    [string]$Python = 'C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$ProjectRoot = '',
    [string]$DbPath = '',
    [string]$OutputDir = '',
    [switch]$ExportOnly,
    [string[]]$Site
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
$runner = Join-Path $ProjectRoot 'scripts\refresh_spec.py'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到 Python 3.12: $Python"
}
if (-not (Test-Path -LiteralPath $runner)) {
    throw "找不到刷新脚本: $runner"
}

Set-Location -LiteralPath $ProjectRoot
$env:OVERSEAS_NAV_TIMEOUT = if ($env:OVERSEAS_NAV_TIMEOUT) { $env:OVERSEAS_NAV_TIMEOUT } else { '60' }
$env:PYTHONIOENCODING = 'utf-8'
$arguments = @($runner)
if ($DbPath) { $arguments += @('--db', $DbPath) }
if ($OutputDir) { $arguments += @('--output-dir', $OutputDir) }
if ($ExportOnly) { $arguments += '--export-only' }
foreach ($code in ($Site | Where-Object { $_ })) {
    $arguments += @('--site', $code)
}

& $Python @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
