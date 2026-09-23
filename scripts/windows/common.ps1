# Shared helpers for AI Clipper Windows launcher (start/health/stop).
$ErrorActionPreference = "Stop"
# Repo root = parent of scripts/windows
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:RunDir = Join-Path $RepoRoot ".run"
$script:VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$script:ApiUrl = "http://127.0.0.1:8000"

function Test-Venv {
    return (Test-Path $VenvPython)
}

function New-Venv {
    Write-Host "[launcher] creating .venv ..." -ForegroundColor Yellow
    python -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed (is Python 3.11+ on PATH?)" }
}

function Install-Backend {
    & $VenvPython -m pip install -e (Join-Path $RepoRoot "backend[dev,ml]")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

function Load-DotEnv {
    # Minimal .env loader (KEY=VALUE lines, no quoting magic). Real secrets stay local.
    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $parts = $line.Split("=", 2)
                $name = $parts[0].Trim()
                if (-not [Environment]::GetEnvironmentVariable($name)) {
                    [Environment]::SetEnvironmentVariable($name, $parts[1].Trim(), "Process")
                }
            }
        }
        Write-Host "[launcher] loaded .env" -ForegroundColor DarkGray
    }
}

function Save-Pid($name, $process) {
    if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }
    $process.Id | Out-File -FilePath (Join-Path $RunDir "$name.pid") -Encoding ascii
}

function Get-SavedPid($name) {
    $pidFile = Join-Path $RunDir "$name.pid"
    if (Test-Path $pidFile) {
        $v = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $parsed = 0
        if ($v -and [int]::TryParse($v, [ref]$parsed)) { return $parsed }
    }
    return $null
}
