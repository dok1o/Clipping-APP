# AI Clipper launcher (Windows): venv -> deps -> migrations -> API (+ optional worker/beat/frontend).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1                # API only
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -All           # API + worker + beat + frontend
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -Frontend
param(
    [switch]$All,
    [switch]$Frontend,
    [switch]$Worker,
    [switch]$Beat,
    [switch]$SkipInstall
)
. "$PSScriptRoot\common.ps1"

if ($All) { $Worker = $true; $Beat = $true; $Frontend = $true }

if (-not (Test-Venv)) { New-Venv }
if (-not $SkipInstall) { Install-Backend }
Load-DotEnv

# 1) migrations (idempotent)
Write-Host "[launcher] applying migrations ..." -ForegroundColor Cyan
Push-Location (Join-Path $RepoRoot "backend")
& $VenvPython -m alembic upgrade head
Pop-Location
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }

# 2) API (FastAPI/uvicorn) on 0.0.0.0:8000 by default; set API_HOST/API_PORT to override
$apiHost = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$script:ApiUrl = "http://127.0.0.1:$apiPort"
Write-Host "[launcher] starting API on ${apiHost}:${apiPort} ..." -ForegroundColor Cyan
$api = Start-Process -FilePath $VenvPython -ArgumentList "-m", "uvicorn", "app.main:app", "--host", $apiHost, "--port", $apiPort `
    -WorkingDirectory (Join-Path $RepoRoot "backend") -PassThru -WindowStyle Minimized
Save-Pid "api" $api

# 3) optional Celery worker + beat (needs real Redis; eager mode does not)
if ($Worker) {
    Write-Host "[launcher] starting Celery worker ..." -ForegroundColor Cyan
    $w = Start-Process -FilePath $VenvPython -ArgumentList "-m", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--pool=solo" `
        -WorkingDirectory (Join-Path $RepoRoot "backend") -PassThru -WindowStyle Minimized
    Save-Pid "worker" $w
}
if ($Beat) {
    Write-Host "[launcher] starting Celery beat ..." -ForegroundColor Cyan
    $b = Start-Process -FilePath $VenvPython -ArgumentList "-m", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info" `
        -WorkingDirectory (Join-Path $RepoRoot "backend") -PassThru -WindowStyle Minimized
    Save-Pid "beat" $b
}

# 4) optional frontend (Vite dev server)
if ($Frontend) {
    Write-Host "[launcher] starting frontend (Vite) ..." -ForegroundColor Cyan
    $f = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173" `
        -WorkingDirectory (Join-Path $RepoRoot "frontend") -PassThru -WindowStyle Minimized
    Save-Pid "frontend" $f
}

Write-Host ""
Write-Host "[launcher] started. Health: powershell -File scripts\windows\health.ps1" -ForegroundColor Green
Write-Host "[launcher] API      : $ApiUrl/health"
if ($Frontend) { Write-Host "[launcher] Frontend : http://127.0.0.1:5173" }
Write-Host "[launcher] Stop     : powershell -File scripts\windows\stop.ps1"
