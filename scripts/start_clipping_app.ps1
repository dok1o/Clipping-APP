[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoDialog
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$runtimeRoot = Join-Path $projectRoot "storage\run"
$pidFile = Join-Path $runtimeRoot "desktop-processes.state"
$logFile = Join-Path $runtimeRoot "desktop-launcher.log"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$motoExe = Join-Path $projectRoot ".venv\Scripts\moto_server.exe"
$viteScript = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
$appUrl = "http://127.0.0.1:5173/"

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logFile -Value "[$timestamp] $Message" -Encoding utf8
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 500
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            return $false
        }
        $client.EndConnect($connection)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-TcpPort {
    param(
        [string]$Name,
        [int]$Port,
        [int]$TimeoutSec = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not start on port $Port within $TimeoutSec seconds."
}

function Wait-HttpOk {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSec = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "$Name did not become healthy within $TimeoutSec seconds."
}

function Get-LiveProcessRecords {
    $records = @()
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return $records
    }

    try {
        foreach ($line in Get-Content -LiteralPath $pidFile) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            $parts = $line.Split("|", 3)
            if ($parts.Count -ne 3) {
                continue
            }
            $record = [pscustomobject]@{
                name = $parts[0]
                pid = [int]$parts[1]
                startTicks = [long]$parts[2]
            }
            $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
            if ($null -ne $process) {
                try {
                    if ($process.StartTime.ToUniversalTime().Ticks -eq [long]$record.startTicks) {
                        $records += $record
                    }
                }
                catch {
                    Write-LauncherLog "Ignoring stale process record for $($record.name)."
                }
            }
        }
    }
    catch {
        Write-LauncherLog "Ignoring an invalid process state file."
    }
    return $records
}

$processRecords = @(Get-LiveProcessRecords)
$startedThisRun = @()

function Save-ProcessRecords {
    if (@($script:processRecords).Count -eq 0) {
        Set-Content -LiteralPath $pidFile -Value "" -Encoding utf8
        return
    }
    $lines = foreach ($record in @($script:processRecords)) {
        "$($record.name)|$($record.pid)|$($record.startTicks)"
    }
    Set-Content -LiteralPath $pidFile -Value $lines -Encoding utf8
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $result = Start-Process `
        -FilePath "taskkill.exe" `
        -ArgumentList @("/PID", "$ProcessId", "/T", "/F") `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    return $result.ExitCode
}

function Start-TrackedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )

    $stdoutPath = Join-Path $runtimeRoot "$Name.stdout.log"
    $stderrPath = Join-Path $runtimeRoot "$Name.stderr.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) {
        $details = ""
        if (Test-Path -LiteralPath $stderrPath) {
            $details = (Get-Content -LiteralPath $stderrPath -Raw).Trim()
        }
        throw "$Name exited during startup. $details"
    }

    $record = [pscustomobject]@{
        name = $Name
        pid = $process.Id
        startTicks = $process.StartTime.ToUniversalTime().Ticks
    }
    $script:processRecords += $record
    $script:startedThisRun += $process.Id
    Save-ProcessRecords
    Write-LauncherLog "Started $Name (PID $($process.Id))."
}

try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Python virtual environment was not found: $pythonExe"
    }
    if (-not (Test-Path -LiteralPath $motoExe)) {
        throw "Moto server was not found. Run the backend dependency installation first."
    }
    if (-not (Test-Path -LiteralPath $viteScript)) {
        throw "Frontend dependencies were not found. Run: npm --prefix frontend install"
    }

    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 9000)) {
        Start-TrackedProcess `
            -Name "moto" `
            -FilePath $motoExe `
            -ArgumentList @("-H", "127.0.0.1", "-p", "9000") `
            -WorkingDirectory $projectRoot
        Wait-TcpPort -Name "Local S3" -Port 9000
    }

    Push-Location $backendRoot
    try {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $migrationOutput = & $pythonExe -m alembic upgrade head 2>&1
        $migrationExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
        $migrationOutput | Add-Content -LiteralPath $logFile -Encoding utf8
        if ($migrationExitCode -ne 0) {
            throw "Database migration failed. See $logFile"
        }

        $ensureBucket = "from app.core.config import get_settings; from app.infra.s3 import S3Storage; storage = S3Storage.from_settings(get_settings()); storage.ensure_bucket()"
        $ErrorActionPreference = "Continue"
        $bucketOutput = & $pythonExe -c $ensureBucket 2>&1
        $bucketExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
        $bucketOutput | Add-Content -LiteralPath $logFile -Encoding utf8
        if ($bucketExitCode -ne 0) {
            throw "S3 bucket initialization failed. See $logFile"
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 8000)) {
        Start-TrackedProcess `
            -Name "backend" `
            -FilePath $pythonExe `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $backendRoot
    }
    Wait-HttpOk -Name "Backend" -Url "http://127.0.0.1:8000/health"

    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 5173)) {
        $nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
        $quotedViteScript = "`"$viteScript`""
        Start-TrackedProcess `
            -Name "frontend" `
            -FilePath $nodeExe `
            -ArgumentList @($quotedViteScript, "--host", "127.0.0.1", "--port", "5173") `
            -WorkingDirectory $frontendRoot
    }
    Wait-HttpOk -Name "Frontend" -Url $appUrl

    Write-LauncherLog "AI Clipper is ready at $appUrl"
    if (-not $NoBrowser) {
        Start-Process $appUrl
    }
}
catch {
    Write-LauncherLog "Startup failed: $($_.Exception.Message)"
    $startedProcessIds = @($startedThisRun)
    for ($index = $startedProcessIds.Count - 1; $index -ge 0; $index--) {
        Stop-ProcessTree -ProcessId $startedProcessIds[$index] | Out-Null
    }
    $processRecords = @($processRecords | Where-Object { $startedThisRun -notcontains $_.pid })
    Save-ProcessRecords

    if (-not $NoDialog) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "$($_.Exception.Message)`n`nLog: $logFile",
            "AI Clipper startup error",
            "OK",
            "Error"
        ) | Out-Null
    }
    exit 1
}
