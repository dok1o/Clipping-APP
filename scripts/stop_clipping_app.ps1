[CmdletBinding()]
param(
    [switch]$NoDialog
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = Join-Path $projectRoot "storage\run"
$pidFile = Join-Path $runtimeRoot "desktop-processes.state"
$logFile = Join-Path $runtimeRoot "desktop-launcher.log"

function Write-LauncherLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logFile -Value "[$timestamp] $Message" -Encoding utf8
}

$stopped = 0
if (Test-Path -LiteralPath $pidFile) {
    try {
        $records = @()
        foreach ($line in Get-Content -LiteralPath $pidFile) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            $parts = $line.Split("|", 3)
            if ($parts.Count -ne 3) {
                continue
            }
            $records += [pscustomobject]@{
                name = $parts[0]
                pid = [int]$parts[1]
                startTicks = [long]$parts[2]
            }
        }
        for ($index = $records.Count - 1; $index -ge 0; $index--) {
            $record = $records[$index]
            $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
            if ($null -ne $process) {
                try {
                    if ($process.StartTime.ToUniversalTime().Ticks -eq [long]$record.startTicks) {
                        $result = Start-Process `
                            -FilePath "taskkill.exe" `
                            -ArgumentList @("/PID", "$($process.Id)", "/T", "/F") `
                            -WindowStyle Hidden `
                            -Wait `
                            -PassThru
                        if ($result.ExitCode -eq 0) {
                            Write-LauncherLog "Stopped $($record.name) process tree (PID $($process.Id))."
                            $stopped++
                        }
                        else {
                            Write-LauncherLog "taskkill failed for $($record.name) with exit code $($result.ExitCode)."
                        }
                    }
                }
                catch {
                    Write-LauncherLog "Could not stop $($record.name): $($_.Exception.Message)"
                }
            }
        }
    }
    catch {
        Write-LauncherLog "Stop warning: $($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

if (-not $NoDialog) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "AI Clipper processes stopped: $stopped",
        "AI Clipper",
        "OK",
        "Information"
    ) | Out-Null
}
