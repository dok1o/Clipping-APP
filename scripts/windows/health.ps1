# Check AI Clipper health: /health endpoint + saved processes.
. "$PSScriptRoot\common.ps1"

$failed = $false

Write-Host "[health] GET $ApiUrl/health"
try {
    $response = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
    Write-Host ("[health] API: {0} (version {1})" -f $response.status, $response.version) -ForegroundColor Green
    foreach ($prop in $response.checks.PSObject.Properties) {
        Write-Host ("[health]   {0}: {1}" -f $prop.Name, $prop.Value)
    }
    if ($response.status -ne "ok") { $failed = $true }
} catch {
    Write-Host "[health] API: UNREACHABLE ($($_.Exception.Message))" -ForegroundColor Red
    $failed = $true
}

foreach ($name in @("api", "worker", "beat", "frontend")) {
    $p = Get-SavedPid $name
    if ($p) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host ("[health] process {0} (pid {1}): running" -f $name, $p) -ForegroundColor Green
        } else {
            Write-Host ("[health] process {0} (pid {1}): NOT running" -f $name, $p) -ForegroundColor Yellow
        }
    }
}

if ($failed) { exit 1 } else { exit 0 }
