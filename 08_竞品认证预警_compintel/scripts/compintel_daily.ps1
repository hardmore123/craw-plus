# compintel_daily.ps1 — 竞品情报日常抓取(每天 1 次)
# 由 Windows 计划任务调用。无 --details(快),只抓新记录信号。
# 时间限制:FCC 只抓近 365 天认证(--since 默认),不堆旧认证。
# 增量模式:默认增量(--incremental),遇整页已知 FCC ID 即停翻,
#   今天抓过的授权码用 --refresh-days 1 整码跳过,不重复抓。
# 日志写 data/logs/compintel_daily_<日期>.log
#
# 计划任务设置(见 deploy/compintel_daily_task.xml):
#   每天凌晨 06:00 触发,串行执行,超时 30 分钟。

$ErrorActionPreference = "Stop"
# 控制台 UTF8 输出(计划任务无控制台,日志文件本身是 UTF8)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# ---- 环境(与项目一致) ----
$env:PYTHONIOENCODING = "utf-8"
$env:OVERSEAS_PROXY = "http://127.0.0.1:7877"

# ---- 路径 ----
$PROJECT = Split-Path -Parent $PSScriptRoot   # 海外/
Set-Location $PROJECT
# DB 路径:优先用 OVERSEAS_DB_PATH 覆盖(测试用),否则用正式库
$DB = if ($env:OVERSEAS_DB_PATH) { $env:OVERSEAS_DB_PATH } else { Join-Path $PROJECT "data\overseas.db" }
$LOG_DIR = Join-Path $PROJECT "data\logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }
$DATE = Get-Date -Format "yyyy-MM-dd"
$LOG = Join-Path $LOG_DIR "compintel_daily_$DATE.log"

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Write-Host $line
}

Write-Log "==== 竞品情报日常抓取开始 ===="

# ---- 竞品品牌清单(FCC 全量抓取:授权码发现 + 所有分页) ----
# 用 --brands 传标准品牌名,脚本自动发现全部授权码再遍历(比公司名搜索全得多)
# 实测: 6 家共 72 个授权码;公司名搜索会截断(如 TCL 33 条 vs 授权码 2ACCJ 508 条)
$BRANDS = @(
    "Samsung",
    "LG",
    "Hisense",
    "TCL",
    "Sony",
    "Panasonic"
)

# ---- EPREL 重点品牌(只保留这些品牌的电子显示器/电视记录) ----
$EPREL_BRANDS = $BRANDS

# ---- 备份 DB(工程红线:长时抓取先备份) ----
$BAK = "$DB.bak_compintel_$DATE"
if (-not (Test-Path $BAK)) {
    Copy-Item $DB $BAK -ErrorAction SilentlyContinue
    Write-Log "已备份数据库 -> $BAK"
}

# ---- 1. FCC 增量抓取(授权码 + 所有分页,增量早停) ----
# 增量模式:已知记录不重复入库,遇整页已知ID即停翻(95页→85页)
# --refresh-days 1:今天抓过的授权码整码跳过(同一天多次运行=秒回)
# 注意:PowerShell 数组传外部命令,必须用 @() 并逐个展开,否则变成 System.Object[]
Write-Log "---- FCC 增量抓取(授权码发现 + 分页遍历 + 早停) ----"
$fccArgs = @("-m", "overseas.cli", "compintel-fcc-full", "--json",
             "--refresh-days", "1", "--brands") + $BRANDS
Write-Log "执行: py -3.12 $($fccArgs -join ' ')"
$fccJson = & py -3.12 @fccArgs 2>&1 | Out-String
Add-Content -Path $LOG -Value $fccJson -Encoding UTF8

try {
    $fr = $fccJson | ConvertFrom-Json
    Write-Log "FCC: ok=$($fr.ok) fail=$($fr.fail) 新=$($fr.new) 跳过授权码=$($fr.skipped) 增量=$($fr.incremental)"
    foreach ($b in $fr.grantees.PSObject.Properties) {
        $pg = if ($b.Value.pages) { " 翻页$($b.Value.pages)" } else { "" }
        $sk = if ($b.Value.skipped) { " 跳过$($b.Value.skipped)" } else { "" }
        Write-Log "   $($b.Name): 授权码 $($b.Value.grantees) 个, 记录 $($b.Value.records)$pg$sk"
    }
} catch {
    Write-Log "FCC 解析失败: $_"
}

# ---- 2. EPREL 列表抓取 ----
Write-Log "---- EPREL 抓取 ----"
$eprelArgs = @("-m", "overseas.cli", "compintel-eprel", "--json", "--brands") + $EPREL_BRANDS
$json = & py -3.12 @eprelArgs 2>&1 | Out-String
Add-Content -Path $LOG -Value $json -Encoding UTF8

# ---- 解析 EPREL 结果 ----
try {
    $r = $json | ConvertFrom-Json
    Write-Log "EPREL: ok=$($r.ok) 新=$($r.new)/$($r.total) 信号=$($r.signals.Count)"
} catch {
    Write-Log "EPREL 解析失败: $_"
}

# ---- 上市预警汇总 ----
Write-Log "---- 上市预警(launch_warning) ----"
$alertJson = & py -3.12 -m overseas.cli compintel-alert --type launch_warning --limit 30 --json 2>&1 | Out-String
Add-Content -Path $LOG -Value $alertJson -Encoding UTF8
try {
    $al = $alertJson | ConvertFrom-Json
    Write-Log "★ 上市预警 $($al.Count) 条:"
    foreach ($a in $al) {
        Write-Log "   [$($a.brand)] $($a.source_id) $($a.message)"
    }
} catch {
    Write-Log "预警汇总解析失败: $_"
}

Write-Log "==== 日常抓取结束 ===="
