$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$powershellExe = Join-Path $PSHOME "powershell.exe"
if (-not (Test-Path -LiteralPath $powershellExe)) {
    $powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
}

$shell = New-Object -ComObject WScript.Shell

$startShortcut = $shell.CreateShortcut((Join-Path $desktop "AI Clipper.lnk"))
$startShortcut.TargetPath = $powershellExe
$startShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $PSScriptRoot 'start_clipping_app.ps1')`""
$startShortcut.WorkingDirectory = $projectRoot
$startShortcut.Description = "Start AI Clipper and open it in the browser"
$startShortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$startShortcut.Save()

$stopShortcut = $shell.CreateShortcut((Join-Path $desktop "Stop AI Clipper.lnk"))
$stopShortcut.TargetPath = $powershellExe
$stopShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $PSScriptRoot 'stop_clipping_app.ps1')`""
$stopShortcut.WorkingDirectory = $projectRoot
$stopShortcut.Description = "Stop AI Clipper background processes"
$stopShortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,131"
$stopShortcut.Save()

Write-Output "Desktop shortcuts created."
