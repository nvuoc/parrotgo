# ==============================================================================
# ParrotGo - Run Interactive CLI Demo (Nationwide Voicebot)
# ==============================================================================

param (
    [string]$Phone = $null,
    [string]$Name = $null,
    [string]$City = $null,
    [switch]$NoDebug
)

# Set Windows console to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 >$null

$PythonCmd = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "py" }

$CliArgs = @()
if ($Phone) { $CliArgs += @("--phone", $Phone) }
if ($Name) { $CliArgs += @("--name", $Name) }
if ($City) { $CliArgs += @("--city", $City) }
if (-not $NoDebug) { $CliArgs += "--debug" }

& $PythonCmd -m src.cli.runner @CliArgs
