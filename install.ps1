[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    throw "Python 3.9 or newer is required."
}
$installer = Join-Path $repoRoot "tools/install_skill.py"
if ($Destination) {
    & $pythonCommand.Source -X utf8 $installer $Destination
} else {
    & $pythonCommand.Source -X utf8 $installer
}
if ($LASTEXITCODE -ne 0) {
    throw "Skill installation failed (exit code $LASTEXITCODE)."
}
