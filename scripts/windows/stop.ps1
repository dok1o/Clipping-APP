# Stop AI Clipper processes started by start.ps1 (API/worker/beat/frontend).
. "$PSScriptRoot\common.ps1"

foreach ($name in @("api", "worker", "beat", "frontend")) {
    $p = Get-SavedPid $name
    if ($p) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            Write-Host ("[stop] {0} (pid {1}) stopped" -f $name, $p) -ForegroundColor Green
        } else {
            Write-Host ("[stop] {0} (pid {1}) already gone" -f $name, $p) -ForegroundColor DarkGray
        }
        Remove-Item (Join-Path $RunDir "$name.pid") -ErrorAction SilentlyContinue
    } else {
        Write-Host "[stop] $name : no pid file (not started here)" -ForegroundColor DarkGray
    }
}
Write-Host "[stop] done" -ForegroundColor Green
