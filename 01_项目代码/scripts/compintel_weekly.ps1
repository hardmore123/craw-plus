# compintel_weekly.ps1 — 竞品情报深度抓取(每周 1 次)
# 1. FCC 带 --details 抓详情页文件清单,检测保密到期 + 字段级变化。
#    用 compintel-fcc-full(授权码全量),--full-refresh 周度重查全部(含详情页变化)。
# 2. EPREL 全量扫描(step=1000 抽样),补充列表接口漏掉的竞品电视记录。
# 比 daily 慢,所以单独一周跑一次。

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$env:PYTHONIOENCODING = "utf-8"
$env:OVERSEAS_PROXY = "http://127.0.0.1:7877"

$PROJECT = Split-Path -Parent $PSScriptRoot
Set-Location $PROJECT
$DB = if ($env:OVERSEAS_DB_PATH) { $env:OVERSEAS_DB_PATH } else { Join-Path $PROJECT "data\overseas.db" }
$LOG_DIR = Join-Path $PROJECT "data\logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }
$DATE = Get-Date -Format "yyyy-MM-dd"
$LOG = Join-Path $LOG_DIR "compintel_weekly_$DATE.log"

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Write-Host $line
}

Write-Log "==== 竞品情报深度抓取开始(带详情) ===="

# 6 家核心电视竞品(标准品牌名,compintel-fcc-full 自动发现授权码)
$BRANDS = @("Samsung", "LG", "Hisense", "TCL", "Sony", "Panasonic")

# 备份
$BAK = "$DB.bak_compintel_weekly_$DATE"
if (-not (Test-Path $BAK)) {
    Copy-Item $DB $BAK -ErrorAction SilentlyContinue
    Write-Log "已备份数据库 -> $BAK"
}

# ---- 1. FCC 全量抓取(带详情,--full-refresh 周度重查全部) ----
# --full-refresh: 不走增量早停,重新翻所有页 + 抓详情页,检测保密到期/字段变化
# --details: 抓每个 FCC ID 的文件清单(Internal Photos 等)
Write-Log "---- FCC 全量抓取(带详情 + 全量重查) ----"
$fccArgs = @("-m", "overseas.cli", "compintel-fcc-full", "--json",
             "--full-refresh", "--details", "--brands") + $BRANDS
Write-Log "执行: py -3.12 $($fccArgs -join ' ')"
$fccJson = & py -3.12 @fccArgs 2>&1 | Out-String
Add-Content -Path $LOG -Value $fccJson -Encoding UTF8
try {
    $fr = $fccJson | ConvertFrom-Json
    Write-Log "FCC: ok=$($fr.ok) fail=$($fr.fail) 新=$($fr.new) 信号=$($fr.signals.Count)"
    foreach ($b in $fr.grantees.PSObject.Properties) {
        Write-Log "   $($b.Name): 授权码 $($b.Value.grantees) 个, 记录 $($b.Value.records)"
    }
} catch {
    Write-Log "FCC 解析失败: $_"
}

# ---- 2. EPREL 全量扫描(补充列表接口漏掉的竞品电视记录) ----
Write-Log "==== EPREL 全量扫描开始(step=1000 抽样) ===="
$scanArgs = @("-m", "overseas.cli", "compintel-eprel-scan", "--json",
              "--brands") + $BRANDS +
            @("--start", "1", "--end", "400000", "--step", "1000")
Write-Log "执行: py -3.12 $($scanArgs -join ' ')"
$scanJson = & py -3.12 @scanArgs 2>&1 | Out-String
Add-Content -Path $LOG -Value $scanJson -Encoding UTF8
try {
    $sr = $scanJson | ConvertFrom-Json
    Write-Log "EPREL 扫描: 扫描=$($sr.scanned) ok=$($sr.ok) 新=$($sr.new) 信号=$($sr.signals.Count)"
} catch {
    Write-Log "EPREL 扫描解析失败: $_"
}
Write-Log "==== 深度抓取结束 ===="
