# scripts/verify_build.ps1 — smoke: start exe, poll health (401 = up + auth), kill.
$ErrorActionPreference = "Stop"
$proc = Start-Process -FilePath "dist\SupplyChainSparks\SupplyChainSparks.exe" -PassThru
try {
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/health" -UseBasicParsing
            if ($r.StatusCode -eq 401) { $ok = $true; break }
        } catch {
            # IWR throws on 4xx: a 401 response IS the success signal (auth enforced)
            $resp = $_.Exception.Response
            if ($resp -and [int]$resp.StatusCode -eq 401) { $ok = $true; break }
        }
    }
    if (-not $ok) { throw "health endpoint did not come up (401 expected without token)" }
    Write-Host "BUILD OK - server up, auth enforced"
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
