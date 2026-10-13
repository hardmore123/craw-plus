$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$sites = Get-Content (Join-Path $root 'sites.json') -Raw -Encoding UTF8 | ConvertFrom-Json

$tmp = Join-Path $env:TEMP ('sitecheck_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

$worker = {
    param($s, $ua, $tmp)
    $ErrorActionPreference = 'Continue'
    $outFile = Join-Path $tmp ([guid]::NewGuid().ToString('N') + '.html')
    $errFile = Join-Path $tmp ([guid]::NewGuid().ToString('N') + '.err')

    $a = @(
        '-sS', '-L', '--max-time', '30', '--connect-timeout', '15',
        '-A', $ua,
        '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        '-o', $outFile,
        '-w', '%{http_code}|%{time_total}|%{num_redirects}|%{url_effective}|%{size_download}|%{remote_ip}',
        $s.url
    )

    $meta = & curl.exe @a 2> $errFile
    $exit = $LASTEXITCODE

    $err = ''
    if (Test-Path $errFile) {
        $err = (Get-Content $errFile -Raw -ErrorAction SilentlyContinue)
        if ($err) { $err = ($err -replace '\s+', ' ').Trim() }
    }

    $parts = @()
    if ($meta) { $parts = ($meta | Out-String).Trim() -split '\|' }

    $title = ''
    if (Test-Path $outFile) {
        if ((Get-Item $outFile).Length -gt 0) {
            try {
                $txt = Get-Content $outFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
                if ($txt) {
                    $m = [regex]::Match($txt, '(?is)<title[^>]*>(.*?)</title>')
                    if ($m.Success) {
                        $title = ($m.Groups[1].Value -replace '\s+', ' ').Trim()
                        if ($title.Length -gt 100) { $title = $title.Substring(0, 100) }
                    }
                }
            } catch { }
        }
    }
    Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue

    New-Object psobject -Property @{
        line      = $s.line
        name      = $s.name
        url       = $s.url
        code      = if ($parts.Count -ge 1) { $parts[0] } else { '' }
        time      = if ($parts.Count -ge 2) { $parts[1] } else { '' }
        redirects = if ($parts.Count -ge 3) { $parts[2] } else { '' }
        final_url = if ($parts.Count -ge 4) { $parts[3] } else { '' }
        bytes     = if ($parts.Count -ge 5) { $parts[4] } else { '' }
        ip        = if ($parts.Count -ge 6) { $parts[5] } else { '' }
        exit      = $exit
        error     = $err
        title     = $title
    }
}

$pool = [runspacefactory]::CreateRunspacePool(1, 6)
$pool.Open()
$handles = @()
foreach ($s in $sites) {
    $ps = [powershell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($worker).AddArgument($s).AddArgument($ua).AddArgument($tmp)
    $handles += New-Object psobject -Property @{ PS = $ps; H = $ps.BeginInvoke() }
}

$results = @()
foreach ($h in $handles) {
    $out = $h.PS.EndInvoke($h.H)
    if ($h.PS.HadErrors) {
        foreach ($e in $h.PS.Streams.Error) { Write-Warning ("runspace error: " + $e.ToString()) }
    }
    if ($out) { $results += $out }
    $h.PS.Dispose()
}
$pool.Close()
$pool.Dispose()
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

$json = Join-Path $root 'site_check_result.json'
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $json -Encoding UTF8

foreach ($r in $results) {
    if ($r.exit -eq 0 -and $r.code -match '^[23]') { $st = 'OK' }
    elseif ($r.exit -eq 0) { $st = 'HTTP-' + $r.code }
    else { $st = 'FAIL' }
    $t = 0.0
    [void][double]::TryParse($r.time, [ref]$t)
    '{0,-8} | {1,-13} | {2,-14} | code={3,-4} | {4,7:N2}s | redir={5,-3} | {6,9} B | {7}' -f `
        $st, $r.line, $r.name, $r.code, $t, $r.redirects, $r.bytes, $r.error
}
Write-Output ''
Write-Output ("JSON -> " + $json)
