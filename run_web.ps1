# ==============================================================================
# ParrotGo - Run Web Playground (Voice & Chat Interface)
# ==============================================================================

param (
    [int]$Port = 8000,
    [string]$HostIP = "127.0.0.1",
    [switch]$NoBrowser
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 >$null

$PythonCmd = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "py" }

if (-not $NoBrowser) {
    Start-Process "http://$HostIP`:$Port"
}

$env:PORT = "$Port"
$env:HOST = "$HostIP"

& $PythonCmd -m src.web.run
