$ErrorActionPreference = 'Continue'

$sites = @(
    @{ line='北美线-加拿大'; name='Amazon';         url='https://www.amazon.ca/' }
    @{ line='北美线-加拿大'; name='BestBuy';        url='https://www.bestbuy.ca/en-ca' }
    @{ line='北美线-加拿大'; name='Walmart';        url='https://www.walmart.ca/en' }
    @{ line='北美线-加拿大'; name='Costco';         url='https://www.costco.ca/' }
    @{ line='北美线-加拿大'; name='Brick';          url='https://www.thebrick.com/' }
    @{ line='北美线-加拿大'; name="Leon's";         url='https://www.leons.ca/' }
    @{ line='北美线-加拿大'; name='Visions';        url='https://www.visions.ca/' }
    @{ line='北美线-加拿大'; name='Canadian Tire';  url='https://www.canadiantire.ca/en.html' }
    @{ line='北美线-美国';   name='Best Buy';       url='https://www.bestbuy.com' }
    @{ line='北美线-美国';   name='Walmart';        url='https://www.walmart.com' }
    @{ line='北美线-美国';   name='Costco';         url='https://www.costco.com' }
    @{ line='北美线-美国';   name='Amazon';         url='https://www.amazon.com' }
    @{ line='北美线-墨西哥'; name='Amazon';         url='https://www.amazon.com.mx/' }
    @{ line='北美线-墨西哥'; name='Liverpool';      url='https://www.liverpool.com.mx/tienda/home' }
    @{ line='北美线-墨西哥'; name='Sams';           url='https://www.sams.com.mx/' }
    @{ line='北美线-墨西哥'; name='Palacio';        url='https://www.elpalaciodehierro.com/buscar?q=tv' }
    @{ line='北美线-墨西哥'; name='Walmart';        url='https://www.walmart.com.mx/search?q=TV' }
    @{ line='北美线-墨西哥'; name='Coppel';         url='https://www.coppel.com/sd/TV' }
)

$tmp = Join-Path $env:TEMP ('sitecheck_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

$results = $sites | ForEach-Object -Parallel {
    $s = $_
    $uaLocal = $using:ua
    $tmpLocal = $using:tmp
    $outFile = Join-Path $tmpLocal (([guid]::NewGuid().ToString('N')) + '.html')
    $errFile = Join-Path $tmpLocal (([guid]::NewGuid().ToString('N')) + '.err')

    $args = @(
        '-sS', '-L', '--max-time', '30', '--connect-timeout', '15',
        '-A', $uaLocal,
        '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        '-o', $outFile,
        '-w', '%{http_code}|%{time_total}|%{num_redirects}|%{url_effective}|%{size_download}|%{remote_ip}',
        $s.url
    )

    $meta = & curl.exe @args 2>$errFile
    $exit = $LASTEXITCODE
    $err = ''
    if (Test-Path $errFile) { $err = (Get-Content $errFile -Raw); if ($err) { $err = $err.Trim() } }

    $parts = @()
    if ($meta) { $parts = ($meta | Out-String).Trim() -split '\|' }

    $title = ''
    if (Test-Path $outFile) {
        $len = (Get-Item $outFile).Length
        if ($len -gt 0) {
            try {
                $txt = Get-Content $outFile -Raw -Encoding UTF8 -TotalCount 1 -ErrorAction SilentlyContinue
                if (-not $txt) { $txt = Get-Content $outFile -Raw -ErrorAction SilentlyContinue }
                if ($txt) {
                    $m = [regex]::Match($txt, '(?is)<title[^>]*>(.*?)</title>')
                    if ($m.Success) {
                        $title = ($m.Groups[1].Value -replace '\s+', ' ').Trim()
                        if ($title.Length -gt 120) { $title = $title.Substring(0,120) }
                    }
                }
            } catch { }
        }
    }
    Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue

    [pscustomobject]@{
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
} -ThrottleLimit 6

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

$json = Join-Path 'C:\Users\likunyuan\Desktop\爬取项目' 'site_check_result.json'
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $json -Encoding UTF8

$results | ForEach-Object {
    $status = if ($_.exit -eq 0 -and $_.code -match '^[23]') { 'OK' } `
              elseif ($_.exit -eq 0) { 'HTTP-' + $_.code } `
              else { 'FAIL' }
    '{0,-6} {1,-14} {2,-14} code={3,-4} {4,7:N2}s redir={5,-3} bytes={6,-10} {7}' -f `
        $status, $_.line, $_.name, $_.code, [double]($_.time), $_.redirects, $_.bytes, $_.error
}
Write-Output ''
Write-Output "JSON -> $json"
